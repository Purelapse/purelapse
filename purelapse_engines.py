#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
purelapse_engines.py
=====================
Kapselt alles, was sich zwischen den Entwicklungs-Engines (ART, RawTherapee,
Darktable) unterscheidet. Der Rest von Purelapse kennt nur noch:

    read_arp_dict(path)      -> dict
    write_arp_dict(path, d)  -> None
    set_exposure(d, ev)      -> None
    interpolate_arp_dicts(s, e, ratio) -> dict
    profile_is_complete(d)   -> bool
    strip_rank(d)            -> dict
    set_raw_hotpixel(d, on)  -> None
    check_is_keyframe(path)  -> bool
    find_arp_template(dir, files=None) -> (dict|None, str)
    bootstrap_arp_template(cli_path, sample_image) -> (dict|None, str)
    validate_arp(profile, reference, name) -> list[str]
    write_arp_file(filepath, ev_offset, template=None, hotpixel=False)

Alle diese Funktionen verzweigen intern anhand der globalen ENGINE-Variable.
ART und RawTherapee teilen sich weiterhin dieselbe INI-Implementierung -
fuer Darktable gibt es eine eigene, XML-basierte Variante, die aber nach
aussen dieselbe Dict-Form liefert ("Shim"), damit der Rest des Programms
nicht wissen muss, mit welcher Engine er gerade arbeitet.
"""
import os
import glob
import shutil
import tempfile
import subprocess
import struct
import json
import threading
import re
import math

# Windows: Konsolenprogramme (Engines, FFmpeg) ohne eigenes Fenster starten.
# Ohne das blitzte bei jedem Aufruf ein schwarzes Konsolenfenster auf.
OHNE_FENSTER = ({'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)}
                if os.name == 'nt' else {})
import xml.etree.ElementTree as ET

# ==========================================================================
#  ENGINE-KONFIGURATION
# ==========================================================================
ENGINES = {
    'art': {
        'label': "ART",
        'ext': ".arp",
        'bin': "ART-cli",
        'base': 'basis_art.arp',
        'extra': [],
        'kind': 'ini',
        # Name der eigenen Farbtemperatur in [White Balance] Setting.
        # ART: WBParams::CUSTOM_TEMP -> "CustomTemp"
        # (src/engine/procparams.cc)
        'wb_custom': "CustomTemp",
    },
    'rt': {
        'label': "RawTherapee",
        'ext': ".pp3",
        'bin': "rawtherapee-cli",
        'base': 'basis_rt.pp3',
        'extra': ["-d"],
        'kind': 'ini',
        # RawTherapee kennt den Eintrag "Custom", NICHT "CustomTemp"
        # (rtengine/procparams.cc, WBParams::getWbEntries()).
        'wb_custom': "Custom",
    },
    'dt': {
        'label': "Darktable",
        'ext': ".xmp",
        'bin': "darktable-cli",
        'base': 'basis_dt.xmp',
        'extra': [],
        'kind': 'darktable',
        'wb_custom': "",
    },
    # Lightroom Classic: kein Programm, das Purelapse aufrufen koennte.
    # Purelapse schreibt die XMP-Begleitdateien (BILD.xmp, ohne die Endung
    # des RAW), Lightroom liest sie ein und exportiert die Serie; aus dem
    # Export baut Purelapse das Video. Siehe TEIL C.
    'lr': {
        'label': "Lightroom",
        'ext': ".xmp",
        'bin': "",
        'base': '',
        'extra': [],
        'kind': 'lightroom',
        'wb_custom': "Custom",
    },
}
ENGINE = 'art'


def set_engine(key):
    """Legt fest, mit welcher Anwendung entwickelt wird."""
    global ENGINE
    ENGINE = key if key in ENGINES else 'art'


def eng(feld):
    return ENGINES[ENGINE][feld]


def sidecar(image_path):
    """Pfad der Begleitdatei zu einem Bild - .arp, .pp3 oder .xmp.
    Lightroom nennt sie nach dem Bild OHNE dessen Endung (IMG_0001.xmp),
    alle anderen haengen ihre Endung an (IMG_0001.NEF.xmp)."""
    if ENGINE == 'lr':
        return os.path.splitext(image_path)[0] + eng('ext')
    return image_path + eng('ext')


def xmp_herkunft(xmp_pfad):
    """
    Wer hat diese .xmp geschrieben? 'dt' (darktable), 'lr' (Lightroom bzw.
    die Raw-Entwicklung, die dieselben Einstellungen liest) oder
    'bewertung' (nur eine Sternebewertung, etwa von Purelapse selbst).
    """
    try:
        with open(xmp_pfad, 'r', encoding='utf-8', errors='ignore') as f:
            inhalt = f.read(262144)
    except OSError:
        return 'bewertung'
    if 'darktable:' in inhalt or 'darktable.org' in inhalt:
        return 'dt'
    if 'ns.adobe.com/camera-raw-settings/1.0/' in inhalt:
        return 'lr'
    return 'bewertung'


def ist_reine_bewertung(xmp_pfad):
    """
    Stammt diese .xmp nur aus Purelapses Keyframe-Markierung?

    Purelapse legt fuer jedes markierte Bild eine winzige .xmp mit
    xmp:Rating an - auch dann, wenn mit ART oder RawTherapee gearbeitet
    wird. Solche Dateien duerfen nicht als Darktable-Sidecar zaehlen,
    sonst erkennt Purelapse in seinem eigenen Ordner die falsche Engine.

    Eine echte Darktable-Sidecar bringt den darktable-Namensraum und
    eine Liste bearbeiteter Module mit.
    """
    if not os.path.exists(xmp_pfad):
        return False
    return xmp_herkunft(xmp_pfad) == 'bewertung'


def engine_key():
    """Die aktuell eingestellte Engine. Fuer Module, die set_engine()
    nicht sehen - ein importiertes ENGINE waere dort eine Kopie vom
    Importzeitpunkt und bliebe fuer immer stehen."""
    return ENGINE


def detect_engine(target_dir):
    """
    Erkennt an den vorhandenen Begleitdateien, womit gearbeitet wurde.
    Rueckgabe: 'art', 'rt', 'dt' oder None, wenn nichts oder mehreres vorliegt.
    """
    gefunden = []
    for key, cfg in ENGINES.items():
        muster = cfg['ext']
        treffer = (glob.glob(os.path.join(target_dir, "*" + muster))
                   + glob.glob(os.path.join(target_dir, "*" + muster.upper())))
        if cfg['ext'] == '.xmp':
            # .xmp schreiben darktable und Lightroom - und Purelapse selbst
            # fuer Keyframe-Sterne. Es zaehlt, wer die Datei geschrieben hat.
            treffer = [p for p in treffer if xmp_herkunft(p) == key]
        if treffer:
            gefunden.append(key)
    return gefunden[0] if len(gefunden) == 1 else None


# ==========================================================================
#  EINE KONFIGURATIONSDATEI
#
#  Bisher legte Purelapse bis zu 16 einzelne Dateien direkt im
#  Benutzerordner an (~/.purelapse_theme, ~/.purelapse_lang, ...). Jetzt
#  steht alles in einer Datei:
#      Linux    ~/.config/purelapse/purelapse.json
#      Windows  %APPDATA%\Purelapse\purelapse.json
#  Sie ist nur fuer den Benutzer lesbar (darin steht der Telegram-Token).
#  Die alten Dateien werden beim ersten Start uebernommen und entfernt.
#  Selbst erzeugte Basisprofile der Engines sind keine Einstellungen und
#  liegen im Datenordner (~/.local/share/purelapse).
# ==========================================================================
_KONFIG_SPERRE = threading.RLock()
_KONFIG_ZWISCHEN = {'pfad': None, 'stand': None, 'daten': None}


def konfig_ordner():
    if os.name == 'nt':
        return os.path.join(os.environ.get('APPDATA') or os.path.expanduser("~"), "Purelapse")
    return os.path.join(os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser("~/.config"),
                        "purelapse")


def konfig_pfad():
    return os.path.join(konfig_ordner(), "purelapse.json")


def daten_ordner():
    if os.name == 'nt':
        return os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser("~"), "Purelapse")
    return os.path.join(os.environ.get('XDG_DATA_HOME') or os.path.expanduser("~/.local/share"),
                        "purelapse")


def basis_profil_pfad():
    return os.path.join(daten_ordner(), eng('base'))


def _alte_dateien():
    """Die Einzeldateien frueherer Versionen: Pfad -> (Schluessel, Art)."""
    h = os.path.expanduser("~")
    alt = {
        ".purelapse_last_path": (('letzter_ordner',), 'text'),
        ".purelapse_bereiche.json": (('bereiche',), 'json'),
        ".purelapse_settings.json": (('einstellungen',), 'json'),
        ".purelapse_queue.json": (('warteschlange',), 'json'),
        ".purelapse_lang": (('sprache',), 'text'),
        ".purelapse_theme": (('design',), 'text'),
        ".purelapse_telegram.json": (('telegram',), 'json'),
        ".purelapse_art_path": (('engines', 'art', 'programm'), 'text'),
        ".purelapse_arp_template": (('engines', 'art', 'profil'), 'text'),
        ".purelapse_rt_path": (('engines', 'rt', 'programm'), 'text'),
        ".purelapse_rt_template": (('engines', 'rt', 'profil'), 'text'),
        ".purelapse_dt_path": (('engines', 'dt', 'programm'), 'text'),
        ".purelapse_dt_template": (('engines', 'dt', 'profil'), 'text'),
    }
    return {os.path.join(h, n): v for n, v in alt.items()}


_ALTE_BASIS = {".purelapse_base.arp": "basis_art.arp", ".purelapse_rt_base.pp3": "basis_rt.pp3",
               ".purelapse_dt_base.xmp": "basis_dt.xmp"}


def _konfig_uebernehmen():
    """Liest die alten Einzeldateien in ein Dict; leer, wenn es keine gibt."""
    daten = {}
    gefunden = []
    for pfad, (schluessel, art) in _alte_dateien().items():
        if not os.path.isfile(pfad):
            continue
        try:
            with open(pfad, "r", encoding="utf-8", errors="replace") as f:
                inhalt = f.read()
            wert = json.loads(inhalt) if art == 'json' else inhalt.strip()
        except (OSError, ValueError):
            gefunden.append(pfad)
            continue
        ziel = daten
        for k in schluessel[:-1]:
            ziel = ziel.setdefault(k, {})
        ziel[schluessel[-1]] = wert
        gefunden.append(pfad)
    h = os.path.expanduser("~")
    for alt, neu in _ALTE_BASIS.items():
        a = os.path.join(h, alt)
        if os.path.isfile(a):
            n = os.path.join(daten_ordner(), neu)
            try:
                os.makedirs(daten_ordner(), exist_ok=True)
                shutil.move(a, n)
            except OSError:
                continue
            for eng_key in ('art', 'rt', 'dt'):
                prof = daten.get('engines', {}).get(eng_key, {})
                if prof.get('profil') == a:
                    prof['profil'] = n
    return daten, gefunden


def konfig_laden():
    """Die ganze Konfiguration als Dict (eine Kopie)."""
    with _KONFIG_SPERRE:
        pfad = konfig_pfad()
        try:
            stand = os.stat(pfad).st_mtime_ns
        except OSError:
            stand = None
        z = _KONFIG_ZWISCHEN
        if z['pfad'] == pfad and z['stand'] == stand and z['daten'] is not None:
            return json.loads(json.dumps(z['daten']))
        daten = {}
        if stand is not None:
            try:
                with open(pfad, "r", encoding="utf-8") as f:
                    daten = json.load(f)
                if not isinstance(daten, dict):
                    daten = {}
            except (OSError, ValueError):
                daten = {}
        else:
            daten, alte = _konfig_uebernehmen()
            if daten or alte:
                if _konfig_schreiben_roh(daten):
                    for a in alte:
                        try:
                            os.remove(a)
                        except OSError:
                            pass
                try:
                    stand = os.stat(pfad).st_mtime_ns
                except OSError:
                    stand = None
        z.update(pfad=pfad, stand=stand, daten=daten)
        return json.loads(json.dumps(daten))


def _konfig_schreiben_roh(daten):
    try:
        os.makedirs(konfig_ordner(), exist_ok=True)
        pfad = konfig_pfad()
        datei_atomar(pfad, json.dumps(daten, indent=1, ensure_ascii=False))
        os.chmod(pfad, 0o600)
        return True
    except OSError:
        return False


def konfig_lesen(*schluessel, standard=None):
    wert = konfig_laden()
    for k in schluessel:
        if not isinstance(wert, dict) or k not in wert:
            return standard
        wert = wert[k]
    return wert


def konfig_setzen(*schluessel_und_wert):
    """konfig_setzen('design', 'dark') oder konfig_setzen('engines', 'rt', 'programm', pfad)"""
    *schluessel, wert = schluessel_und_wert
    with _KONFIG_SPERRE:
        daten = konfig_laden()
        ziel = daten
        for k in schluessel[:-1]:
            if not isinstance(ziel.get(k), dict):
                ziel[k] = {}
            ziel = ziel[k]
        if wert is None:
            ziel.pop(schluessel[-1], None)
        else:
            ziel[schluessel[-1]] = wert
        ok = _konfig_schreiben_roh(daten)
        _KONFIG_ZWISCHEN['daten'] = None
        return ok


# Wo die Installer der Engines unter Windows ablegen - relativ zu
# "C:\Program Files" und Co. Die Versionsordner (RawTherapee\5.10) werden
# per Muster gefunden, die neueste zuerst.
WINDOWS_ORTE = {
    'art': ("ART\\ART-cli.exe", "ART*\\ART-cli.exe"),
    'rt': ("RawTherapee\\*\\rawtherapee-cli.exe", "RawTherapee\\rawtherapee-cli.exe"),
    'dt': ("darktable\\bin\\darktable-cli.exe",),
}


def _versions_schluessel(pfad):
    """Sortiert 5.10 nach 5.9 - Zahlen als Zahlen, nicht als Text."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r'(\d+)', pfad)]


def engine_suchen(key=None, umgebung=None, nt=None, suchpfad=True):
    """
    Das Kommandozeilenprogramm einer Engine: erst im Suchpfad, unter
    Windows dann in den ueblichen Installationsordnern.
    suchpfad=False laesst den Suchpfad aus (fuer die Pruefungen: ein
    installiertes RawTherapee soll sie nicht beeinflussen).
    Rueckgabe: Pfad oder "".
    """
    key = key or engine_key()
    bin_name = ENGINES[key]['bin']
    gefunden = shutil.which(bin_name) if suchpfad else None
    if gefunden:
        return gefunden
    if not (os.name == 'nt' if nt is None else nt):
        return ""
    env = os.environ if umgebung is None else umgebung
    wurzeln = []
    for name in ('ProgramW6432', 'ProgramFiles', 'ProgramFiles(x86)'):
        w = env.get(name)
        if w and w not in wurzeln:
            wurzeln.append(w)
    if env.get('LOCALAPPDATA'):
        wurzeln.append(os.path.join(env['LOCALAPPDATA'], "Programs"))
    for w in wurzeln:
        for muster in WINDOWS_ORTE.get(key, ()):
            treffer = sorted(glob.glob(os.path.join(w, *muster.split('\\'))),
                             key=_versions_schluessel, reverse=True)
            for t in treffer:
                if os.path.isfile(t):
                    return t
    return ""


# ==========================================================================
#  Engines als Flatpak (Flathub)
#
#  Ein Flatpak legt kein Programm in den Suchpfad; die Kommandozeilen-
#  fassung steckt im Paket und wird mit "flatpak run --command=..."
#  gestartet. Purelapse merkt sich dafuer den Ersatzpfad "flatpak:<App-ID>".
#  Die Engine laeuft dabei in ihrer Sandbox: jeder Ordner, den sie lesen
#  oder beschreiben soll, wird beim Aufruf mit --filesystem freigegeben -
#  auch Arbeitsordner unter /tmp, das in der Sandbox sonst ein eigenes ist.
# ==========================================================================
FLATPAK = 'flatpak:'
FLATPAK_IDS = {
    'art': "us.pixls.art.ART",
    'rt': "com.rawtherapee.RawTherapee",
    'dt': "org.darktable.Darktable",
}
# Ordner, die Flatpak nicht freigibt (und die eine Engine nie braucht)
_FLATPAK_TABU = ('/usr', '/proc', '/dev', '/sys', '/etc', '/app', '/lib', '/bin')


def flatpak_orte(home=None):
    """Die Installationsorte von Flatpak: systemweit und fuer den Nutzer."""
    home = home or os.path.expanduser("~")
    return ["/var/lib/flatpak", os.path.join(home, ".local", "share", "flatpak")]


def flatpak_installiert(app_id, orte=None):
    for wurzel in (orte if orte is not None else flatpak_orte()):
        if os.path.isdir(os.path.join(wurzel, "app", app_id, "current")):
            return True
    return False


def ist_flatpak(pfad):
    return bool(pfad) and str(pfad).startswith(FLATPAK)


def flatpak_suchen(key=None, orte=None, nt=None):
    """Ersatzpfad "flatpak:<ID>", wenn die Engine als Flatpak da ist, sonst "".
    Unter Windows gibt es kein Flatpak (nt=None: das laufende System)."""
    key = key or engine_key()
    app_id = FLATPAK_IDS.get(key)
    if not app_id or (os.name == 'nt' if nt is None else nt):
        return ""
    if shutil.which("flatpak") is None and orte is None:
        return ""
    return FLATPAK + app_id if flatpak_installiert(app_id, orte) else ""


