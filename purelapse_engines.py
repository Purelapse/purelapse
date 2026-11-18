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
import xml.etree.ElementTree as ET

# ==========================================================================
#  ENGINE-KONFIGURATION
# ==========================================================================
ENGINES = {
    'art': {
        'label': "ART",
        'ext': ".arp",
        'bin': "ART-cli",
        'path_cfg': os.path.expanduser("~/.purelapse_art_path"),
        'tpl_cfg': os.path.expanduser("~/.purelapse_arp_template"),
        'base': os.path.expanduser("~/.purelapse_base.arp"),
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
        'path_cfg': os.path.expanduser("~/.purelapse_rt_path"),
        'tpl_cfg': os.path.expanduser("~/.purelapse_rt_template"),
        'base': os.path.expanduser("~/.purelapse_rt_base.pp3"),
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
        'path_cfg': os.path.expanduser("~/.purelapse_dt_path"),
        'tpl_cfg': os.path.expanduser("~/.purelapse_dt_template"),
        'base': os.path.expanduser("~/.purelapse_dt_base.xmp"),
        'extra': [],
        'kind': 'darktable',
        'wb_custom': "",
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
    """Pfad der Begleitdatei zu einem Bild - .arp, .pp3 oder .xmp."""
    return image_path + eng('ext')


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
    try:
        if os.path.getsize(xmp_pfad) > 8192:
            return False
        with open(xmp_pfad, 'r', encoding='utf-8', errors='ignore') as f:
            inhalt = f.read()
    except OSError:
        return False
    return 'darktable:' not in inhalt and 'darktable.org' not in inhalt


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
        if key == 'dt':
            # Nur echte Darktable-Sidecars zaehlen, nicht die
            # Bewertungsdateien, die Purelapse selbst anlegt.
            treffer = [p for p in treffer if not ist_reine_bewertung(p)]
        if treffer:
            gefunden.append(key)
    return gefunden[0] if len(gefunden) == 1 else None


def get_art_path():
    cfg = eng('path_cfg')
    if os.path.exists(cfg):
        with open(cfg, "r") as f:
            wert = f.read().strip()
        if wert:
            return wert
    return shutil.which(eng('bin')) or ""


def save_art_path(path):
    try:
        with open(eng('path_cfg'), "w") as f:
            f.write(path)
    except OSError:
        pass


def get_arp_template_path():
    cfg = eng('tpl_cfg')
    if os.path.exists(cfg):
        with open(cfg, "r") as f:
            return f.read().strip()
    return ""


def save_arp_template_path(path):
    try:
        with open(eng('tpl_cfg'), "w") as f:
            f.write(path)
    except OSError:
        pass


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
        with open(arp_path, "w", encoding="utf-8") as f:
            for sec in order:
                f.write(f"[{sec}]\n")
                for k, v in data[sec].items():
                    f.write(f"{k}={v}\n")
    except Exception as e:
        print(f"Fehler beim Speichern von {arp_path}: {e}")


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
#  Felder je Regler: Sektion, Schluessel, Minimum, Maximum, Neutralwert.
#  Minimum und Maximum sind die Grenzen der jeweiligen Engine; wo deren
#  Bereich fuer einen Schieberegler unbrauchbar weit ist (Gruenabgleich bis
#  100), steht in QUICK_CONTROLS ein engerer Bereich fuer die Bedienung.
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
        'sharpen':    ('Sharpening',    'Amount',      1,    1000,  200),
        'denoise_l':  ('Directional Pyramid Denoising', 'Luma',   0, 100, 0),
        'denoise_c':  ('Directional Pyramid Denoising', 'Chroma', 0, 100, 15),
    },
    # Darktable arbeitet mit XML-Modulen statt mit INI-Schluesseln; dort
    # gibt es die Schnelleinstellungen nicht.
    'dt': {},
}


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
}
HL_EMPFOHLEN = {'art': "Color", 'rt': "Coloropp", 'dt': ""}


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
        d['sec'], d['key'], d['min'], d['max'], d['neutral'] = eintrag
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
        (vorhanden if d['sec'] in (profile or {}) else fehlend).append(d)
    return vorhanden, fehlend


def quick_read(profile, engine=None):
    """Aktuelle Werte der Schnelleinstellungen aus einem Profil."""
    werte = {}
    for d in quick_defs(engine):
        roh = (profile or {}).get(d['sec'], {}).get(d['key'])
        try:
            # Listenwerte wie "512;0;0;0" -> erster Eintrag
            werte[d['id']] = float(str(roh).split(';')[0].strip())
        except (TypeError, ValueError):
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
        sek = profile.setdefault(d['sec'], {})
        if 'Enabled' in sek:
            sek['Enabled'] = "true"
        sek[d['key']] = (str(int(round(v))) if d['dezimal'] == 0
                         else f"{v:.{d['dezimal']}f}")
        geschrieben.append((d['sec'], d['key'], sek[d['key']]))
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
    """Schaltet die Defektpixel-Korrektur im Profil. Fuer Darktable (noch)
    ein bewusster No-Op - siehe Hinweis im Hauptprogramm, Worker._run_raw_pass1()."""
    if ENGINE == 'dt':
        return
    raw = arp_data.setdefault('RAW', {})
    raw['HotDeadPixelEnabled'] = "true" if enabled else "false"
    raw['HotPixelFilter'] = "true" if enabled else "false"
    raw['DeadPixelFilter'] = "true" if enabled else "false"
    raw.setdefault('HotDeadPixelThresh', "100")