def engine_vorhanden(pfad, orte=None):
    """Gibt es das eingetragene Engine-Programm (Datei oder Flatpak)?"""
    if not pfad:
        return False
    if ist_flatpak(pfad):
        return flatpak_installiert(pfad[len(FLATPAK):], orte)
    return os.path.isfile(pfad)


def _flatpak_freigaben(args):
    ordner = []
    for a in args:
        a = str(a)
        if not os.path.isabs(a):
            continue
        if os.path.isdir(a):
            d = a
        elif os.path.exists(a) or os.path.splitext(a)[1]:
            d = os.path.dirname(a)       # Datei (auch eine, die erst entsteht)
        else:
            d = a                         # Ordner, der noch angelegt wird
        d = os.path.normpath(d)
        tabu = [os.path.normpath(t) for t in _FLATPAK_TABU]
        if d in (os.sep, '') or any(d == t or d.startswith(t + os.sep) for t in tabu):
            continue
        if d not in ordner:
            ordner.append(d)
    # Unterordner eines schon freigegebenen Ordners brauchen keine eigene Freigabe
    return [d for d in ordner
            if not any(d != o and d.startswith(o.rstrip(os.sep) + os.sep) for o in ordner)]


def engine_befehl(cmd, env=None, key=None):
    """
    Der wirkliche Aufruf. Steht vorne ein Ersatzpfad "flatpak:<ID>", wird
    daraus "flatpak run" mit dem Kommandozeilenprogramm der Engine, den
    noetigen Ordnerfreigaben und den Umgebungsvariablen, die Purelapse
    setzt (die Sandbox reicht sie sonst nicht sicher durch).
    """
    cmd = list(cmd)
    if not cmd or not ist_flatpak(cmd[0]):
        return cmd
    app_id = cmd[0][len(FLATPAK):]
    key = key or next((k for k, v in FLATPAK_IDS.items() if v == app_id), engine_key())
    vorne = ["flatpak", "run", f"--command={ENGINES[key]['bin']}"]
    vorne += [f"--filesystem={d}" for d in _flatpak_freigaben(cmd[1:])]
    for name in ('OMP_NUM_THREADS',):
        if env and env.get(name):
            vorne.append(f"--env={name}={env[name]}")
    return vorne + [app_id] + cmd[1:]


def prozess_beenden(proc):
    """
    Beendet ein gestartetes Programm sofort - unter Windows samt allen
    Prozessen, die es selbst gestartet hat. Sonst liefe dort z. B. hinter
    einer .cmd- oder .bat-Huelle das eigentliche Programm weiter, und wer
    auf dessen Ausgabe wartet, wartete bis zu dessen Ende.
    """
    if proc is None or proc.poll() is not None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, **OHNE_FENSTER)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()
    except OSError:
        pass


def get_art_path():
    wert = konfig_lesen('engines', engine_key(), 'programm', standard="")
    if wert and engine_vorhanden(wert):
        return wert
    # Eingetragenes Programm fehlt (deinstalliert, auf Flatpak umgestiegen):
    # neu suchen, sonst den Eintrag zeigen, damit man sieht, was fehlt.
    return engine_suchen() or flatpak_suchen() or wert


def save_art_path(path):
    konfig_setzen('engines', engine_key(), 'programm', path)


def get_arp_template_path():
    return konfig_lesen('engines', engine_key(), 'profil', standard="") or ""


def save_arp_template_path(path):
    konfig_setzen('engines', engine_key(), 'profil', path)


# ==========================================================================
#  HILFSFUNKTIONEN (engine-unabhaengig)
# ==========================================================================
def _looks_like_int(text):
    return str(text).strip().lstrip('+-').isdigit()


def _value_kind(value):
    v = str(value).strip()
    if v == '':
        return 'leer'
    if v.lower() in ('true', 'false'):
        return 'bool'
    if ';' in v:
        parts = [t.strip() for t in v.split(';') if t.strip()]
        if not parts:
            return 'liste-leer'
        if all(_looks_like_int(t) for t in parts):
            return f'ganzzahl-liste[{len(parts)}]'
        try:
            for t in parts:
                float(t)
            return f'komma-liste[{len(parts)}]'
        except ValueError:
            return f'text-liste[{len(parts)}]'
    if _looks_like_int(v):
        return 'ganzzahl'
    try:
        float(v)
        return 'kommazahl'
    except ValueError:
        return 'text'


def datei_atomar(pfad, daten):
    """
    Schreibt eine Datei so, dass sie nie halb geschrieben dasteht: erst in
    eine Nachbardatei, dann in einem Schritt an ihren Platz. Bricht der
    Rechner mitten im Schreiben ab, bleibt die alte Fassung stehen.
    daten: bytes oder str (wird als UTF-8 geschrieben)
    """
    if isinstance(daten, str):
        daten = daten.encode("utf-8")
    ordner = os.path.dirname(os.path.abspath(pfad))
    fd, tmp = tempfile.mkstemp(prefix=".purelapse_", suffix=".tmp", dir=ordner)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(daten)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(tmp, os.stat(pfad).st_mode & 0o7777)
        except OSError:
            os.chmod(tmp, 0o644)
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def xml_atomar(tree, pfad):
    """Schreibt eine XMP/XML-Datei ueber datei_atomar."""
    import io
    puffer = io.BytesIO()
    tree.write(puffer, encoding='UTF-8', xml_declaration=True)
    datei_atomar(pfad, puffer.getvalue())


def interp_value(v_s, v_e, ratio):
    """Interpoliert einen einzelnen Profil-Parameter (Zahl, Zahlenliste oder Text)."""
    if v_s == v_e:
        return v_s
    if ';' in v_s and ';' in v_e:
        parts_s = [t for t in v_s.split(';') if t.strip()]
        parts_e = [t for t in v_e.split(';') if t.strip()]
        if len(parts_s) == len(parts_e):
            out = []
            for ps, pe in zip(parts_s, parts_e):
                try:
                    v_c = float(ps) + (float(pe) - float(ps)) * ratio
                except ValueError:
                    out.append(ps if ratio < 0.5 else pe)
                    continue
                if _looks_like_int(ps) and _looks_like_int(pe):
                    out.append(str(int(round(v_c))))
                else:
                    out.append(f"{v_c:.4f}")
            return ";".join(out) + ";"
    try:
        v_c = float(v_s) + (float(v_e) - float(v_s)) * ratio
    except ValueError:
        return v_s if ratio < 0.5 else v_e
    if _looks_like_int(v_s) and _looks_like_int(v_e):
        return str(int(round(v_c)))
    return f"{v_c:.4f}"


def ordered_union(first, second):
    out = list(first)
    seen = set(first)
    out.extend(k for k in second if k not in seen)
    return out