def validate_arp(profile, reference, name):
    """Prueft ein geschriebenes Profil gegen ein von ART/RT stammendes Vorbild.
    Fuer Darktable nicht sinnvoll - liefert dann einfach eine leere Liste."""
    if ENGINE == 'dt':
        return []
    issues = []
    if not profile:
        return [f"{name}: Profil ist leer oder nicht lesbar"]
    secs = list(profile.keys())
    if 'Version' not in secs:
        issues.append(f"{name}: [Version] fehlt - {eng('label')} verwirft das Profil")
    elif secs[0] != 'Version':
        issues.append(f"{name}: [Version] steht an Position {secs.index('Version')+1} statt an erster Stelle")
    for sec in reference:
        if sec not in profile:
            issues.append(f"{name}: Sektion [{sec}] fehlt")
    for sec in profile:
        if sec not in reference:
            issues.append(f"{name}: Sektion [{sec}] ist zusaetzlich vorhanden")
    ref_order = [s for s in reference if s in profile]
    own_order = [s for s in profile if s in reference]
    if ref_order != own_order:
        issues.append(f"{name}: Sektionsreihenfolge weicht von der Vorlage ab")
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
                issues.append(f"{name}: [{sec}] {k} fehlt")
                continue
            want, got = _value_kind(ref_v), _value_kind(own[k])
            if want != got:
                issues.append(f"{name}: [{sec}] {k} ist '{got}' statt '{want}' "
                              f"(Wert '{str(own[k])[:40]}')")
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
    if not art_cli_path or not os.path.isfile(art_cli_path):
        return None, ""
    if not sample_image or not os.path.isfile(sample_image):
        return None, ""
    tmp = tempfile.mkdtemp(prefix="purelapse_tpl_")
    try:
        for args in (["-O", tmp], ["-o", tmp]):
            cmd = [art_cli_path] + args + ["-Y", "-j80"] + eng('extra') + ["-c", sample_image]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=300)
            except (OSError, subprocess.SubprocessError):
                continue
            found = sorted(glob.glob(os.path.join(tmp, '*' + eng('ext'))) +
                           glob.glob(os.path.join(tmp, "*.pp3")))
            for path in found:
                data = strip_rank(read_arp_dict_ini(path))
                if profile_is_complete(data):
                    write_arp_dict_ini(eng('base'), data)
                    save_arp_template_path(eng('base'))
                    return data, eng('base')
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
    if ENGINE != 'dt' and os.path.exists(arp_path):
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
_DT_NEUTRAL_BLEND = "gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU="
_DT_OWN_MULTI_NAME = "purelapse deflicker"
_KNOWN_EXPOSURE_VERSIONS = (6,)


def _dt_decode_exposure(hex_str, modversion):
    if modversion not in _KNOWN_EXPOSURE_VERSIONS:
        return None
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return None
    if len(raw) != _EXPOSURE_V6.size:
        return None
    return dict(zip(_EXPOSURE_V6_FIELDS, _EXPOSURE_V6.unpack(raw)))


def _dt_encode_exposure(fields):
    vals = (int(fields['mode']), float(fields['black']), float(fields['exposure']),
            float(fields['deflicker_percentile']), float(fields['deflicker_target_level']),
            int(fields['compensate_exposure_bias']))
    return _EXPOSURE_V6.pack(*vals).hex()


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


def _dt_get_current_ev(desc):
    entries = _dt_exposure_entries(desc)
    if not entries:
        return None
    li = entries[-1]
    if li.get(_qn(_DT, 'enabled')) != '1':
        return None
    fields = _dt_decode_exposure(
        li.get(_qn(_DT, 'params'), ''),
        int(li.get(_qn(_DT, 'modversion'), '0') or '0'))
    return fields['exposure'] if fields else None


def _dt_write_ev(xmp_path, ev_offset):
    """
    Schreibt den Deflicker-EV-Offset in die Darktable-XMP.
    - eigener 'purelapse deflicker'-Eintrag existiert schon -> Wert aktualisieren
    - sonst -> neue Modul-Instanz ans Ende der History anhaengen
    """
    tree, desc = _dt_load(xmp_path)
    if dt_has_custom_iop_order(desc):
        raise RuntimeError(
            f"{os.path.basename(xmp_path)}: benutzerdefinierte Modul-Reihenfolge "
            "(iop_order_list) gefunden - automatisches Schreiben wird uebersprungen."
        )
    seq = _dt_history_seq(desc)
    if seq is None:
        raise RuntimeError(f"{os.path.basename(xmp_path)}: kein <darktable:history> gefunden.")
    entries = _dt_exposure_entries(desc)
    own = next((li for li in entries
                if li.get(_qn(_DT, 'multi_name')) == _DT_OWN_MULTI_NAME), None)

    fields = {'mode': 0, 'black': 0.0, 'exposure': float(ev_offset),
              'deflicker_percentile': 50.0, 'deflicker_target_level': -4.0,
              'compensate_exposure_bias': 0}
    params_hex = _dt_encode_exposure(fields)

    if own is not None:
        own.set(_qn(_DT, 'params'), params_hex)
        own.set(_qn(_DT, 'enabled'), '1')
        own.set(_qn(_DT, 'modversion'), '6')
    else:
        all_nums = [int(li.get(_qn(_DT, 'num'), '0') or '0')
                    for li in seq.findall(_qn(_RDF, 'li'))]
        next_num = (max(all_nums) + 1) if all_nums else 0
        prios = [int(li.get(_qn(_DT, 'multi_priority'), '0') or '0') for li in entries]
        next_prio = (max(prios) + 1) if prios else 0

        li = ET.SubElement(seq, _qn(_RDF, 'li'))
        li.set(_qn(_DT, 'num'), str(next_num))
        li.set(_qn(_DT, 'operation'), 'exposure')
        li.set(_qn(_DT, 'enabled'), '1')
        li.set(_qn(_DT, 'modversion'), '6')
        li.set(_qn(_DT, 'params'), params_hex)
        li.set(_qn(_DT, 'multi_name'), _DT_OWN_MULTI_NAME)
        li.set(_qn(_DT, 'multi_name_hand_edited'), '0')
        li.set(_qn(_DT, 'multi_priority'), str(next_prio))
        li.set(_qn(_DT, 'blendop_version'), '13')
        li.set(_qn(_DT, 'blendop_params'), _DT_NEUTRAL_BLEND)

        cur_end = int(desc.get(_qn(_DT, 'history_end'), str(next_num)) or str(next_num))
        desc.set(_qn(_DT, 'history_end'), str(max(cur_end, next_num + 1)))

    tree.write(xmp_path, encoding='UTF-8', xml_declaration=True)


def read_arp_dict_dt(xmp_path):
    """Liest eine Darktable-XMP und liefert sie in DERSELBEN Dict-Form wie
    read_arp_dict_ini() zurueck (nur mit 'Exposure'/'Compensation' befuellt)."""
    if not os.path.exists(xmp_path):
        return {}
    try:
        _, desc = _dt_load(xmp_path)
    except (ET.ParseError, OSError):
        return {}
    ev = _dt_get_current_ev(desc)
    return {
        'Version': {'AppVersion': 'darktable-passthrough'},
        'Exposure': {
            'Enabled': 'true' if ev is not None else 'false',
            'Auto': 'false',
            'Compensation': f"{ev:.3f}" if ev is not None else '0.000',
        },
    }


def write_arp_dict_dt(xmp_path, data):
    """Schreibt nur den 'Exposure'/'Compensation'-Wert aus dem Shim-Dict
    zurueck in die echte Darktable-XMP - alles andere bleibt unberuehrt."""
    try:
        comp = float(data.get('Exposure', {}).get('Compensation', 0.0))
    except (TypeError, ValueError):
        comp = 0.0
    _dt_write_ev(xmp_path, comp)


def dt_build_cli_cmd(dt_cli_path, raw_path, xmp_path, out_jpg, quality=92):
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
            "--core",
            "--conf", f"plugins/imageio/format/jpeg/quality={quality}"]
    return cmd


# ==========================================================================
#  DISPATCHER: hier entscheidet sich, welche Implementierung laeuft
# ==========================================================================
def read_arp_dict(arp_path):
    if ENGINE == 'dt':
        return read_arp_dict_dt(arp_path)
    return read_arp_dict_ini(arp_path)


def write_arp_dict(arp_path, data):
    if ENGINE == 'dt':
        write_arp_dict_dt(arp_path, data)
    else:
        write_arp_dict_ini(arp_path, data)


def find_arp_template(target_dir, files=None):
    if ENGINE == 'dt':
        return {}, "(Darktable: kein Basisprofil erforderlich)"
    return find_arp_template_ini(target_dir, files)


def bootstrap_arp_template(art_cli_path, sample_image):
    if ENGINE == 'dt':
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
    if ENGINE != 'dt':
        automatik_einfrieren(data)
    write_arp_dict(arp_path, data)