# ==========================================================================
#  TEIL A: ART / RAWTHERAPEE  (INI-Format)
# ==========================================================================
def read_arp_dict_ini(arp_path):
    data = {}
    if not os.path.exists(arp_path):
        return data
    curr_sec = None
    try:
        with open(arp_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    sec_name = line
                    if '][' in sec_name:
                        sec_name = '[' + sec_name.split('][')[-1]
                    curr_sec = sec_name[1:-1]
                    if curr_sec not in data:
                        data[curr_sec] = {}
                elif '=' in line and curr_sec:
                    k, v = line.split('=', 1)
                    data[curr_sec][k.strip()] = v.strip()
    except Exception:
        pass
    return data


def write_arp_dict_ini(arp_path, data):
    try:
        order = list(data.keys())
        if 'Version' in data:
            order = ['Version'] + [s for s in order if s != 'Version']
        zeilen = []
        for sec in order:
            zeilen.append(f"[{sec}]\n")
            for k, v in data[sec].items():
                zeilen.append(f"{k}={v}\n")
        datei_atomar(arp_path, "".join(zeilen))
    except OSError as e:
        # Frueher nur eine Zeile auf der Konsole: das Video wurde dann ohne
        # diese Korrektur gerendert, und niemand erfuhr davon.
        raise OSError(f"{os.path.basename(arp_path)} konnte nicht geschrieben "
                      f"werden: {e.strerror or e}") from e


def profile_is_complete(arp_data):
    """
    Ein von ART/RT geschriebenes Profil hat einen [Version]-Block und viele
    Sektionen. Ein Profil, das Purelapse selbst aus dem Nichts erzeugt hat,
    besteht nur aus [Exposure] - so eines verwirft ART beim Laden.
    Fuer Darktable liefert read_arp_dict_dt() immer einen [Version]-Block
    (Shim), das Profil gilt also als vollstaendig, sobald die XMP lesbar war.
    """
    if not arp_data:
        return False
    return 'Version' in arp_data or len(arp_data) >= 3


def strip_rank(arp_data):
    """Rank/Rating entfernen, damit kopierte Profile keine neuen Keyframes erzeugen."""
    return {sec: {k: v for k, v in params.items() if k not in ('Rank', 'Rating')}
            for sec, params in arp_data.items()}


# ==========================================================================
#  SCHNELLEINSTELLUNGEN FUER KEYFRAMES
#
#  Damit sich ein Keyframe ohne ART oder RawTherapee grundlegend anpassen
#  laesst. Die Interpolation zwischen den Keyframes uebernimmt das danach
#  wie jede andere Bearbeitung.
#
#  Die Schluesselnamen stammen aus den Quelltexten der Programme und nicht
#  aus Vermutungen:
#      ART          src/engine/procparams.cc, saveToKeyfile(...)
#      RawTherapee  rtengine/procparams.cc,   saveToKeyfile(...)
#
#  Sie unterscheiden sich erheblich. ART hat Helligkeit und Kontrast in
#  [Luminance Curve] und die Saettigung in [Saturation]; RawTherapee hat
#  alle drei in [Exposure]. Ein geratener Schluessel wuerde von der Engine
#  stillschweigend ignoriert - genau die Fehlerart, die man nicht sieht.
#
#  Die Belichtungskorrektur ist mit Absicht NICHT dabei: die gehoert dem
#  Deflicker. Was hier "Helligkeit" heisst, ist der Tonwert-Regler, der
#  neben der Belichtung sitzt und ihr nicht in die Arbeit faellt.
#
#  Felder je Regler: Sektion, Schluessel, Minimum, Maximum, Neutralwert,
#  wahlweise Faktor und weitere Schluessel. Minimum und Maximum gelten fuer
#  den Reglerwert; wo der Bereich der Engine fuer einen Schieberegler
#  unbrauchbar weit ist (Gruenabgleich bis 100), steht in QUICK_CONTROLS
#  ein engerer Bereich fuer die Bedienung.
#
#  Faktor: in die Datei kommt Reglerwert x Faktor. Damit bedeutet
#  "Tiefen aufhellen 40" in allen drei Engines ungefaehr dasselbe, obwohl
#  ihre Werkzeuge verschieden stark zupacken.
#  Weitere Schluessel: ((Schluessel, Faktor), ...) in derselben Sektion,
#  fuer Werkzeuge, bei denen ein Regler mehrere Werte braucht - etwa die
#  Baender des Tonwert-Equalizers.
# ==========================================================================
QUICK_CONTROLS = [
    dict(id='wb_temp',    de="Farbtemperatur",  en="Colour temperature",
         einheit=" K",  dezimal=0, ui_min=2000,  ui_max=12000, schritt=50),
    dict(id='wb_green',   de="Gruenabgleich",   en="Green balance",
         einheit="",    dezimal=3, ui_min=0.6,   ui_max=1.8,   schritt=0.005),
    dict(id='brightness', de="Helligkeit",      en="Brightness",
         einheit="",    dezimal=0, ui_min=-100,  ui_max=100,   schritt=1),
    dict(id='contrast',   de="Kontrast",        en="Contrast",
         einheit="",    dezimal=0, ui_min=-100,  ui_max=100,   schritt=1),
    dict(id='highlights', de="Lichter abdunkeln", en="Recover highlights",
         einheit="",    dezimal=0, ui_min=0,     ui_max=100,   schritt=1),
    dict(id='shadows',    de="Tiefen aufhellen", en="Lift shadows",
         einheit="",    dezimal=0, ui_min=0,     ui_max=100,   schritt=1),
    dict(id='vibrance',   de="Dynamik",         en="Vibrance",
         einheit="",    dezimal=0, ui_min=-100,  ui_max=100,   schritt=1),
    dict(id='saturation', de="Saettigung",      en="Saturation",
         einheit="",    dezimal=0, ui_min=-100,  ui_max=100,   schritt=1),
    dict(id='sharpen',    de="Schaerfe",        en="Sharpening",
         einheit="",    dezimal=0, ui_min=1,     ui_max=1000,  schritt=5),
    dict(id='denoise_l',  de="Entrauschen Helligkeit", en="Denoise luminance",
         einheit="",    dezimal=0, ui_min=0,     ui_max=100,   schritt=1),
    dict(id='denoise_c',  de="Entrauschen Farbe",      en="Denoise chrominance",
         einheit="",    dezimal=0, ui_min=0,     ui_max=100,   schritt=1),
]

QUICK_KEYS = {
    'art': {
        'wb_temp':    ('White Balance',   'Temperature', 1500, 60000, 5500),
        'wb_green':   ('White Balance',   'Green',       0.02, 10.0,  1.0),
        'brightness': ('Luminance Curve', 'Brightness',  -100, 100,   0),
        'contrast':   ('Luminance Curve', 'Contrast',    -100, 100,   0),
        'saturation': ('Saturation',      'Saturation',  -100, 100,   0),
        'vibrance':   ('Saturation',      'Vibrance',    -100, 100,   0),
        # Tiefen und Lichter ueber den Tonwert-Equalizer (ART hat kein
        # eigenes Werkzeug dafuer). Fuenf Baender, gemessen in Blenden
        # unter Weiss: Band0 <= -8, Band1 -6, Band2 -4, Band3 -2, Band4 >= 0.
        # Ein Bandwert v hebt um v/100 * 3 Blenden (Band0-2 aufwaerts,
        # Band3-4 abwaerts) - src/engine/iptoneequalizer.cc, tone_eq().
        'shadows':    ('ToneEqualizer',   'Band1',       0,    100,   0,
                       0.6, (('Band0', 0.35), ('Band2', 0.2))),
        'highlights': ('ToneEqualizer',   'Band4',       0,    100,   0,
                       -0.5, (('Band3', -0.2),)),
        'sharpen':    ('Sharpening',      'Amount',      1,    1000,  200),
        'denoise_l':  ('Denoise',         'Luminance',   0,    100,   0),
        'denoise_c':  ('Denoise',         'Chrominance', 0,    100,   15),
    },
    'rt': {
        'wb_temp':    ('White Balance', 'Temperature', 1500, 60000, 5500),
        'wb_green':   ('White Balance', 'Green',       0.02, 100.0, 1.0),
        'brightness': ('Exposure',      'Brightness',  -100, 100,   0),
        'contrast':   ('Exposure',      'Contrast',    -100, 100,   0),
        'saturation': ('Exposure',      'Saturation',  -100, 100,   0),
        # Dynamik: RawTherapee trennt Pastell- und kraeftige Toene; beide
        # bekommen denselben Wert (rtengine/ipvibrance.cc).
        'vibrance':   ('Vibrance',      'Pastels',     -100, 100,   0,
                       1.0, (('Saturated', 1.0),)),
        # [Shadows & Highlights] wirkt als Gamma 4^(-Wert/100) in der
        # Maske (rtengine/ipshadowshighlights.cc) und damit weit kraeftiger
        # als der Equalizer in ART. Der Faktor bringt beide auf etwa
        # dieselbe Wirkung je Reglerstellung.
        'shadows':    ('Shadows & Highlights', 'Shadows',    0, 100,   0, 0.3),
        'highlights': ('Shadows & Highlights', 'Highlights', 0, 100,   0, 0.75),
        'sharpen':    ('Sharpening',    'Amount',      1,    1000,  200),
        'denoise_l':  ('Directional Pyramid Denoising', 'Luma',   0, 100, 0),
        'denoise_c':  ('Directional Pyramid Denoising', 'Chroma', 0, 100, 15),
    },
    # Darktable: Module statt INI-Schluessel. Sektion und Feld wie im
    # Profil-Dict (dt:op#0), Grenzen in den Einheiten der Regler; der
    # Faktor in QUICK_DT rechnet in die Werte des Moduls um. Weissabgleich
    # und Entrauschen fehlen bewusst: Darktable speichert dort
    # kameraabhaengige Werte (Kanalfaktoren, Rauschprofil), die sich ohne
    # die Farbmatrix der Kamera nicht aus Kelvin bzw. einer Staerke
    # berechnen lassen.
    'dt': {
        'brightness': ('dt:colorbalancergb#0', 'brilliance_global', -100, 100, 0),
        'contrast':   ('dt:colorbalancergb#0', 'contrast',          -100, 100, 0),
        'saturation': ('dt:colorbalancergb#0', 'saturation_global', -100, 100, 0),
        'vibrance':   ('dt:colorbalancergb#0', 'vibrance',          -100, 100, 0),
        # Modul "Schatten und Lichter" (shadhi): Tiefen positiv hellen auf,
        # Lichter negativ dunkeln ab.
        'shadows':    ('dt:shadhi#0',          'shadows',           0,    100, 0),
        'highlights': ('dt:shadhi#0',          'highlights',        0,    100, 0),
        'sharpen':    ('dt:sharpen#0',         'amount',            1,    800, 200),
    },
    # Lightroom: Werte von crs (Entwicklungsmodul "Grundeinstellungen").
    # Helligkeit gibt es dort nicht getrennt von der Belichtung (die
    # gehoert dem Deflicker), und der Gruenabgleich heisst "Tonung" mit
    # eigener Skala - beide fehlen hier.
    # Lichter: 0..100 abdunkeln = Highlights2012 0..-100.
    # Schaerfe: Purelapse 200 = Lightroom 40 (dessen Grundwert).
    'lr': {
        'wb_temp':    ('crs', 'Temperature',         2000, 50000, 5500),
        'contrast':   ('crs', 'Contrast2012',        -100, 100,   0),
        'highlights': ('crs', 'Highlights2012',      0,    100,   0, -1.0),
        'shadows':    ('crs', 'Shadows2012',         0,    100,   0),
        'vibrance':   ('crs', 'Vibrance',            -100, 100,   0),
        'saturation': ('crs', 'Saturation',          -100, 100,   0),
        'sharpen':    ('crs', 'Sharpness',           1,    750,   200, 0.2),
        'denoise_l':  ('crs', 'LuminanceSmoothing',  0,    100,   0),
        'denoise_c':  ('crs', 'ColorNoiseReduction', 0,    100,   25),
    },
}
# Regler -> Modulwert: Prozent wie in Darktables Oberflaeche; die Schaerfe
# so, dass 200 (Grundwert von ART/RawTherapee) Darktables 0,5 entspricht.
# Tiefen und Lichter mit 0,6: Darktables Grundwerte +50/-50 sind schon
# eine kraeftige Aufhellung; Purelapse 100 entspricht dort 60.
QUICK_DT = {'brightness': 0.01, 'contrast': 0.01, 'saturation': 0.01,
            'vibrance': 0.01, 'sharpen': 1.0 / 400.0,
            'shadows': 0.6, 'highlights': -0.6}


# ==========================================================================
#  LICHTER-REKONSTRUKTION
#
#  Warum der Sonnenball rosa wird: Im Kern der Sonne laufen alle drei
#  Kanaele des Sensors an. Sie laufen aber nicht gleichzeitig an - Gruen
#  ist am empfindlichsten und steht zuerst am Anschlag. Danach werden die
#  Rohwerte mit den Faktoren des Weissabgleichs multipliziert, und zwar
#  mit drei VERSCHIEDENEN. Rot und Blau kommen dadurch hoeher heraus als
#  das bereits festsitzende Gruen, und aus Weiss wird Magenta.
#
#  Eine negative Belichtungskorrektur hilft dagegen nicht: was am
#  Anschlag stand, steht dort immer noch, es wird nur dunkler. Die
#  Rekonstruktion schaetzt stattdessen den fehlenden Kanal aus seiner
#  Umgebung und den unbeschaedigten Kanaelen.
#
#  Schluessel, aus den Quelltexten entnommen:
#    ART           [Exposure] HLRecovery = Off|Blend|Color|Balanced
#                  (src/engine/procparams.cc, ExposureParams)
#    RawTherapee   [HLRecovery] Enabled + Method
#                  = Luminance|CIELab|Blend|Color|Coloropp
#                  (rtengine/procparams.cc, ToneCurveParams)
# ==========================================================================
HL_OPTIONEN = {
    'art': [("Off", "aus", "ausgeschaltet"),
            ("Blend", "Blend", "mischt die Lichter weich aus - ruhig, "
                               "verliert etwas Zeichnung"),
            ("Color", "Farbe", "rechnet den fehlenden Kanal aus den "
                               "anderen - fuer Sonne und Wolken meist "
                               "die beste Wahl"),
            ("Balanced", "Ausgewogen", "wie Farbe, nur zurueckhaltender")],
    'rt': [("Off", "aus", "ausgeschaltet"),
           ("Blend", "Blend", "mischt die Lichter weich aus - ruhig, "
                              "verliert etwas Zeichnung"),
           ("Color", "Farbe", "rechnet den fehlenden Kanal aus den anderen"),
           ("Coloropp", "Farbfortsetzung", "setzt die Farbe aus der "
                                           "Umgebung fort - fuer einen "
                                           "Sonnenball meist die beste "
                                           "Wahl")],
    'dt': [],
    'lr': [],
}
HL_EMPFOHLEN = {'art': "Color", 'rt': "Coloropp", 'dt': "", 'lr': ""}


def hl_optionen(engine=None):
    """Die waehlbaren Verfahren der aktuellen Engine."""
    return list(HL_OPTIONEN.get(engine or ENGINE, []))


def hl_empfohlen(engine=None):
    """Das Verfahren, das fuer einen ausgebrannten Sonnenball taugt."""
    return HL_EMPFOHLEN.get(engine or ENGINE, "")


def hl_verfuegbar(profil, engine=None):
    """
    Kennt das vorliegende Profil die Lichter-Rekonstruktion?

    Wie bei den uebrigen Schnelleinstellungen gilt: was die Engine nicht
    selbst in ihr Profil schreibt, schreiben wir auch nicht hinein - ein
    unbekannter Schluessel verfiele ohne Fehlermeldung.
    """
    e = engine or ENGINE
    if not HL_OPTIONEN.get(e):
        return False
    if e == 'rt':
        return 'HLRecovery' in (profil or {})
    return 'HLRecovery' in (profil or {}).get('Exposure', {})


def hl_lesen(profil, engine=None):
    """Welches Verfahren steht im Profil? 'Off', wenn keines."""
    e = engine or ENGINE
    p = profil or {}
    if e == 'rt':
        sek = p.get('HLRecovery', {})
        if str(sek.get('Enabled', 'false')).strip().lower() != 'true':
            return "Off"
        return str(sek.get('Method', 'Coloropp')).strip() or "Off"
    return str(p.get('Exposure', {}).get('HLRecovery', 'Off')).strip() or "Off"


def hl_schreiben(profil, wert, engine=None):
    """
    Traegt das Verfahren in das Profil ein.

    Rueckgabe: Liste der geschriebenen (Sektion, Schluessel, Wert).
    """
    e = engine or ENGINE
    wert = str(wert or "Off").strip()
    geschrieben = []
    if e == 'rt':
        sek = profil.setdefault('HLRecovery', {})
        if wert == "Off":
            sek['Enabled'] = "false"
            geschrieben.append(('HLRecovery', 'Enabled', "false"))
        else:
            sek['Enabled'] = "true"
            sek['Method'] = wert
            geschrieben.append(('HLRecovery', 'Enabled', "true"))
            geschrieben.append(('HLRecovery', 'Method', wert))
        return geschrieben
    if e == 'art':
        exp = profil.setdefault('Exposure', {})
        exp['HLRecovery'] = wert
        geschrieben.append(('Exposure', 'HLRecovery', wert))
    return geschrieben


def quick_defs(engine=None):
    """Alle Schnelleinstellungen, die die Engine grundsaetzlich kennt."""
    e = engine or ENGINE
    tabelle = QUICK_KEYS.get(e, {})
    out = []
    for c in QUICK_CONTROLS:
        eintrag = tabelle.get(c['id'])
        if not eintrag:
            continue
        d = dict(c)
        d['sec'], d['key'], d['min'], d['max'], d['neutral'] = eintrag[:5]
        d['faktor'] = float(eintrag[5]) if len(eintrag) > 5 else 1.0
        d['mehr'] = tuple(eintrag[6]) if len(eintrag) > 6 else ()
        out.append(d)
    return out


def quick_available(profile, engine=None):
    """
    Trennt die Regler danach, ob das vorliegende Profil ihre Sektion
    ueberhaupt enthaelt.

    Ein Schluessel in einer Sektion, die die Engine nicht schreibt, waere
    wirkungslos, ohne dass jemand eine Fehlermeldung bekommt. Solche Regler
    werden gesperrt statt stillschweigend ins Leere zu schreiben.
    """
    vorhanden, fehlend = [], []
    for d in quick_defs(engine):
        if (engine or ENGINE) == 'dt':
            # Fehlende Module legt Purelapse selbst an - mit Darktables
            # Grundwerten, also ohne Wirkung, solange der Regler nicht bewegt wird.
            (vorhanden if DT_STAPEL in (profile or {}) else fehlend).append(d)
            continue
        (vorhanden if d['sec'] in (profile or {}) else fehlend).append(d)
    return vorhanden, fehlend


def quick_read(profile, engine=None):
    """Aktuelle Werte der Schnelleinstellungen aus einem Profil."""
    werte = {}
    for d in quick_defs(engine):
        roh = (profile or {}).get(d['sec'], {}).get(d['key'])
        if (engine or ENGINE) == 'dt':
            sek = (profile or {}).get(d['sec'], {})
            try:
                if roh is None or sek.get('~enabled') != '1':
                    raise ValueError
                werte[d['id']] = float(roh) / QUICK_DT[d['id']]
            except (TypeError, ValueError):
                werte[d['id']] = float(d['neutral'])
            continue
        try:
            # Listenwerte wie "512;0;0;0" -> erster Eintrag
            werte[d['id']] = (float(str(roh).split(';')[0].strip())
                              / d.get('faktor', 1.0))
        except (TypeError, ValueError, ZeroDivisionError):
            werte[d['id']] = float(d['neutral'])
    return werte


def quick_apply(profile, werte, engine=None):
    """
    Schreibt die uebergebenen Schnelleinstellungen in ein Profil-Dict.

    werte: {id: Zahl}. Nur die enthaltenen Regler werden angefasst, alles
    uebrige im Profil bleibt unberuehrt - ein Keyframe, der in ART schon
    bearbeitet wurde, verliert dadurch nichts.

    'Enabled' wird nur gesetzt, wenn die Sektion diesen Schluessel bereits
    fuehrt. ART braucht ihn, RawTherapee kennt ihn in [Exposure] nicht, und
    einen erfundenen Schluessel wuerde die Profilpruefung zu Recht
    anmahnen.

    Rueckgabe: Liste der geschriebenen (Sektion, Schluessel, Wert).
    """
    e = engine or ENGINE
    geschrieben = []
    wb_beruehrt = False
    for d in quick_defs(e):
        if d['id'] not in werte:
            continue
        try:
            v = float(werte[d['id']])
        except (TypeError, ValueError):
            continue
        v = max(float(d['min']), min(float(d['max']), v))
        if e == 'dt':
            op = d['sec'][len(DT_SEK):].partition('#')[0]
            if dt_modul_setzen(profile, op, {d['key']: v * QUICK_DT[d['id']]}):
                geschrieben.append((d['sec'], d['key'], profile[d['sec']][d['key']]))
            continue
        sek = profile.setdefault(d['sec'], {})
        if e == 'lr':
            for key, f in ((d['key'], d.get('faktor', 1.0)),) + tuple(d.get('mehr', ())):
                sek[key] = lr_zahl_text(key, v * float(f), sek.get(key))
                geschrieben.append((d['sec'], key, sek[key]))
            if d['key'] in LR_WB:
                sek['WhiteBalance'] = "Custom"
                geschrieben.append((d['sec'], 'WhiteBalance', "Custom"))
            continue
        if 'Enabled' in sek:
            sek['Enabled'] = "true"
        for key, f in ((d['key'], d.get('faktor', 1.0)),) + tuple(d.get('mehr', ())):
            w = v * float(f)
            sek[key] = (str(int(round(w))) if d['dezimal'] == 0
                        else f"{w:.{d['dezimal']}f}")
            geschrieben.append((d['sec'], key, sek[key]))
        if d['sec'] == 'White Balance':
            wb_beruehrt = True
    if wb_beruehrt:
        name = ENGINES.get(e, {}).get('wb_custom', "")
        if name:
            profile.setdefault('White Balance', {})['Setting'] = name
            geschrieben.append(('White Balance', 'Setting', name))
    return geschrieben


# ==========================================================================
#  BILDWEISE AUTOMATIK EINFRIEREN
#
#  ART und RawTherapee kennen Funktionen, die fuer JEDES Bild neu rechnen.
#  Im Einzelbild ist das erwuenscht, im Zeitraffer ist es Flackern:
#
#  - "Auto-angepasste Tonkurve" (HistogramMatching): die Engine gleicht
#    jedes RAW an sein eingebettetes Kamera-JPEG an und baut daraus eine
#    eigene Tonkurve - Bild fuer Bild eine andere
#    (simpleprocess.cc: getAutoMatchedToneCurve). Es ist die Voreinstellung
#    beider Programme fuer RAW-Dateien. Wer ein Keyframe im Programm selbst
#    oeffnet, bekommt die Kurve dort einmal berechnet und festgeschrieben
#    (CurveFromHistogramMatching=true); ein Profil, das nie in der
#    Oberflaeche war, laesst sie bei jedem Bild neu entstehen.
#    RawTherapee setzt in diesem Modus obendrein Helligkeit und Kontrast
#    auf null - die Schnelleinstellungen blieben wirkungslos.
#  - ART "Log Tone Mapping" mit Auto: Graupunkt und Umfang je Bild.
#
#  Fuer den Zeitraffer wird beides auf feste Werte gestellt.
# ==========================================================================
FILMKURVE = {
    # ART: data/profiles/Standard Film Curve.arp
    'art': ('ToneCurve', "1;0;0;0.11;0.09;0.32;0.47;0.66;0.87;1;1;", "Neutral"),
    # RawTherapee: Standard Film Curve - ISO Low.pp3
    'rt':  ('Exposure',  "1;0;0;0.11;0.09;0.32;0.43;0.66;0.87;1;1;", "FilmLike"),
}


def _ist_wahr(wert):
    return str(wert).strip().lower() == 'true'


def kurve_ist_leer(wert):
    """ "0;" ist die lineare Kurve, also keine."""
    teile = [t for t in str(wert or "").split(';') if t.strip()]
    return len(teile) <= 1


def automatik_finden(profil, engine=None):
    """
    Welche bildweise rechnenden Funktionen sind in diesem Profil aktiv?

    Rueckgabe: Liste aus 'tonkurve' (Kurve entsteht je Bild neu),
    'tonkurve_fest' (nur RawTherapee: Kurve steht fest, der Modus sperrt
    aber Helligkeit und Kontrast) und 'log'.
    """
    e = engine or ENGINE
    p = profil or {}
    gefunden = []
    if e in FILMKURVE:
        sek = p.get(FILMKURVE[e][0])
        if sek is not None:
            hm = sek.get('HistogramMatching')
            fest = _ist_wahr(sek.get('CurveFromHistogramMatching', 'false'))
            # RawTherapee laeuft mit "-d": fehlt der Schluessel, gilt das
            # Standardprofil, und dort ist die Automatik eingeschaltet.
            an = _ist_wahr(hm) or (e == 'rt' and hm is None)
            if e == 'art' and 'Enabled' in sek and not _ist_wahr(sek['Enabled']):
                an = False
            if an and not fest:
                gefunden.append('tonkurve')
            elif an and fest and e == 'rt':
                gefunden.append('tonkurve_fest')
    if e == 'art':
        log = p.get('LogEncoding', {})
        if _ist_wahr(log.get('Enabled', 'false')) and _ist_wahr(log.get('Auto', 'false')):
            gefunden.append('log')
    return gefunden


def automatik_einfrieren(profil, engine=None):
    """
    Stellt die bildweise Automatik im Profil auf feste Werte.

    Ein unvollstaendiges Profil bleibt unberuehrt. Rueckgabe wie
    automatik_finden(): was geaendert wurde.
    """
    e = engine or ENGINE
    if not profile_is_complete(profil):
        return []
    gefunden = automatik_finden(profil, e)
    if 'tonkurve' in gefunden or 'tonkurve_fest' in gefunden:
        name, kurve, modus = FILMKURVE[e]
        sek = profil[name]
        sek['HistogramMatching'] = "false"
        if 'tonkurve' in gefunden:
            sek['CurveFromHistogramMatching'] = "false"
            if kurve_ist_leer(sek.get('Curve')):
                sek['Curve'] = kurve
                if e == 'rt' or 'CurveMode' not in sek:
                    sek['CurveMode'] = modus
        else:
            # RawTherapee rechnet eine festgeschriebene Auto-Kurve immer
            # im Modus "FilmLike" und ohne zweite Kurve; so bleibt das
            # Bild gleich, nur Helligkeit und Kontrast greifen wieder.
            sek['CurveFromHistogramMatching'] = "false"
            sek['CurveMode'] = "FilmLike"
            sek['Curve2'] = "0;"
    if 'log' in gefunden:
        profil['LogEncoding']['Auto'] = "false"
    return gefunden


def nicht_ueberblendbar(start_arp, end_arp):
    """
    Werte, die zwischen zwei Keyframes nicht weich ueberblendet werden
    koennen (Text, Kurven mit verschieden vielen Punkten). interp_value()
    schaltet sie in der Mitte hart um - das sieht man als Sprung.
    """
    harte = []
    for sec in ordered_union(start_arp, end_arp):
        s_dict = start_arp.get(sec, {})
        e_dict = end_arp.get(sec, {})
        if dt_ist_sektion(sec):
            # Darktable-Modul: was dt_sektion_mischen() nicht weich kann.
            # Die Belichtung selbst gehoert dem Deflicker.
            _, hart = dt_sektion_mischen(sec, s_dict, e_dict, 0.0)
            haupt = (start_arp.get(DT_STAPEL) or end_arp.get(DT_STAPEL) or {}).get('haupt')
            if sec == haupt:
                hart = [h for h in hart if h not in ('mode', 'ein/aus')]
            harte.extend((dt_modulname(sec, s_dict or e_dict), h) for h in hart)
            continue
        if lr_ist_sektion(sec):
            _, hart = lr_sektion_mischen(sec, s_dict, e_dict, 0.0)
            harte.extend((sec, h) for h in hart)
            continue
        for k in ordered_union(s_dict, e_dict):
            if k in ('Rank', 'Rating', 'Enabled'):
                continue
            if sec == 'Exposure' and k in ('Compensation', 'Auto'):
                continue
            if sec == 'White Balance' and k == 'Setting':
                continue
            v_s = s_dict.get(k, e_dict.get(k))
            v_e = e_dict.get(k, s_dict.get(k))
            if v_s == v_e:
                continue
            if ';' in v_s and ';' in v_e:
                t_s = [t for t in v_s.split(';') if t.strip()]
                t_e = [t for t in v_e.split(';') if t.strip()]
                if len(t_s) == len(t_e):
                    try:
                        [float(t) for t in t_s + t_e]
                        continue
                    except ValueError:
                        pass
                harte.append((sec, k))
                continue
            try:
                float(v_s), float(v_e)
            except ValueError:
                harte.append((sec, k))
    return harte


# ==========================================================================
#  ECHTE VORSCHAU
#
#  Wie ein Bild am Ende aussieht, weiss nur die Engine. Die Vorschau der
#  Schnelleinstellungen laesst deshalb die Engine selbst entwickeln: mit
#  genau dem Profil, das beim Speichern geschrieben wuerde, nur kleiner.
# ==========================================================================
def schnell_profil(profil, werte, hl=None, engine=None):
    """
    Das Profil, das die Schnelleinstellungen ergeben - als Kopie.

    Speichern und Vorschau gehen beide hier durch. Nur so ist sicher, dass
    die Vorschau zeigt, was spaeter im Profil steht.

    werte   {id: Zahl} der angekreuzten Regler
    hl      Verfahren der Lichter-Rekonstruktion; None laesst es, wie es ist
    Rueckgabe: (profil_neu, geschrieben, eingefroren)
    """
    e = engine or ENGINE
    neu = {sec: dict(par) for sec, par in (profil or {}).items()}
    geschrieben = quick_apply(
        neu, {k: v for k, v in (werte or {}).items() if not str(k).startswith('_')}, e)
    if hl is not None and hl != hl_lesen(neu, e):
        geschrieben += hl_schreiben(neu, hl, e)
    eingefroren = automatik_einfrieren(neu, e)
    return neu, geschrieben, eingefroren


def vorschau_profil(profil, kante):
    """Kopie des Profils, die die Engine auf hoechstens 'kante' Pixel
    Kantenlaenge ausgeben laesst. Alles andere bleibt, wie es ist."""
    neu = {sec: dict(par) for sec, par in (profil or {}).items()}
    gr = neu.setdefault('Resize', {})
    gr['Enabled'] = "true"
    gr['DataSpecified'] = "3"            # in ein Rechteck einpassen
    gr['Width'] = str(int(kante))
    gr['Height'] = str(int(kante))
    gr['AllowUpscaling'] = "false"
    return neu


def vorschau_befehl(cli, bild, profil_pfad, ziel_jpg, engine=None):
    """
    Aufruf, mit dem die Engine EIN Bild mit einem bestimmten Profil
    entwickelt. Entspricht dem Aufruf in Pass 2 - nur dass das Profil
    ueber "-p" kommt statt aus der Begleitdatei, damit die nicht
    angefasst werden muss.
    """
    e = engine or ENGINE
    return ([cli, "-o", ziel_jpg, "-p", profil_pfad, "-Y", "-j92"]
            + list(ENGINES.get(e, {}).get('extra', [])) + ["-c", bild])


def profil_kennung(profil):
    """Fingerabdruck eines Profil-Dicts, fuer den Zwischenspeicher."""
    import hashlib
    h = hashlib.sha1()
    for sec in profil:
        h.update(f"[{sec}]".encode("utf-8"))
        for k, v in profil[sec].items():
            h.update(f"{k}={v};".encode("utf-8"))
    return h.hexdigest()


def set_exposure(arp_data, ev_value):
    """Setzt die Belichtungskorrektur im Profil-Dict. Gilt fuer ALLE Engines
    identisch, weil read_arp_dict_dt() dieselbe Dict-Form liefert wie ART/RT."""
    exp = arp_data.setdefault('Exposure', {})
    exp['Enabled'] = "true"
    exp['Auto'] = "false"
    exp['Compensation'] = f"{ev_value:.3f}"


def interpolate_arp_dicts(start_arp, end_arp, ratio):
    """Interpoliert zwei vollstaendige Profile. Engine-unabhaengig."""
    out = {}
    for sec in ordered_union(start_arp, end_arp):
        s_dict = start_arp.get(sec, {})
        e_dict = end_arp.get(sec, {})
        if dt_ist_sektion(sec):
            gemischt, _ = dt_sektion_mischen(sec, s_dict, e_dict, ratio)
            if gemischt is not None:
                out[sec] = gemischt
            continue
        if lr_ist_sektion(sec):
            out[sec], _ = lr_sektion_mischen(sec, s_dict, e_dict, ratio)
            continue
        force_custom = False
        if sec == 'White Balance':
            force_custom = any(s_dict.get(k) != e_dict.get(k)
                               for k in ('Temperature', 'Green', 'Multipliers'))
        params = {}
        for k in ordered_union(s_dict, e_dict):
            if k in ('Rank', 'Rating'):
                continue
            if sec == 'Exposure' and k in ('Compensation', 'Auto'):
                continue
            v_s = s_dict.get(k, e_dict.get(k))
            v_e = e_dict.get(k, s_dict.get(k))
            if sec == 'White Balance' and k == 'Setting':
                # ART erwartet "CustomTemp", RawTherapee "Custom" - ein
                # fester Wert waere bei einer der beiden Engines falsch
                # und der Weissabgleich fiele still auf die Kamera zurueck.
                params[k] = (eng('wb_custom') or v_s) if force_custom else v_s
            elif k == 'Enabled':
                params[k] = 'true' if 'true' in (str(v_s).lower(), str(v_e).lower()) else 'false'
            else:
                params[k] = interp_value(v_s, v_e, ratio)
        out[sec] = params
    return out


def set_raw_hotpixel(arp_data, enabled):
    """Schaltet die Defektpixel-Korrektur im Profil. Bei Darktable ueber
    das Modul "Hotpixel" (wird bei Bedarf angelegt). Ausschalten laesst ein
    vom Nutzer selbst eingeschaltetes Modul in Ruhe."""
    if ENGINE == 'dt':
        if enabled and DT_STAPEL in arp_data:
            dt_modul_setzen(arp_data, 'hotpixels', {}, an=True)
        return
    if ENGINE == 'lr':
        return      # Lightroom entfernt Hotpixel selbst, ohne Einstellung
    raw = arp_data.setdefault('RAW', {})
    raw['HotDeadPixelEnabled'] = "true" if enabled else "false"
    raw['HotPixelFilter'] = "true" if enabled else "false"
    raw['DeadPixelFilter'] = "true" if enabled else "false"
    raw.setdefault('HotDeadPixelThresh', "100")


def validate_arp(profile, reference, name, lang='de'):
    """Prueft ein geschriebenes Profil gegen ein von ART/RT stammendes Vorbild.
    Fuer Darktable nicht sinnvoll - liefert dann einfach eine leere Liste.
    Die Befunde stehen in der Sprache der Oberflaeche (lang)."""
    if ENGINE in ('dt', 'lr'):
        return []
    en = (lang == 'en')
    issues = []
    if not profile:
        return [f"{name}: profile is empty or unreadable" if en
                else f"{name}: Profil ist leer oder nicht lesbar"]
    secs = list(profile.keys())
    if 'Version' not in secs:
        issues.append(f"{name}: [Version] missing - {eng('label')} discards the profile" if en
                      else f"{name}: [Version] fehlt - {eng('label')} verwirft das Profil")
    elif secs[0] != 'Version':
        pos = secs.index('Version') + 1
        issues.append(f"{name}: [Version] is at position {pos} instead of first" if en
                      else f"{name}: [Version] steht an Position {pos} statt an erster Stelle")
    for sec in reference:
        if sec not in profile:
            issues.append(f"{name}: section [{sec}] missing" if en
                          else f"{name}: Sektion [{sec}] fehlt")
    for sec in profile:
        if sec not in reference:
            issues.append(f"{name}: section [{sec}] is extra" if en
                          else f"{name}: Sektion [{sec}] ist zusaetzlich vorhanden")
    ref_order = [s for s in reference if s in profile]
    own_order = [s for s in profile if s in reference]
    if ref_order != own_order:
        issues.append(f"{name}: section order differs from the template" if en
                      else f"{name}: Sektionsreihenfolge weicht von der Vorlage ab")
    eigene = {('Exposure', 'Compensation'), ('Exposure', 'Auto'),
              ('Exposure', 'Enabled'),
              ('RAW', 'HotDeadPixelEnabled'), ('RAW', 'HotPixelFilter'),
              ('RAW', 'DeadPixelFilter'), ('RAW', 'HotDeadPixelThresh'),
              ('White Balance', 'Setting')}
    for sec, ref_params in reference.items():
        own = profile.get(sec, {})
        for k, ref_v in ref_params.items():
            if k in ('Rank', 'Rating') or (sec, k) in eigene:
                continue
            if k not in own:
                issues.append(f"{name}: [{sec}] {k} missing" if en
                              else f"{name}: [{sec}] {k} fehlt")
                continue
            want, got = _value_kind(ref_v), _value_kind(own[k])
            if want != got:
                wert = str(own[k])[:40]
                issues.append(f"{name}: [{sec}] {k} is '{got}' instead of '{want}' (value '{wert}')"
                              if en else
                              f"{name}: [{sec}] {k} ist '{got}' statt '{want}' (Wert '{wert}')")
    return issues


def find_arp_template_ini(target_dir, files=None):
    """
    Sucht ein gueltiges ART/RT-Basisprofil.
    1. ein vollstaendiges Profil im Bilderordner (von der Engine selbst geschrieben)
    2. die vom Benutzer hinterlegte Vorlagendatei
    Rueckgabe: (profil_dict, herkunftspfad) oder (None, "").
    """
    candidates = []
    if files:
        candidates += [sidecar(f) for f in files]
    candidates += sorted(glob.glob(os.path.join(target_dir, '*' + eng('ext'))))
    seen = set()
    for path in candidates:
        if path in seen or not os.path.exists(path):
            continue
        seen.add(path)
        data = read_arp_dict_ini(path)
        if profile_is_complete(data):
            return strip_rank(data), path
    tpl = get_arp_template_path()
    if tpl and os.path.exists(tpl):
        data = read_arp_dict_ini(tpl)
        if profile_is_complete(data):
            return strip_rank(data), tpl
    return None, ""


def bootstrap_arp_template_ini(art_cli_path, sample_image):
    """Laesst ART-cli/rawtherapee-cli einmalig sein Standardprofil erzeugen."""
    if not engine_vorhanden(art_cli_path):
        return None, ""
    if not sample_image or not os.path.isfile(sample_image):
        return None, ""
    tmp = tempfile.mkdtemp(prefix="purelapse_tpl_")
    try:
        for args in (["-O", tmp], ["-o", tmp]):
            cmd = engine_befehl([art_cli_path] + args + ["-Y", "-j80"] + eng('extra')
                                + ["-c", sample_image])
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=300, **OHNE_FENSTER)
            except (OSError, subprocess.SubprocessError):
                continue
            found = sorted(glob.glob(os.path.join(tmp, '*' + eng('ext'))) +
                           glob.glob(os.path.join(tmp, "*.pp3")))
            for path in found:
                data = strip_rank(read_arp_dict_ini(path))
                if profile_is_complete(data):
                    ziel = basis_profil_pfad()
                    os.makedirs(os.path.dirname(ziel), exist_ok=True)
                    write_arp_dict_ini(ziel, data)
                    save_arp_template_path(ziel)
                    return data, ziel
        return None, ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_is_keyframe(arp_path):
    """
    Ein Bild gilt als Keyframe, wenn es 5 Sterne (Rating) traegt.
    Funktioniert unveraendert fuer alle drei Engines.
    """
    # Die Endung JEDER Engine abschneiden, nicht nur .arp - sonst wird bei
    # RawTherapee nach "BILD.NEF.pp3.xmp" gesucht.
    img_path = arp_path
    for _cfg in ENGINES.values():
        if _cfg['ext'] != '.xmp' and arp_path.lower().endswith(_cfg['ext']):
            img_path = arp_path[:-len(_cfg['ext'])]
            break
    base_path = os.path.splitext(img_path)[0]
    for xp in (f"{img_path}.xmp", f"{img_path}.XMP",
               f"{base_path}.xmp", f"{base_path}.XMP"):
        if not os.path.exists(xp):
            continue
        try:
            with open(xp, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except OSError:
            continue
        if 'Rating="5"' in content or '<xmp:Rating>5</xmp:Rating>' in content:
            return True
        if 'Rating="0"' in content or '<xmp:Rating>0</xmp:Rating>' in content:
            return False
    if ENGINE not in ('dt', 'lr') and os.path.exists(arp_path):
        for keys in read_arp_dict_ini(arp_path).values():
            if keys.get('Rank') == '5' or keys.get('Rating') == '5':
                return True
    return False


# ==========================================================================
#  TEIL B: DARKTABLE  (XML/History-Stack-Format)
# ==========================================================================
_RDF = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
_DT = 'http://darktable.sf.net/'
ET.register_namespace('rdf', _RDF)
ET.register_namespace('darktable', _DT)


def _qn(ns, tag):
    return f'{{{ns}}}{tag}'


# dt_iop_exposure_params_t, modversion 6:
#   mode:int32, black:float, exposure:float,
#   deflicker_percentile:float, deflicker_target_level:float,
#   compensate_exposure_bias:int32
_EXPOSURE_V6 = struct.Struct('<i f f f f i')
_EXPOSURE_V6_FIELDS = ('mode', 'black', 'exposure',
                        'deflicker_percentile', 'deflicker_target_level',
                        'compensate_exposure_bias')
# darktable 5: dazu compensate_hilite_pres (gboolean)
_EXPOSURE_V7 = struct.Struct('<i f f f f i i')
_EXPOSURE_V7_FIELDS = _EXPOSURE_V6_FIELDS + ('compensate_hilite_pres',)
_EXPOSURE_LAYOUT = {6: (_EXPOSURE_V6, _EXPOSURE_V6_FIELDS),
                    7: (_EXPOSURE_V7, _EXPOSURE_V7_FIELDS)}
_DT_NEUTRAL_BLEND = "gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU="
_DT_OWN_MULTI_NAME = "purelapse deflicker"
_KNOWN_EXPOSURE_VERSIONS = tuple(_EXPOSURE_LAYOUT)


def _dt_decode_exposure(hex_str, modversion):
    if modversion not in _KNOWN_EXPOSURE_VERSIONS:
        return None
    struktur, namen = _EXPOSURE_LAYOUT[modversion]
    raw = dt_params_lesen(hex_str)
    if raw is None or len(raw) != struktur.size:
        return None
    return dict(zip(namen, struktur.unpack(raw)))


def _dt_encode_exposure(fields, modversion=6):
    """Packt die Belichtung in genau der Version, in der sie gelesen wurde -
    so bleibt in darktable 5 auch compensate_hilite_pres, wie es war."""
    struktur, namen = _EXPOSURE_LAYOUT[modversion]
    vals = [int(fields.get(n, 0)) if n in ('mode', 'compensate_exposure_bias',
                                           'compensate_hilite_pres')
            else float(fields[n]) for n in namen]
    return struktur.pack(*vals).hex()


def _dt_load(xmp_path):
    tree = ET.parse(xmp_path)
    desc = tree.getroot().find(f'.//{_qn(_RDF, "Description")}')
    if desc is None:
        raise ET.ParseError(f"Kein rdf:Description in {xmp_path}")
    return tree, desc


def _dt_history_seq(desc):
    hist = desc.find(_qn(_DT, 'history'))
    if hist is None:
        return None
    return hist.find(_qn(_RDF, 'Seq'))


def _dt_exposure_entries(desc):
    seq = _dt_history_seq(desc)
    if seq is None:
        return []
    return [li for li in seq.findall(_qn(_RDF, 'li'))
            if li.get(_qn(_DT, 'operation')) == 'exposure']


def dt_has_custom_iop_order(desc):
    """True, wenn der Nutzer die Modul-Reihenfolge manuell veraendert hat."""
    return bool(desc.get(_qn(_DT, 'iop_order_list')))


_XMP_NS = 'http://ns.adobe.com/xap/1.0/'
# Damit beim Zurueckschreiben einer fremden XMP die ueblichen Kuerzel
# erhalten bleiben (sonst macht ElementTree "ns0:" daraus).
for _kurz, _uri in (('x', 'adobe:ns:meta/'), ('xmp', _XMP_NS),
                    ('xmpMM', 'http://ns.adobe.com/xap/1.0/mm/'),
                    ('dc', 'http://purl.org/dc/elements/1.1/'),
                    ('exif', 'http://ns.adobe.com/exif/1.0/'),
                    ('tiff', 'http://ns.adobe.com/tiff/1.0/'),
                    ('lr', 'http://ns.adobe.com/lightroom/1.0/'),
                    ('photoshop', 'http://ns.adobe.com/photoshop/1.0/')):
    ET.register_namespace(_kurz, _uri)


def bewertung_schreiben(xmp_path, sterne):
    """
    Setzt die Sternebewertung (xmp:Rating) in der .xmp eines Bildes.

    Gibt es die Datei schon - etwa von Darktable -, wird NUR die Bewertung
    darin geaendert; alles andere bleibt, wie es ist. Bisher wurde eine
    vorhandene Darktable-XMP bei ART/RawTherapee durch eine Minimaldatei
    ersetzt (die Darktable-Bearbeitung war weg), und bei Darktable ohne
    vorhandene XMP wurde gar nichts geschrieben.
    Rueckgabe: True, wenn geschrieben wurde.
    """
    wert = str(int(sterne))
    if os.path.exists(xmp_path):
        try:
            tree = ET.parse(xmp_path)
            desc = tree.getroot().find(f'.//{_qn(_RDF, "Description")}')
            if desc is not None:
                for kind in list(desc):
                    if kind.tag == _qn(_XMP_NS, 'Rating'):
                        desc.remove(kind)
                desc.set(_qn(_XMP_NS, 'Rating'), wert)
                xml_atomar(tree, xmp_path)
                return True
        except (ET.ParseError, OSError):
            pass
    inhalt = ('<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
              '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.4.0-Exiv2">\n'
              '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
              '  <rdf:Description rdf:about=""\n'
              '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
              f'    xmp:Rating="{wert}">\n'
              '  </rdf:Description>\n'
              '</rdf:RDF>\n'
              '</x:xmpmeta>\n'
              '<?xpacket end="w"?>')
    try:
        datei_atomar(xmp_path, inhalt)
        return True
    except OSError:
        return False


def dt_sidecar_bereit(xmp_path):
    """
    Kann Purelapse in diese Darktable-XMP schreiben?

    Dafuer muss Darktable sie angelegt haben: mit rdf:Description und
    einer Bearbeitungsliste (darktable:history). Fehlt die Datei, oder ist
    es nur Purelapses kleine Bewertungsdatei fuer einen Keyframe-Stern,
    gibt es nichts, in das die Belichtung eingetragen werden koennte.
    Rueckgabe: (True, "") oder (False, Grund)
    """
    if not os.path.exists(xmp_path):
        return False, "fehlt"
    try:
        _, desc = _dt_load(xmp_path)
    except (ET.ParseError, OSError):
        return False, "nicht lesbar"
    if _dt_history_seq(desc) is None:
        return False, "ohne Darktable-Bearbeitungsliste"
    return True, ""


def _dt_attr(li, name, default=None):
    """Ein Feld eines History-Eintrags - als Attribut (so schreibt es
    Darktable) oder als Kindelement (so koennen es andere Werkzeuge
    schreiben)."""
    wert = li.get(_qn(_DT, name))
    if wert is None:
        kind = li.find(_qn(_DT, name))
        if kind is not None:
            wert = kind.text or ''
    return default if wert is None else wert


def _dt_int(text, default=0):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return default


# ==========================================================================
#  DARKTABLE: DER KOMPLETTE MODULSTAPEL
#
#  Bisher kannte Purelapse in einer Darktable-XMP nur die Belichtung. Alles
#  andere, was in den Keyframes eingestellt war - Weissabgleich, Schaerfe,
#  Farbbalance, Filmic ... -, kam in den Bildern dazwischen nie an: die
#  Keyframes "blitzten" im Video auf.
#
#  Jetzt liest Purelapse den wirksamen Stapel eines Keyframes vollstaendig
#  und schreibt ihn in die Bilder dazwischen. Zahlenparameter werden dabei
#  weich ueberblendet, alles andere (Schalter, Auswahllisten, Masken,
#  Module, die nur in einem Keyframe vorkommen) kommt vom naeheren Keyframe.
#
#  Wie die Parameter eines Moduls im Speicher liegen, steht in seinem
#  Quelltext (struct dt_iop_..._params_t). Die Tabelle unten ist daraus fuer
#  darktable 4.6.1 automatisch erzeugt. Darktable erhoeht die Modulversion
#  (modversion), sobald sich dieses Layout aendert - zusammen mit der
#  Groessenpruefung beim Entschluesseln ist damit sicher, dass nie ein
#  fremdes Layout ueberblendet wird. Passt etwas nicht, wird das Modul wie
#  ein Schalter behandelt: unveraendert vom naeheren Keyframe.
#
#  Feldarten: f = Kommazahl (wird ueberblendet), fh = Farbton in Grad
#  (ueberblendet auf dem kuerzeren Weg um den Farbkreis), i = Ganzzahl,
#  Schalter oder Auswahl (wird nie ueberblendet). Eine Zahl dahinter ist
#  die Anzahl bei Feldern.
# ==========================================================================
_DT_LAYOUT_TEXT = {
    'ashift': (5, 'rotation:f lensshift_v:f lensshift_h:f shear:f f_length:f crop_factor:f orthocorr:f aspect:f mode:i cropmode:i cl:f cr:f ct:f cb:f last_drawn_lines:f200 last_drawn_lines_count:i last_quad_lines:f8'),
    'atrous': (2, 'octaves:i x:f30 y:f30 mix:f'),
    'basicadj': (2, 'black_point:f exposure:f hlcompr:f hlcomprthresh:f contrast:f preserve_colors:i middle_grey:f brightness:f saturation:f vibrance:f clip:f'),
    'bilat': (3, 'mode:i sigma_r:f sigma_s:f detail:f midtone:f'),
    'bilateral': (1, 'radius:f reserved:f red:f green:f blue:f'),
    'bloom': (1, 'size:f threshold:f strength:f'),
    'blurs': (1, 'type:i radius:i blades:i concavity:f linearity:f rotation:f angle:f curvature:f offset:f'),
    'cacorrect': (2, 'avoidshift:i iterations:i'),
    'cacorrectrgb': (1, 'guide_channel:i radius:f strength:f mode:i refine_manifolds:i'),
    'censorize': (1, 'radius_1:f pixelate:f radius_2:f noise:f'),
    'channelmixer': (2, 'red:f7 green:f7 blue:f7 algorithm_version:i'),
    'channelmixerrgb': (3, 'red:f4 green:f4 blue:f4 saturation:f4 lightness:f4 grey:f4 normalize_R:i normalize_G:i normalize_B:i normalize_sat:i normalize_light:i normalize_grey:i illuminant:i illum_fluo:i illum_led:i adaptation:i x:f y:f temperature:f gamut:f clip:i version:i'),
    'clipping': (5, 'angle:f cx:f cy:f cw:f ch:f k_h:f k_v:f kxa:f kya:f kxb:f kyb:f kxc:f kyc:f kxd:f kyd:f k_type:i k_sym:i k_apply:i crop_auto:i ratio_n:i ratio_d:i'),
    'colisa': (1, 'contrast:f brightness:f saturation:f'),
    'colorbalance': (3, 'mode:i lift:f4 gamma:f4 gain:f4 saturation:f contrast:f grey:f saturation_out:f'),
    'colorbalancergb': (5, 'shadows_Y:f shadows_C:f shadows_H:fh midtones_Y:f midtones_C:f midtones_H:fh highlights_Y:f highlights_C:f highlights_H:fh global_Y:f global_C:f global_H:fh shadows_weight:f white_fulcrum:f highlights_weight:f chroma_shadows:f chroma_highlights:f chroma_global:f chroma_midtones:f saturation_global:f saturation_highlights:f saturation_midtones:f saturation_shadows:f hue_angle:f brilliance_global:f brilliance_highlights:f brilliance_midtones:f brilliance_shadows:f mask_grey_fulcrum:f vibrance:f grey_fulcrum:f contrast:f saturation_formula:i'),
    'colorchecker': (2, 'source_L:f49 source_a:f49 source_b:f49 target_L:f49 target_a:f49 target_b:f49 num_patches:i'),
    'colorcontrast': (2, 'a_steepness:f a_offset:f b_steepness:f b_offset:f unbound:i'),
    'colorcorrection': (1, 'hia:f hib:f loa:f lob:f saturation:f'),
    'colorize': (2, 'hue:f saturation:f source_lightness_mix:f lightness:f version:i'),
    'colorreconstruction': (3, 'threshold:f spatial:f range:f hue:f precedence:i'),
    'crop': (1, 'cx:f cy:f cw:f ch:f ratio_n:i ratio_d:i'),
    'defringe': (1, 'radius:f thresh:f op_mode:i'),
    'demosaic': (4, 'green_eq:i median_thrs:f color_smoothing:i demosaicing_method:i lmmse_refine:i dual_thrs:f'),
    'denoiseprofile': (11, 'radius:f nbhood:f strength:f shadows:f bias:f scattering:f central_pixel_weight:f overshooting:f a:f3 b:f3 mode:i x:f42 y:f42 wb_adaptive_anscombe:i fix_anscombe_and_nlmeans_norm:i use_new_vst:i wavelet_color_mode:i'),
    'diffuse': (2, 'iterations:i sharpness:f radius:i regularization:f variance_threshold:f anisotropy_first:f anisotropy_second:f anisotropy_third:f anisotropy_fourth:f threshold:f first:f second:f third:f fourth:f radius_center:i'),
    'equalizer': (1, 'equalizer_x:f18 equalizer_y:f18'),
    'exposure': (6, 'mode:i black:f exposure:f deflicker_percentile:f deflicker_target_level:f compensate_exposure_bias:i'),
    'filmic': (3, 'grey_point_source:f black_point_source:f white_point_source:f security_factor:f grey_point_target:f black_point_target:f white_point_target:f output_power:f latitude_stops:f contrast:f saturation:f global_saturation:f balance:f interpolator:i preserve_color:i'),
    'filmicrgb': (6, 'grey_point_source:f black_point_source:f white_point_source:f reconstruct_threshold:f reconstruct_feather:f reconstruct_bloom_vs_details:f reconstruct_grey_vs_color:f reconstruct_structure_vs_texture:f security_factor:f grey_point_target:f black_point_target:f white_point_target:f output_power:f latitude:f contrast:f saturation:f balance:f noise_level:f preserve_color:i version:i auto_hardness:i custom_grey:i high_quality_reconstruction:i noise_distribution:i shadows:i highlights:i compensate_icc_black:i spline_version:i enable_highlight_reconstruction:i'),
    'finalscale': (1, 'dummy:i'),
    'flip': (2, 'orientation:i'),
    'gamma': (1, 'gamma:f linear:f'),
    'graduatednd': (1, 'density:f hardness:f rotation:f offset:f hue:f saturation:f'),
    'grain': (2, 'channel:i scale:f strength:f midtones_bias:f'),
    'hazeremoval': (1, 'strength:f distance:f'),
    'highlights': (4, 'mode:i blendL:f blendC:f strength:f clip:f noise_level:f iterations:i scales:i candidating:f combine:f recovery:i solid_color:f'),
    'highpass': (1, 'sharpness:f contrast:f'),
    'hotpixels': (1, 'strength:f threshold:f markfixed:i permissive:i'),
    'invert': (2, 'color:f4'),
    'levels': (2, 'mode:i black:f gray:f white:f levels:f3'),
    'lowlight': (1, 'blueness:f transition_x:f6 transition_y:f6'),
    'lowpass': (4, 'order:i radius:f contrast:f brightness:f saturation:f lowpass_algo:i unbound:i'),
    'mask_manager': (2, 'dummy:i'),
    'monochrome': (2, 'a:f b:f size:f highlights:f'),
    'negadoctor': (2, 'film_stock:i Dmin:f4 wb_high:f4 wb_low:f4 D_max:f offset:f black:f gamma:f soft_clip:f exposure:f'),
    'nlmeans': (2, 'radius:f strength:f luma:f chroma:f'),
    'primaries': (1, 'achromatic_tint_hue:f achromatic_tint_purity:f red_hue:f red_purity:f green_hue:f green_purity:f blue_hue:f blue_purity:f'),
    'profile_gamma': (2, 'mode:i linear:f gamma:f dynamic_range:f grey_point:f shadows_range:f security_factor:f'),
    'rawdenoise': (2, 'threshold:f x:f20 y:f20'),
    'relight': (1, 'ev:f center:f width:f'),
    'rgblevels': (1, 'autoscale:i preserve_colors:i levels:f9'),
    'rotatepixels': (1, 'rx:i ry:i angle:f'),
    'scalepixels': (1, 'pixel_aspect_ratio:f'),
    'shadhi': (5, 'order:i radius:f shadows:f whitepoint:f highlights:f reserved2:f compress:f shadows_ccorrect:f highlights_ccorrect:f flags:i low_approximation:f shadhi_algo:i'),
    'sharpen': (1, 'radius:f amount:f threshold:f'),
    'sigmoid': (3, 'middle_grey_contrast:f contrast_skewness:f display_white_target:f display_black_target:f color_processing:i hue_preservation:f red_inset:f red_rotation:f green_inset:f green_rotation:f blue_inset:f blue_rotation:f purity:f base_primaries:i'),
    'soften': (1, 'size:f saturation:f brightness:f amount:f'),
    'splittoning': (1, 'shadow_hue:f shadow_saturation:f highlight_hue:f highlight_saturation:f balance:f compress:f'),
    'spots': (2, 'clone_id:i64 clone_algo:i64'),
    'temperature': (3, 'red:f green:f blue:f various:f'),
    'toneequal': (2, 'noise:f ultra_deep_blacks:f deep_blacks:f blacks:f shadows:f midtones:f highlights:f whites:f speculars:f blending:f smoothing:f feathering:f quantization:f contrast_boost:f exposure_boost:f details:i method:i iterations:i'),
    'tonemap': (1, 'contrast:f Fsize:f'),
    'useless': (3, 'checker_scale:i factor:f check:i method:i'),
    'velvia': (2, 'strength:f bias:f'),
    'vibrance': (2, 'amount:f'),
    'zonesystem': (1, 'size:i zone:f25'),
}


def _dt_layouts_aufbauen():
    tabelle = {}
    for op, (version, spec) in _DT_LAYOUT_TEXT.items():
        felder = []
        for teil in spec.split():
            name, art = teil.split(':')
            m = re.match(r'(fh|f|i)(\d*)$', art)
            felder.append((name, m.group(1), int(m.group(2) or 1)))
        tabelle[op] = (version, felder)
    return tabelle


DT_LAYOUTS = _dt_layouts_aufbauen()

# Neuere Modulversionen aus darktable 5.6.2 (src/iop/*.c), zusaetzlich zu
# den Versionen von 4.6.1 oben. Ein XMP aus darktable 5 traegt diese
# Versionen; ohne sie konnte Purelapse dort weder die Belichtung lesen noch
# den Weissabgleich zwischen Keyframes ueberblenden.
#   exposure 7        + compensate_hilite_pres (gboolean)
#   temperature 4     + preset (int: -1 unbekannt, 0 wie aufgenommen, ...)
#   denoiseprofile 12 + compensate_hilite_pres (gboolean)
#   hazeremoval 3     + compatibility_mode, adaptive (gboolean)
_DT_LAYOUT_NEUER = [
    ('exposure', 7, 'mode:i black:f exposure:f deflicker_percentile:f deflicker_target_level:f compensate_exposure_bias:i compensate_hilite_pres:i'),
    ('temperature', 4, 'red:f green:f blue:f various:f preset:i'),
    ('denoiseprofile', 12, _DT_LAYOUT_TEXT['denoiseprofile'][1] + ' compensate_hilite_pres:i'),
    ('hazeremoval', 3, 'strength:f distance:f compatibility_mode:i adaptive:i'),
]


def _dt_versionen_aufbauen():
    """{op: {version: felder}} - alle bekannten Layouts je Modul."""
    tabelle = {op: {version: felder} for op, (version, felder) in DT_LAYOUTS.items()}
    for op, version, spec in _DT_LAYOUT_NEUER:
        felder = []
        for teil in spec.split():
            name, art = teil.split(':')
            m = re.match(r'(fh|f|i)(\d*)$', art)
            felder.append((name, m.group(1), int(m.group(2) or 1)))
        tabelle.setdefault(op, {})[version] = felder
    return tabelle


DT_LAYOUT_VERSIONEN = _dt_versionen_aufbauen()


def dt_felder_fuer(op, version):
    """Das Layout eines Moduls in genau dieser Version, sonst None."""
    return DT_LAYOUT_VERSIONEN.get(op, {}).get(_dt_int(version, -1))

# Module, deren Zahlen zwar lesbar sind, aber nicht ueberblendet werden
# duerfen: Geometrie, Retusche, Masken - ein halber Zuschnitt oder ein
# halb verschobener Stempel ergaebe Unsinn.
DT_NICHT_MISCHEN = {'ashift', 'spots', 'mask_manager', 'flip', 'crop',
                    'clipping', 'lens', 'retouch', 'liquify', 'rotatepixels',
                    'scalepixels', 'finalscale', 'colorchecker', 'hotpixels',
                    'rawprepare', 'demosaic', 'gamma', 'colorin', 'colorout'}

# Pflichtmodule der Pipeline - werden mit uebertragen, aber in der
# Uebersicht fuer den Nutzer nicht aufgezaehlt.
DT_TECHNIK = {'rawprepare', 'demosaic', 'colorin', 'colorout', 'gamma',
              'flip', 'mask_manager', 'finalscale'}

DT_MODULNAMEN = {
    'temperature': "Weissabgleich", 'channelmixerrgb': "Farbkalibrierung",
    'exposure': "Belichtung", 'sharpen': "Schaerfen",
    'colorbalancergb': "Farbbalance RGB", 'filmicrgb': "Filmic RGB",
    'sigmoid': "Sigmoid", 'basecurve': "Basiskurve",
    'toneequal': "Tonwert-Equalizer", 'bilat': "Lokaler Kontrast",
    'highlights': "Lichter-Rekonstruktion", 'vibrance': "Dynamik",
    'velvia': "Velvia", 'colisa': "Kontrast Helligkeit Saettigung",
    'hazeremoval': "Dunstentfernung", 'shadhi': "Schatten und Lichter",
    'denoiseprofile': "Entrauschen (Profil)", 'diffuse': "Diffuse/Schaerfen",
    'vignette': "Vignettierung", 'graduatednd': "Verlaufsfilter",
    'colorzones': "Farbzonen", 'rgbcurve': "RGB-Kurve",
    'tonecurve': "Gradationskurve", 'rgblevels': "RGB-Tonwerte",
    'levels': "Tonwerte", 'lens': "Objektivkorrektur",
    'ashift': "Perspektive", 'crop': "Zuschneiden", 'flip': "Ausrichtung",
    'colorin': "Eingabefarbprofil", 'colorout': "Ausgabefarbprofil",
    'demosaic': "Entrastern", 'rawprepare': "RAW-Vorbereitung",
    'basicadj': "Grundeinstellungen", 'grain': "Koernung",
    'colorcontrast': "Farbkontrast", 'atrous': "Kontrast-Equalizer",
    'blurs': "Weichzeichner", 'soften': "Weichzeichnen", 'bloom': "Bloom",
    'lowlight': "Low-Light-Sicht", 'monochrome': "Monochrom",
    'splittoning': "Teiltonung", 'nlmeans': "Entrauschen (NL-Means)",
    'hotpixels': "Hotpixel", 'cacorrect': "CA-Korrektur",
    'cacorrectrgb': "CA-Korrektur RGB", 'defringe': "Farbsaum",
    'retouch': "Retusche", 'spots': "Flecken entfernen",
}

DT_SEK = 'dt:'              # Sektionen mit einer Modulinstanz: dt:op#prio
DT_STAPEL = 'dt~stapel'     # Sektion mit dem, was den Stapel zusammenhaelt
_DT_META = ('~modversion', '~enabled', '~multi_name', '~multi_name_hand_edited',
            '~blendop_version', '~blendop_params', '~params')
_DT_HASHES = ('history_current_hash', 'history_basic_hash', 'history_auto_hash')


# Grundwerte der Module, die Purelapse bei Bedarf selbst anlegt - aus den
# $DEFAULT-Angaben im Quelltext von darktable 4.6.1 (keines der Module
# aendert sie beim Laden; die eine Abweichung steht bei shadhi).
DT_STANDARD = {
    'hotpixels': (1, {'strength': 0.25, 'threshold': 0.05, 'markfixed': 0,
                      'permissive': 0}),
    # shadhi: Felder und Grundwerte aus src/iop/shadhi.c (Version 5) -
    # mit EINER Ausnahme: Tiefen und Lichter stehen auf 0 statt +50/-50.
    # Darktables Grundwerte wirken schon beim Einschalten; hier soll das
    # neu angelegte Modul nichts tun, solange der Regler nicht bewegt ist.
    # order 0 = DT_IOP_GAUSSIAN_ZERO, flags 127 = UNBOUND_DEFAULT,
    # shadhi_algo 1 = SHADHI_ALGO_BILATERAL.
    'shadhi': (5, {'order': 0, 'radius': 100.0, 'shadows': 0.0,
                   'whitepoint': 0.0, 'highlights': 0.0, 'reserved2': 0.0,
                   'compress': 50.0, 'shadows_ccorrect': 100.0,
                   'highlights_ccorrect': 50.0, 'flags': 127,
                   'low_approximation': 0.000001, 'shadhi_algo': 1}),
    'sharpen': (1, {'radius': 2.0, 'amount': 0.5, 'threshold': 0.5}),
    'colorbalancergb': (5, dict(
        {n: 0.0 for n in ('shadows_Y', 'shadows_C', 'shadows_H', 'midtones_Y',
                          'midtones_C', 'midtones_H', 'highlights_Y', 'highlights_C',
                          'highlights_H', 'global_Y', 'global_C', 'global_H',
                          'white_fulcrum', 'chroma_shadows', 'chroma_highlights',
                          'chroma_global', 'chroma_midtones', 'saturation_global',
                          'saturation_highlights', 'saturation_midtones',
                          'saturation_shadows', 'hue_angle', 'brilliance_global',
                          'brilliance_highlights', 'brilliance_midtones',
                          'brilliance_shadows', 'vibrance', 'contrast')},
        shadows_weight=1.0, highlights_weight=1.0, mask_grey_fulcrum=0.1845,
        grey_fulcrum=0.1845, saturation_formula=1)),
}


def dt_modul_setzen(profil, op, aenderungen=None, an=True):
    """
    Setzt Felder eines Darktable-Moduls (erste Instanz) im Profil-Dict.
    Fehlt das Modul im Stapel, wird es mit seinen Grundwerten angelegt.
    Rueckgabe: der Sektionsname oder None, wenn das Modul unbekannt ist.
    """
    sec = f"{DT_SEK}{op}#0"
    sek = profil.get(sec)
    if sek is None:
        if op not in DT_STANDARD:
            return None
        version, grund = DT_STANDARD[op]
        felder = dt_felder_fuer(op, version)
        sek = {'~modversion': str(version), '~enabled': '1', '~multi_name': '',
               '~multi_name_hand_edited': '0', '~blendop_version': '13',
               '~blendop_params': _DT_NEUTRAL_BLEND, '~params': ''}
        for name, art, n in felder:
            sek[name] = _dt_wert_text(art, [grund[name]] * n)
        profil[sec] = sek
        meta = profil.setdefault(DT_STAPEL, {})
        reihe = meta.get('reihenfolge', '').split()
        if sec not in reihe:
            meta['reihenfolge'] = ' '.join(reihe + [sec])
    felder = dt_felder_fuer(op, sek.get('~modversion'))
    if felder is None:
        return None
    for name, wert in (aenderungen or {}).items():
        art = next((a for nm, a, _n in felder if nm == name), None)
        if art is None:
            continue
        sek[name] = _dt_wert_text(art, [wert])
    sek['~enabled'] = '1' if an else '0'
    sek['~params'] = _dt_felder_packen(op, sek)
    return sec


def dt_ist_sektion(sec):
    return sec.startswith(DT_SEK) or sec == DT_STAPEL


def dt_modulname(sec, sektion=None):
    """Lesbarer Name einer Modulinstanz fuer Meldungen."""
    if sec == DT_STAPEL:
        return "Modul-Reihenfolge/Masken"
    op, _, prio = sec[len(DT_SEK):].partition('#')
    name = DT_MODULNAMEN.get(op, op)
    if prio not in ('', '0'):
        zusatz = (sektion or {}).get('~multi_name') or f"Instanz {prio}"
        name = f"{name} ({zusatz})"
    return name


def dt_params_lesen(text):
    """Darktable speichert Parameter als Hex-Text oder - bei groesseren -
    als "gz" + zweistelliger Faktor + Base64 eines zlib-Pakets."""
    import base64
    import zlib
    text = (text or '').strip()
    try:
        if text.startswith('gz'):
            return zlib.decompress(base64.b64decode(text[4:]))
        return bytes.fromhex(text)
    except (ValueError, zlib.error):
        return None


def _dt_layout(op, modversion, roh):
    """Das Layout, wenn es zu Version UND Groesse passt - sonst None."""
    felder = dt_felder_fuer(op, modversion)
    if felder is None or roh is None:
        return None
    if sum(4 * n for _, _, n in felder) != len(roh):
        return None
    return felder


def _dt_struct(felder):
    return struct.Struct('<' + ''.join(art[0] * n for _, art, n in felder))


def _dt_wert_text(art, werte):
    if art == 'i':
        return ' '.join(str(int(w)) for w in werte)
    return ' '.join(repr(float(w)) for w in werte)


def _dt_felder_lesen(op, modversion, roh):
    """{Feldname: Text} eines Moduls oder None, wenn das Layout unbekannt ist."""
    felder = _dt_layout(op, modversion, roh)
    if felder is None:
        return None
    werte = _dt_struct(felder).unpack(roh)
    out, pos = {}, 0
    for name, art, n in felder:
        out[name] = _dt_wert_text(art, werte[pos:pos + n])
        pos += n
    return out


def _dt_felder_packen(op, sektion):
    """Packt die Felder einer Sektion wieder zu Darktables Hex-Text."""
    felder = dt_felder_fuer(op, sektion.get('~modversion'))
    if felder is None:
        raise ValueError(f"{op}: Version {sektion.get('~modversion')} unbekannt")
    werte = []
    for name, art, n in felder:
        teile = str(sektion[name]).split()
        if len(teile) != n:
            raise ValueError(f"{op}.{name}: {len(teile)} statt {n} Werte")
        werte.extend(int(t) if art == 'i' else float(t) for t in teile)
    return _dt_struct(felder).pack(*werte).hex()


def _dt_eintraege(desc):
    """Alle History-Eintraege, nach Nummer sortiert, mit history_end."""
    seq = _dt_history_seq(desc)
    if seq is None:
        return [], 0
    lis = list(seq.findall(_qn(_RDF, 'li')))
    lis.sort(key=lambda li: _dt_int(_dt_attr(li, 'num'), 0))
    ende = _dt_int(desc.get(_qn(_DT, 'history_end')), len(lis))
    return lis, ende


def dt_stapel(desc):
    """
    Der wirksame Modulstapel: {(op, prio): rdf:li}.

    Darktable ordnet jeden History-Eintrag ueber Modulname UND
    multi_priority einer Instanz zu; der spaetere Eintrag gewinnt.
    Eintraege ab history_end zaehlen nicht (dahin hat der Nutzer im
    Verlauf zurueckgeschaltet). Die Reihenfolge ist die der letzten
    Aenderung.
    """
    lis, ende = _dt_eintraege(desc)
    stapel = {}
    for li in lis:
        if _dt_int(_dt_attr(li, 'num'), 0) >= ende:
            continue
        key = (_dt_attr(li, 'operation', ''), _dt_int(_dt_attr(li, 'multi_priority'), 0))
        stapel.pop(key, None)
        stapel[key] = li
    return stapel


def _dt_haupt_key(stapel):
    """
    Die Belichtungsinstanz, in die Purelapse den Deflicker-Wert schreibt.

    Eine wirksame Instanz mit Purelapses Namen (aeltere Versionen haben sie
    angelegt), sonst die erste Belichtungsinstanz. Die gibt es im
    szenenbezogenen Ablauf immer: Darktable legt sie mit +0,7 EV an. In
    die schreibt Purelapse jetzt - wie bei ART die Belichtungskorrektur -
    den Gesamtwert; die eigene Aenderung des Nutzers bleibt als Abstand
    zum Deflicker-Wert erhalten.

    Frueher wurde eine zweite Instanz mit derselben multi_priority 0
    angelegt. Darktable fasst beide zu EINER zusammen, der spaetere
    Eintrag gewinnt - je nach Reihenfolge war der Deflicker-Wert oder
    Darktables Grundbelichtung verloren.
    """
    for key, li in stapel.items():
        if key[0] == 'exposure' and _dt_attr(li, 'multi_name') == _DT_OWN_MULTI_NAME:
            return key
    if ('exposure', 0) in stapel:
        return ('exposure', 0)
    prios = sorted(p for op, p in stapel if op == 'exposure')
    return ('exposure', prios[0]) if prios else None


def _dt_sek_name(key):
    return f"{DT_SEK}{key[0]}#{key[1]}"


def _dt_haupt_ev(li):
    """Belichtungswert einer exposure-Instanz oder None."""
    if li is None or _dt_attr(li, 'enabled') != '1':
        return None
    fields = _dt_decode_exposure(_dt_attr(li, 'params', ''),
                                 _dt_int(_dt_attr(li, 'modversion'), 0))
    return fields['exposure'] if fields else None


def _dt_get_current_ev(desc):
    stapel = dt_stapel(desc)
    key = _dt_haupt_key(stapel)
    return _dt_haupt_ev(stapel.get(key)) if key else None


def _dt_neuer_eintrag(seq, num, op, prio, felder):
    li = ET.SubElement(seq, _qn(_RDF, 'li'))
    li.set(_qn(_DT, 'num'), str(num))
    li.set(_qn(_DT, 'operation'), op)
    for name in ('enabled', 'modversion', 'params', 'multi_name',
                 'multi_name_hand_edited'):
        li.set(_qn(_DT, name), felder.get(name, ''))
    li.set(_qn(_DT, 'multi_priority'), str(prio))
    for name in ('blendop_version', 'blendop_params'):
        if felder.get(name):
            li.set(_qn(_DT, name), felder[name])
    return li


def _dt_ev_setzen(li, ev_offset):
    """Traegt den Belichtungswert in einen exposure-Eintrag ein. Die
    uebrigen Felder (Schwarzwert, Belichtungsausgleich) bleiben, wie der
    Nutzer sie hat; nur die Betriebsart wird "manuell" - im Modus
    "Deflicker" rechnet Darktable die Belichtung selbst aus und der
    eingetragene Wert waere wirkungslos."""
    version = _dt_int(_dt_attr(li, 'modversion'), 0)
    fields = _dt_decode_exposure(_dt_attr(li, 'params', ''), version)
    if fields is None:
        # Neu oder unbekannt: Version 6. darktable 5 rechnet sie beim Laden
        # selbst auf 7 um (compensate_hilite_pres = aus, wie bisher).
        version = 6
        fields = {'mode': 0, 'black': 0.0, 'exposure': 0.0,
                  'deflicker_percentile': 50.0, 'deflicker_target_level': -4.0,
                  'compensate_exposure_bias': 0}
    fields['mode'] = 0
    fields['exposure'] = float(ev_offset)
    li.set(_qn(_DT, 'params'), _dt_encode_exposure(fields, version))
    li.set(_qn(_DT, 'modversion'), str(version))
    li.set(_qn(_DT, 'enabled'), '1')


def _dt_write_ev(xmp_path, ev_offset):
    """
    Schreibt den Deflicker-Wert in die Darktable-XMP, ohne den Verlauf
    sonst anzufassen: in den WIRKSAMEN Eintrag der Belichtungsinstanz
    (siehe _dt_haupt_key). Gibt es noch keine, kommt eine dazu.
    """
    tree, desc = _dt_load(xmp_path)
    seq = _dt_history_seq(desc)
    if seq is None:
        raise RuntimeError(f"{os.path.basename(xmp_path)}: kein <darktable:history> gefunden.")
    stapel = dt_stapel(desc)
    key = _dt_haupt_key(stapel)
    if key is not None:
        _dt_ev_setzen(stapel[key], ev_offset)
    else:
        lis, ende = _dt_eintraege(desc)
        # Eintraege hinter history_end verwirft Darktable bei jeder neuen
        # Aenderung - genauso hier, sonst wuerden sie wieder wirksam.
        for li in lis:
            if _dt_int(_dt_attr(li, 'num'), 0) >= ende:
                seq.remove(li)
        li = _dt_neuer_eintrag(seq, ende, 'exposure', 0, {
            'enabled': '1', 'modversion': '6', 'params': '',
            'multi_name': _DT_OWN_MULTI_NAME, 'multi_name_hand_edited': '0',
            'blendop_version': '13', 'blendop_params': _DT_NEUTRAL_BLEND})
        _dt_ev_setzen(li, ev_offset)
        desc.set(_qn(_DT, 'history_end'), str(ende + 1))
    xml_atomar(tree, xmp_path)


def _dt_stapel_dict(desc):
    """Die Sektionen dt~stapel und dt:op#prio eines Profil-Dicts."""
    stapel = dt_stapel(desc)
    haupt = _dt_haupt_key(stapel)
    masken = desc.find(_qn(_DT, 'masks_history'))
    out = {DT_STAPEL: {
        'iop_order_version': desc.get(_qn(_DT, 'iop_order_version'), ''),
        'iop_order_list': desc.get(_qn(_DT, 'iop_order_list'), ''),
        'masks_history': (ET.tostring(masken, encoding='unicode')
                          if masken is not None and len(masken) else ''),
        'haupt': _dt_sek_name(haupt) if haupt else '',
        'reihenfolge': ' '.join(_dt_sek_name(k) for k in stapel),
        'auto_presets_applied': desc.get(_qn(_DT, 'auto_presets_applied'), '0'),
    }}
    for key, li in stapel.items():
        sek = {}
        for name in _DT_META:
            sek[name] = _dt_attr(li, name[1:], '')
        felder = _dt_felder_lesen(key[0], sek['~modversion'],
                                  dt_params_lesen(sek['~params']))
        if felder:
            sek.update(felder)
        out[_dt_sek_name(key)] = sek
    return out


def read_arp_dict_dt(xmp_path):
    """
    Liest eine Darktable-XMP in DERSELBEN Dict-Form wie read_arp_dict_ini():
    [Exposure] Compensation ist der Wert der Belichtungsinstanz, in die
    der Deflicker schreibt. Dazu kommt der komplette wirksame Modulstapel
    (Sektionen dt~stapel und dt:op#prio), damit die Keyframe-Verteilung
    ihn in die Bilder dazwischen uebertragen kann.
    """
    if not os.path.exists(xmp_path):
        return {}
    try:
        _, desc = _dt_load(xmp_path)
    except (ET.ParseError, OSError):
        return {}
    ev = _dt_get_current_ev(desc)
    data = {
        'Version': {'AppVersion': 'darktable-passthrough'},
        'Exposure': {
            'Enabled': 'true' if ev is not None else 'false',
            'Auto': 'false',
        },
    }
    if ev is not None:
        data['Exposure']['Compensation'] = f"{ev:.3f}"
    if _dt_history_seq(desc) is not None:
        data.update(_dt_stapel_dict(desc))
    return data


def _dt_vergleichsform(data):
    """Der Stapel ohne das, was der Deflicker ohnehin selbst setzt."""
    out = {sec: dict(par) for sec, par in data.items() if dt_ist_sektion(sec)}
    haupt = out.get(DT_STAPEL, {}).get('haupt')
    if haupt in out:
        for k in ('~params', '~enabled', 'exposure', 'mode'):
            out[haupt].pop(k, None)
    return out


def _dt_stapel_schreiben(xmp_path, data, ev):
    """
    Schreibt den Modulstapel aus dem Profil-Dict als neuen, kompakten
    Verlauf in die XMP. Bewertung, Zeitstempel und alles ausserhalb des
    Verlaufs bleiben, wie sie in der Datei stehen.
    """
    if os.path.exists(xmp_path):
        try:
            tree, desc = _dt_load(xmp_path)
        except (ET.ParseError, OSError):
            tree = desc = None
    else:
        tree = desc = None
    if desc is None:
        wurzel = ET.Element(_qn('adobe:ns:meta/', 'xmpmeta'))
        rdf = ET.SubElement(wurzel, _qn(_RDF, 'RDF'))
        desc = ET.SubElement(rdf, _qn(_RDF, 'Description'))
        desc.set(_qn(_RDF, 'about'), '')
        desc.set(_qn(_DT, 'xmp_version'), '5')
        desc.set(_qn(_DT, 'raw_params'), '0')
        tree = ET.ElementTree(wurzel)
    for alt in (desc.findall(_qn(_DT, 'history'))
                + desc.findall(_qn(_DT, 'masks_history'))):
        desc.remove(alt)
    meta = data.get(DT_STAPEL, {})
    for name in _DT_HASHES:
        desc.attrib.pop(_qn(_DT, name), None)
    if meta.get('iop_order_version'):
        desc.set(_qn(_DT, 'iop_order_version'), meta['iop_order_version'])
    if meta.get('iop_order_list'):
        desc.set(_qn(_DT, 'iop_order_list'), meta['iop_order_list'])
    else:
        desc.attrib.pop(_qn(_DT, 'iop_order_list'), None)
    # Stammt der Stapel aus einem Keyframe, hat Darktable seine
    # Grundeinstellungen darin schon angewendet (1) - taete es das beim
    # Entwickeln noch einmal, kaemen sie doppelt. Eine frische Datei aus
    # Pass 1 (0) braucht sie dagegen noch: ohne sie fehlte z. B. Filmic.
    desc.set(_qn(_DT, 'auto_presets_applied'), meta.get('auto_presets_applied') or '1')
    if meta.get('masks_history'):
        try:
            desc.append(ET.fromstring(meta['masks_history']))
        except ET.ParseError:
            pass
    seq = ET.SubElement(ET.SubElement(desc, _qn(_DT, 'history')), _qn(_RDF, 'Seq'))
    secs = [s for s in meta.get('reihenfolge', '').split() if s in data]
    secs += [s for s in data if s.startswith(DT_SEK) and s not in secs]
    haupt = meta.get('haupt') or ''
    num = 0
    for sec in secs:
        sek = data[sec]
        op, _, prio = sec[len(DT_SEK):].partition('#')
        li = _dt_neuer_eintrag(seq, num, op, _dt_int(prio, 0),
                               {k[1:]: str(sek.get(k, '')) for k in _DT_META})
        if sec == haupt and ev is not None:
            _dt_ev_setzen(li, ev)
        num += 1
    if ev is not None and haupt not in data:
        li = _dt_neuer_eintrag(seq, num, 'exposure', 0, {
            'enabled': '1', 'modversion': '6', 'params': '',
            'multi_name': _DT_OWN_MULTI_NAME, 'multi_name_hand_edited': '0',
            'blendop_version': '13', 'blendop_params': _DT_NEUTRAL_BLEND})
        _dt_ev_setzen(li, ev)
        num += 1
    desc.set(_qn(_DT, 'history_end'), str(num))
    xml_atomar(tree, xmp_path)


def write_arp_dict_dt(xmp_path, data):
    """
    Schreibt ein Profil-Dict zurueck in die Darktable-XMP.

    Ist der Modulstapel derselbe wie in der Datei (Pass 1, Nachregeln,
    Keyframes selbst), wird nur der Belichtungswert geaendert - der
    Verlauf bleibt, wie Darktable ihn angelegt hat. Bringt das Dict einen
    anderen Stapel mit (Bilder zwischen Keyframes), wird er geschrieben.
    """
    try:
        comp = float(data.get('Exposure', {}).get('Compensation', 0.0))
    except (TypeError, ValueError):
        comp = 0.0
    neu = _dt_vergleichsform(data)
    if neu and neu != _dt_vergleichsform(read_arp_dict_dt(xmp_path)):
        _dt_stapel_schreiben(xmp_path, data, comp)
    else:
        _dt_write_ev(xmp_path, comp)


def _dt_mischen_float(art, a, b, t):
    if not (math.isfinite(a) and math.isfinite(b)):
        return a if t < 0.5 else b
    if art == 'fh':
        d = ((b - a + 180.0) % 360.0) - 180.0
        return (a + d * t) % 360.0
    return a + (b - a) * t


# Module, deren Wirkung sich auf Null stellen laesst, ohne sie
# auszuschalten: je Modul die Felder, die dafuer auf 0 muessen. Ein
# fehlendes Modul ist dasselbe wie eines mit diesen Nullwerten - fehlt es
# in einem der beiden Keyframes, wird von Null aus ueberblendet statt in
# der Mitte hart umzuschalten.
DT_NULLBAR = {
    'shadhi': ('shadows', 'highlights', 'whitepoint'),
    'colorbalancergb': tuple(n for n in DT_STANDARD['colorbalancergb'][1]
                             if DT_STANDARD['colorbalancergb'][1][n] == 0.0
                             and n not in ('saturation_formula',)),
}


def dt_neutral_gegenstueck(sec, vorhanden):
    """
    Die wirkungslose Fassung eines Moduls, das nur in EINEM Keyframe steht.

    Kopie des vorhandenen Moduls - gleiche Version, Maske, Ueberblendung -
    mit den Wirkungsfeldern auf 0. Rueckgabe None, wenn sich das Modul so
    nicht neutral stellen laesst.
    """
    if not sec.startswith(DT_SEK) or not vorhanden:
        return None
    op = sec[len(DT_SEK):].partition('#')[0]
    felder = DT_NULLBAR.get(op)
    layout = dt_felder_fuer(op, vorhanden.get('~modversion'))
    if not felder or layout is None or vorhanden.get('~enabled') != '1':
        return None
    namen = {n: (art, anz) for n, art, anz in layout}
    if not all(n in vorhanden for n in namen):
        return None
    neu = dict(vorhanden)
    for n in felder:
        art, anz = namen[n]
        neu[n] = _dt_wert_text(art, [0.0] * anz)
    try:
        neu['~params'] = _dt_felder_packen(op, neu)
    except Exception:
        return None
    return neu


# Hochstufen wie darktables legacy_params(): (Modul, von, nach) ->
# Werte der neuen Felder. Quelle: darktable 5.6.2, src/iop/*.c.
DT_HOCHSTUFEN = {
    ('exposure', 6, 7): {'compensate_hilite_pres': 0},
    # preset ist nur die Anzeige im Modul (wie aufgenommen, D65 ...), die
    # Faktoren sind dieselben: vom anderen Keyframe uebernehmen (None), sonst
    # schaltete der Weissabgleich nur wegen der Anzeige hart um.
    ('temperature', 3, 4): {'preset': None},
    ('denoiseprofile', 11, 12): {'compensate_hilite_pres': 0},
    ('hazeremoval', 1, 3): {'compatibility_mode': 1, 'adaptive': 0},
}


def dt_hochstufen(op, sek, ziel_version, vorbild=None):
    """
    Die Sektion in der hoeheren Version 'ziel_version' - oder None, wenn sie
    schon so neu ist oder der Weg dorthin nicht bekannt ist. Felder, die in
    DT_HOCHSTUFEN None haben, kommen aus 'vorbild' (dem anderen Keyframe).
    """
    von = _dt_int((sek or {}).get('~modversion'), -1)
    nach = _dt_int(ziel_version, -1)
    neue = DT_HOCHSTUFEN.get((op, von, nach))
    if neue is None or dt_felder_fuer(op, nach) is None:
        return None
    alt = dt_felder_fuer(op, von)
    if alt is None or not all(n in sek for n, _, _ in alt):
        return None
    neu = dict(sek)
    neu['~modversion'] = str(nach)
    for name, art, n in dt_felder_fuer(op, nach):
        if name not in neu:
            wert = neue.get(name, 0)
            if wert is None:
                if vorbild and name in vorbild:
                    neu[name] = vorbild[name]
                    continue
                wert = -1
            neu[name] = _dt_wert_text(art, [wert] * n)
    try:
        neu['~params'] = _dt_felder_packen(op, neu)
    except (ValueError, KeyError, struct.error):
        return None
    return neu


def dt_sektion_mischen(sec, s, e, t):
    """
    Ueberblendet eine dt-Sektion zwischen zwei Keyframes.
    Rueckgabe: (Sektion oder None, [was nicht weich geht])
    """
    nah = s if t < 0.5 else e
    if (not s or not e) and (s or e):
        ergaenzt = dt_neutral_gegenstueck(sec, s or e)
        if ergaenzt is not None:
            if not s:
                s = ergaenzt
            else:
                e = ergaenzt
            nah = s if t < 0.5 else e
    if not s or not e:
        return (dict(nah) if nah else None), ["nur in einem Keyframe"]
    if s == e:
        return dict(s), []
    if sec == DT_STAPEL:
        harte = [k for k in ('iop_order_version', 'iop_order_list', 'masks_history')
                 if s.get(k) != e.get(k)]
        return dict(nah), harte
    out = dict(nah)
    harte = []
    for k, label in (('~enabled', "ein/aus"), ('~modversion', "Modulversion"),
                     ('~blendop_params', "Maske/Ueberblendung"),
                     ('~blendop_version', "Maske/Ueberblendung")):
        if s.get(k) != e.get(k) and label not in harte:
            harte.append(label)
    op = sec[len(DT_SEK):].partition('#')[0]
    # Keyframes aus verschiedenen darktable-Versionen: die aeltere Fassung
    # so hochstufen, wie darktable selbst es beim Laden taete.
    if s.get('~modversion') != e.get('~modversion'):
        s2 = dt_hochstufen(op, s, e.get('~modversion'), e)
        e2 = dt_hochstufen(op, e, s.get('~modversion'), s)
        if (s2 or e2) is not None:
            s, e = (s2 or s), (e2 or e)
            if s.get('~modversion') == e.get('~modversion'):
                harte = [h for h in harte if h != "Modulversion"]
                nah = s if t < 0.5 else e
                out = dict(nah)
    felder = None
    if s.get('~modversion') == e.get('~modversion') and op not in DT_NICHT_MISCHEN:
        layout = dt_felder_fuer(op, s.get('~modversion'))
        if layout is not None and all(n in s and n in e for n, _, _ in layout):
            felder = layout
    if felder is None:
        if s.get('~params') != e.get('~params'):
            harte.append("Einstellungen")
        return out, harte
    for name, art, n in felder:
        v_s, v_e = s[name], e[name]
        if v_s == v_e:
            out[name] = v_s
            continue
        if art == 'i':
            out[name] = nah[name]
            harte.append(name)
            continue
        a, b = [float(x) for x in v_s.split()], [float(x) for x in v_e.split()]
        out[name] = _dt_wert_text(art, [_dt_mischen_float(art, x, y, t)
                                        for x, y in zip(a, b)])
    try:
        out['~params'] = _dt_felder_packen(op, out)
    except (ValueError, struct.error):
        return dict(nah), harte + ["Einstellungen"]
    return out, harte


def dt_stapel_uebersicht(keyframes):
    """
    Fuer die Meldung vor der Verteilung, als lesbare Namen:
    (alle eingeschalteten Module der Keyframes,
     davon zwischen den Keyframes verschieden und weich ueberblendet).
    Die Belichtungsinstanz des Deflickers zaehlt nicht mit.
    """
    alle, weich = [], []
    for profil in keyframes:
        for sec, sek in profil.items():
            if (sec.startswith(DT_SEK) and sek.get('~enabled') == '1'
                    and sec[len(DT_SEK):].partition('#')[0] not in DT_TECHNIK):
                name = dt_modulname(sec, sek)
                if name not in alle:
                    alle.append(name)
    for a, b in zip(keyframes, keyframes[1:]):
        haupt = (a.get(DT_STAPEL) or {}).get('haupt')
        va, vb = _dt_vergleichsform(a), _dt_vergleichsform(b)
        for sec in ordered_union(va, vb):
            if not sec.startswith(DT_SEK) or sec == haupt \
                    or sec[len(DT_SEK):].partition('#')[0] in DT_TECHNIK:
                continue
            if va.get(sec) == vb.get(sec):
                continue
            _, hart = dt_sektion_mischen(sec, a.get(sec), b.get(sec), 0.0)
            name = dt_modulname(sec, a.get(sec) or b.get(sec))
            if not hart and name not in weich:
                weich.append(name)
    return alle, weich


def dt_build_cli_cmd(dt_cli_path, raw_path, xmp_path, out_jpg, quality=92,
                     configdir=None, tief=False):
    """
    Baut den darktable-cli Befehl fuer EIN Bild (kein Ordner-Batch moeglich).
    HINWEIS: die genauen Flags koennen sich zwischen Darktable-Versionen
    unterscheiden - bitte nach dem ersten Testlauf pruefen/anpassen.
    """
    cmd = [dt_cli_path, raw_path]
    if xmp_path and os.path.exists(xmp_path):
        cmd.append(xmp_path)
    cmd += [out_jpg,
            "--hq", "true",
            "--width", "0", "--height", "0",
            "--core"]
    if configdir:
        # Eigener Konfigurationsordner je Prozess: darktable-cli sperrt die
        # Preset-Datenbank (data.db) darin. Zwei Prozesse - oder ein
        # geoeffnetes darktable - mit demselben Ordner scheitern sonst.
        cmd += ["--configdir", configdir]
    cmd += ["--conf", f"plugins/imageio/format/jpeg/quality={quality}"]
    if tief:
        # Format folgt der Endung der Ausgabedatei (.tif): 16 Bit Ganzzahl, gepackt
        cmd += ["--conf", "plugins/imageio/format/tiff/bpp=16",
                "--conf", "plugins/imageio/format/tiff/pixelformat=0",
                "--conf", "plugins/imageio/format/tiff/compress=1"]
    return cmd


def dt_vorschau_befehl(dt_cli_path, raw_path, profil, ordner, kante, configdir=None):
    """
    Aufruf fuer die echte Vorschau mit darktable-cli: der Stapel aus dem
    Profil-Dict als eigene XMP im Arbeitsordner, kleiner ausgegeben.
    Rueckgabe: (Befehl, Zieldatei)
    """
    xmp = os.path.join(ordner, "vorschau.xmp")
    ziel = os.path.join(ordner, "vorschau.jpg")
    try:
        ev = float(profil.get('Exposure', {}).get('Compensation'))
    except (TypeError, ValueError):
        ev = None
    _dt_stapel_schreiben(xmp, profil, ev)
    cmd = [dt_cli_path, raw_path, xmp, ziel, "--hq", "false",
           "--width", str(int(kante)), "--height", str(int(kante)), "--core"]
    if configdir:
        cmd += ["--configdir", configdir]
    cmd += ["--conf", "plugins/imageio/format/jpeg/quality=92"]
    return cmd, ziel


def dt_konfig_quelle():
    """Der Konfigurationsordner des Nutzers (darktablerc, data.db)."""
    kandidaten = [os.environ.get('DARKTABLE_CONFIGDIR'),
                  os.path.expanduser("~/.config/darktable"),
                  os.path.expanduser("~/.var/app/org.darktable.Darktable/config/darktable")]
    if os.name == 'nt':
        kandidaten.append(os.path.join(os.environ.get('LOCALAPPDATA', ''), 'darktable'))
    for ordner in kandidaten:
        if ordner and os.path.isfile(os.path.join(ordner, 'darktablerc')):
            return ordner
    return None


def dt_konfig_slots(anzahl, basis):
    """
    Legt je darktable-cli-Prozess einen eigenen Konfigurationsordner an
    und uebernimmt darktablerc und data.db des Nutzers - damit gelten seine
    Einstellungen (OpenCL, eigene Presets) auch hier. Die Ordner liegen im
    Zwischenspeicher von Purelapse und werden bei jedem Lauf aufgefrischt.
    """
    quelle = dt_konfig_quelle()
    ordner = []
    for i in range(max(1, int(anzahl))):
        ziel = os.path.join(basis, f"slot{i + 1}")
        os.makedirs(ziel, exist_ok=True)
        for name in ('darktablerc', 'data.db'):
            alt = os.path.join(ziel, name)
            if quelle and os.path.isfile(os.path.join(quelle, name)):
                shutil.copy2(os.path.join(quelle, name), alt)
        for sperre in ('data.db.lock', 'library.db.lock'):
            try:
                os.remove(os.path.join(ziel, sperre))
            except OSError:
                pass
        ordner.append(ziel)
    return ordner, quelle


# ==========================================================================
#  TEIL C: LIGHTROOM CLASSIC  (XMP mit crs:-Einstellungen)
#
#  Lightroom hat keine Kommandozeile. Purelapse arbeitet deshalb nur mit
#  den Begleitdateien: Lightroom schreibt sie ("Metadaten in Datei
#  speichern"), Purelapse traegt Belichtung und Keyframe-Ueberblendung
#  ein, Lightroom liest sie wieder ("Metadaten aus Dateien lesen") und
#  exportiert. Die Einstellungen stehen im Namensraum
#  http://ns.adobe.com/camera-raw-settings/1.0/ (Kuerzel crs) - meist als
#  Attribute von rdf:Description, Kurven und Masken als Unterelemente.
#
#  Profil-Dict wie bei den anderen Engines:
#    'Version'       Platzhalter, damit das Profil als vollstaendig gilt
#    'Exposure'      Compensation = crs:Exposure2012 (gehoert dem Deflicker)
#    'crs'           alle einfachen Einstellungen als Text
#    'crs~elemente'  Kurven, Masken, Look ... als XML-Text
#  Bewertung (xmp:Rating) und alle anderen Namensraeume (Stichwoerter,
#  EXIF ...) gehoeren dem Bild und werden nie mitkopiert.
# ==========================================================================
_CRS = 'http://ns.adobe.com/camera-raw-settings/1.0/'
ET.register_namespace('crs', _CRS)
LR_SEK = 'crs'
LR_ELEMENTE = 'crs~elemente'
# Nie ueberblenden: Kennungen, Versionen, Pruefsummen, Dateinamen.
_LR_KENNUNG = ('Version', 'ProcessVersion', 'CompatibleVersion', 'RawFileName',
               'HasSettings', 'AlreadyApplied', 'Digest', 'UUID', 'Name')
# So schreibt Lightroom sie: mit Vorzeichen (+12, -0.35).
LR_MIT_VORZEICHEN = {
    'Exposure2012', 'Contrast2012', 'Highlights2012', 'Shadows2012',
    'Whites2012', 'Blacks2012', 'Texture', 'Clarity2012', 'Dehaze',
    'Vibrance', 'Saturation', 'Tint', 'ParametricShadows', 'ParametricDarks',
    'ParametricLights', 'ParametricHighlights', 'PostCropVignetteAmount',
    'PostCropVignetteFeather', 'GrainAmount', 'SplitToningBalance',
    'ColorGradeBlending', 'ColorGradeGlobalLum', 'ColorGradeShadowLum',
    'ColorGradeMidtoneLum', 'ColorGradeHighlightLum'}
LR_WB = ('Temperature', 'Tint')


def lr_ist_sektion(sec):
    return sec in (LR_SEK, LR_ELEMENTE)


def _lr_kennung(name):
    return any(t in name for t in _LR_KENNUNG)


def _lr_dezimalen(text):
    t = str(text).strip()
    return len(t.split('.', 1)[1]) if '.' in t else 0


def lr_zahl_text(name, wert, vorbild=None):
    """
    Eine Zahl so geschrieben, wie Lightroom sie schreibt: so viele
    Nachkommastellen wie das Vorbild (die Zahl im Keyframe), mit
    Vorzeichen, wo Lightroom eines setzt.
    """
    stellen = _lr_dezimalen(vorbild) if vorbild is not None else (
        2 if name == 'Exposure2012' else 0)
    if name == 'Exposure2012':
        stellen = max(stellen, 3)      # feiner als die Anzeige: fuer den Deflicker
    vorzeichen = (name in LR_MIT_VORZEICHEN
                  or str(vorbild or '').strip().startswith('+'))
    w = round(float(wert), stellen)
    if stellen == 0:
        text = str(int(w))
    else:
        text = f"{w:.{stellen}f}"
    if text.lstrip('-').strip('0.') == '':
        text = text.lstrip('-')       # keine "-0"
    if vorzeichen and not text.startswith('-') and text.strip('0.') != '':
        text = '+' + text
    return text


def _lr_float(text):
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return None


def _lr_kurve(xml_text):
    """Punkte einer Kurve (rdf:Seq aus "x, y") oder None."""
    try:
        el = ET.fromstring(xml_text)
    except ET.ParseError:
        return None
    seq = el.find(_qn(_RDF, 'Seq'))
    if seq is None or len(el) != 1:
        return None
    punkte = []
    for li in seq:
        teile = [t.strip() for t in (li.text or '').split(',')]
        if len(teile) != 2:
            return None
        try:
            punkte.append((float(teile[0]), float(teile[1])))
        except ValueError:
            return None
    return el, seq, punkte


def _lr_element_mischen(s_xml, e_xml, t):
    """Kurven mit gleich vielen Punkten weich, alles andere vom naeheren
    Keyframe. Rueckgabe: (XML-Text, weich?)"""
    a, b = _lr_kurve(s_xml), _lr_kurve(e_xml)
    if a is None or b is None or len(a[2]) != len(b[2]):
        return (s_xml if t < 0.5 else e_xml), False
    el, seq, _ = a
    for li, (xs, ys), (xe, ye) in zip(seq, a[2], b[2]):
        li.text = f"{int(round(xs + (xe - xs) * t))}, {int(round(ys + (ye - ys) * t))}"
    return ET.tostring(el, encoding='unicode'), True


def lr_sektion_mischen(sec, s, e, t):
    """
    Ueberblendet eine Lightroom-Sektion zwischen zwei Keyframes.
    Rueckgabe: (Sektion, [Schluessel, die nicht weich gehen])
    """
    s, e = s or {}, e or {}
    out, harte = {}, []
    if sec == LR_ELEMENTE:
        for k in ordered_union(s, e):
            if k in s and k in e:
                if s[k] == e[k]:
                    out[k] = s[k]
                    continue
                out[k], weich = _lr_element_mischen(s[k], e[k], t)
                if not weich:
                    harte.append(k)
            else:
                # nur in einem Keyframe (eine Maske, eine Kurve)
                if (k in s) == (t < 0.5):
                    out[k] = s.get(k, e.get(k))
                harte.append(k)
        return out, harte
    wb_anders = any(_lr_float(s.get(k)) != _lr_float(e.get(k)) for k in LR_WB)
    for k in ordered_union(s, e):
        v_s, v_e = s.get(k), e.get(k)
        if v_s is None or v_e is None:
            out[k] = v_s if v_e is None else v_e
            continue
        if v_s == v_e:
            out[k] = v_s
            continue
        if k == 'WhiteBalance':
            continue                   # unten
        f_s, f_e = _lr_float(v_s), _lr_float(v_e)
        if f_s is None or f_e is None or _lr_kennung(k):
            out[k] = v_s if t < 0.5 else v_e
            harte.append(k)
            continue
        out[k] = lr_zahl_text(k, f_s + (f_e - f_s) * t, v_s)
    if 'WhiteBalance' in s or 'WhiteBalance' in e:
        if wb_anders:
            # Zwischenwerte sind kein "Wie aufgenommen" mehr
            out['WhiteBalance'] = "Custom"
        else:
            nah = s if t < 0.5 else e
            out['WhiteBalance'] = nah.get('WhiteBalance', s.get('WhiteBalance', e.get('WhiteBalance')))
            if s.get('WhiteBalance') != e.get('WhiteBalance'):
                harte.append('WhiteBalance')
    return out, harte


def _lr_beschreibungen(root):
    """Nur die obersten rdf:Description (direkt unter rdf:RDF). Darin
    stehende - etwa im Look (crs:Look/crs:Parameters) - tragen eigene
    crs-Werte (Name, Version, ...), die nicht die des Bildes sind."""
    rdf_tag = _qn(_RDF, 'RDF')
    wurzeln = [root] if root.tag == rdf_tag else list(root.iter(rdf_tag))[:1]
    return [k for w in wurzeln for k in w if k.tag == _qn(_RDF, 'Description')]


def _lr_namensraeume(pfad):
    """Die Kuerzel der Datei behalten - sonst schriebe ElementTree ns0:."""
    try:
        for _ereignis, (kurz, uri) in ET.iterparse(pfad, events=('start-ns',)):
            if kurz and not kurz.startswith('ns'):
                try:
                    ET.register_namespace(kurz, uri)
                except ValueError:
                    pass
    except (ET.ParseError, OSError):
        pass


def _lr_einstellungen(root):
    """Alle crs-Einstellungen: (einfach {Name: Text}, Elemente {Name: XML})."""
    einfach, elemente = {}, {}
    praefix = '{' + _CRS + '}'
    for desc in _lr_beschreibungen(root):
        for k, v in desc.attrib.items():
            if k.startswith(praefix):
                einfach[k[len(praefix):]] = v
        for kind in desc:
            if not kind.tag.startswith(praefix):
                continue
            name = kind.tag[len(praefix):]
            if len(kind) == 0:
                einfach[name] = (kind.text or '').strip()
            else:
                elemente[name] = ET.tostring(kind, encoding='unicode').strip()
    return einfach, elemente


def lr_sidecar_bereit(xmp_path):
    """
    Kann Purelapse in diese XMP schreiben? Nur, wenn Lightroom sie mit den
    Entwicklungseinstellungen angelegt hat. Eine Datei mit Purelapses
    Stern allein reicht nicht: liest Lightroom die wieder ein, stuende
    alles, was im Katalog eingestellt ist, wieder auf Grundwerten.
    Rueckgabe: (True, "") oder (False, Grund)
    """
    if not os.path.exists(xmp_path):
        return False, "fehlt"
    try:
        einfach, _ = _lr_einstellungen(ET.parse(xmp_path).getroot())
    except (ET.ParseError, OSError):
        return False, "nicht lesbar"
    if not einfach:
        return False, "ohne Entwicklungseinstellungen"
    return True, ""


def read_arp_dict_lr(xmp_path):
    if not os.path.exists(xmp_path):
        return {}
    try:
        root = ET.parse(xmp_path).getroot()
    except (ET.ParseError, OSError):
        return {}
    einfach, elemente = _lr_einstellungen(root)
    data = {'Version': {'AppVersion': 'lightroom-passthrough'},
            'Exposure': {'Enabled': 'true', 'Auto': 'false'}}
    ev = _lr_float(einfach.pop('Exposure2012', None))
    if ev is not None:
        data['Exposure']['Compensation'] = f"{ev:.3f}"
    if einfach:
        data[LR_SEK] = einfach
    if elemente:
        data[LR_ELEMENTE] = elemente
    return data


_LR_GERUEST = (
    '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Purelapse">\n'
    ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
    '  <rdf:Description rdf:about=""\n'
    '    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/">\n'
    '  </rdf:Description>\n'
    ' </rdf:RDF>\n'
    '</x:xmpmeta>\n')


def write_arp_dict_lr(xmp_path, data):
    """
    Traegt das Profil-Dict in die XMP ein. Steht im Dict eine Sektion
    'crs', gilt sie vollstaendig: Einstellungen, die dort fehlen, kommen
    aus der Datei heraus (so wird ein Bild zur genauen Kopie des
    Keyframes). Bewertung, Stichwoerter und alles ausserhalb von crs
    bleiben, wie sie sind.
    """
    if os.path.exists(xmp_path):
        _lr_namensraeume(xmp_path)
        try:
            tree = ET.parse(xmp_path)
        except ET.ParseError as e:
            raise OSError(f"{os.path.basename(xmp_path)} ist keine lesbare XMP: {e}") from e
    else:
        tree = ET.ElementTree(ET.fromstring(_LR_GERUEST))
    root = tree.getroot()
    beschreibungen = _lr_beschreibungen(root)
    if not beschreibungen:
        raise OSError(f"{os.path.basename(xmp_path)}: kein rdf:Description")
    praefix = '{' + _CRS + '}'
    voll = LR_SEK in data
    einfach = dict(data.get(LR_SEK, {}))
    comp = _lr_float(data.get('Exposure', {}).get('Compensation'))
    if comp is not None:
        einfach['Exposure2012'] = lr_zahl_text('Exposure2012', comp)
    elemente = data.get(LR_ELEMENTE, {}) if voll else None
    # vorhandene Stellen der Einstellungen
    gesetzt = set()
    for desc in beschreibungen:
        for k in list(desc.attrib):
            if not k.startswith(praefix):
                continue
            name = k[len(praefix):]
            if name in einfach:
                desc.set(k, einfach[name])
                gesetzt.add(name)
            elif voll:
                del desc.attrib[k]
        for kind in list(desc):
            if not kind.tag.startswith(praefix):
                continue
            name = kind.tag[len(praefix):]
            if len(kind) == 0:
                if name in einfach:
                    kind.text = einfach[name]
                    gesetzt.add(name)
                elif voll:
                    desc.remove(kind)
            elif elemente is not None:
                desc.remove(kind)       # unten aus dem Profil neu
    ziel = next((d for d in beschreibungen
                 if any(k.startswith(praefix) for k in d.attrib)), beschreibungen[0])
    for name, wert in einfach.items():
        if name not in gesetzt:
            ziel.set(praefix + name, str(wert))
    if not any(praefix + 'ProcessVersion' == k for d in beschreibungen for k in d.attrib) \
            and 'ProcessVersion' not in einfach:
        ziel.set(praefix + 'ProcessVersion', "11.0")
    if 'HasSettings' not in einfach and praefix + 'HasSettings' not in ziel.attrib:
        ziel.set(praefix + 'HasSettings', "True")
    for name in sorted(elemente or {}):
        try:
            ziel.append(ET.fromstring(elemente[name]))
        except ET.ParseError:
            continue
    import io as _io
    puffer = _io.BytesIO()
    tree.write(puffer, encoding='UTF-8', xml_declaration=False)
    try:
        datei_atomar(xmp_path, puffer.getvalue())
    except OSError as e:
        raise OSError(f"{os.path.basename(xmp_path)} konnte nicht geschrieben "
                      f"werden: {e.strerror or e}") from e


def lr_hinweise(profil):
    """Was in einem Lightroom-Keyframe fuer den Zeitraffer heikel ist."""
    out = []
    crs = (profil or {}).get(LR_SEK, {})
    if crs.get('WhiteBalance') == 'Auto':
        out.append('wb_auto')
    if str(crs.get('AutoTone', '')).lower() == 'true':
        out.append('auto_tone')
    return out


# ==========================================================================
#  DISPATCHER: hier entscheidet sich, welche Implementierung laeuft
# ==========================================================================
def read_arp_dict(arp_path):
    if ENGINE == 'dt':
        return read_arp_dict_dt(arp_path)
    if ENGINE == 'lr':
        return read_arp_dict_lr(arp_path)
    return read_arp_dict_ini(arp_path)


def write_arp_dict(arp_path, data):
    if ENGINE == 'dt':
        write_arp_dict_dt(arp_path, data)
    elif ENGINE == 'lr':
        write_arp_dict_lr(arp_path, data)
    else:
        write_arp_dict_ini(arp_path, data)


def find_arp_template(target_dir, files=None):
    if ENGINE == 'dt':
        return {}, "(Darktable: kein Basisprofil erforderlich)"
    if ENGINE == 'lr':
        return {}, "(Lightroom: kein Basisprofil erforderlich)"
    return find_arp_template_ini(target_dir, files)


def bootstrap_arp_template(art_cli_path, sample_image):
    if ENGINE in ('dt', 'lr'):
        return None, ""
    return bootstrap_arp_template_ini(art_cli_path, sample_image)


def write_arp_file(filepath, ev_offset, template=None, hotpixel=False):
    """Schreibt die Deflicker-Belichtung in das Sidecar des Bildes."""
    arp_path = sidecar(filepath)
    data = read_arp_dict(arp_path)
    if not profile_is_complete(data):
        if template:
            merged = {sec: dict(params) for sec, params in template.items()}
            for sec, params in data.items():
                merged.setdefault(sec, {}).update(params)
            data = merged
    exp = data.setdefault('Exposure', {})
    exp['Enabled'] = "true"
    exp['Auto'] = "false"
    exp['Compensation'] = f"{ev_offset:.3f}"
    set_raw_hotpixel(data, hotpixel)
    if eng('kind') == 'ini':
        automatik_einfrieren(data)
    write_arp_dict(arp_path, data)
