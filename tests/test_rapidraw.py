# -*- coding: utf-8 -*-
"""RapidRAW als Engine: .rrdata lesen/schreiben, Keyframes ueberblenden,
Sterne, Suche, Pass 1 und Pass 2 mit "RapidRAW export" (Nachbau),
Rueckfall ohne Verknuepfungen, Abbruch, zu alte Fassung, echte Vorschau."""
import os, sys, shutil, time, json, glob, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
import numpy as np, cv2
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

def rrdata(pfad, adj=None, sterne=0, tags=None, roh=None):
    """Eine .rrdata, wie RapidRAW sie schreibt (serde_json, eingerueckt)."""
    doc = {"version": 1, "rating": sterne, "adjustments": adj, "tags": tags}
    if roh is not None:
        text = roh
    else:
        text = json.dumps(doc, indent=2)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(text)

def laden(pfad):
    return json.load(open(pfad, encoding="utf-8"))

KURVE = [{"x": 0, "y": 0}, {"x": 128, "y": 120}, {"x": 255, "y": 255}]
def look(kontrast=10, ev=0.0, maske=False, wb=None, hue=0):
    adj = {"exposure": ev, "contrast": kontrast, "highlights": -20, "shadows": 15,
           "saturation": 5, "toneMapper": "agx", "baselineExposure": True,
           "activeTools": {"basic": True, "curves": True},
           "hsl": {"reds": {"hue": hue, "saturation": 0, "luminance": 0}},
           "curves": {"luma": [dict(p) for p in KURVE]},
           "whiteBalance": wb, "masks": [], "crop": None, "orientationSteps": 0}
    if maske:
        adj["masks"] = [{"id": "m1", "name": "Himmel", "adjustments": {"exposure": -0.5}}]
    return adj

o = os.path.join(ARBEIT, "rapidraw")
pe.set_engine('rr')

print("=== Begleitdatei, Erkennen, Zustand ===")
shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
nef = os.path.join(o, "IMG_0001.NEF")
pruef(pe.sidecar(nef) == nef + ".rrdata", "Name der Begleitdatei")
pruef(pe.rr_sidecar_bereit(pe.sidecar(nef)) == (False, "fehlt"), "fehlt")
rrdata(pe.sidecar(nef), None, sterne=3)
pruef(pe.rr_sidecar_bereit(pe.sidecar(nef)) == (False, "unbearbeitet"), "nur Sterne = unbearbeitet")
pruef(pe.detect_engine(o) == 'rr', f"Erkennung: {pe.detect_engine(o)}")
rrdata(pe.sidecar(nef), roh="{ kaputt")
pruef(pe.rr_sidecar_bereit(pe.sidecar(nef)) == (False, "nicht lesbar"), "unlesbar")
pruef(pe.read_arp_dict(pe.sidecar(nef)) == {}, "unlesbar ergibt leeres Profil")
try:
    pe.write_arp_dict(pe.sidecar(nef), {'Exposure': {'Compensation': '0.5'}})
    pruef(False, "eine unlesbare .rrdata wurde ueberschrieben")
except OSError as e:
    pruef("lesbare RapidRAW-Datei" in str(e), f"Meldung: {e}")
rrdata(pe.sidecar(nef), look(ev=0.4), sterne=2, tags=["Zeitraffer"])
pruef(pe.rr_sidecar_bereit(pe.sidecar(nef)) == (True, ""), "bereit")

print("=== Lesen und Schreiben ===")
f = pe.sidecar(nef)
d = pe.read_arp_dict(f)
pruef(pe.profile_is_complete(d), "vollstaendig")
pruef(abs(float(d['Exposure']['Compensation']) - 0.5) < 1e-6,
      f"Regler 0,4 = 0,5 Blenden: {d['Exposure']['Compensation']}")
pruef(d['rr']['hsl/reds/hue'] == '0' and d['rr']['contrast'] == '10', "verschachtelte Regler flach")
pruef('exposure' not in d['rr'], "Belichtung steht nur in Exposure")
pruef(json.loads(d['rr']['curves/luma']) == KURVE, "Kurve am Stueck")
vorher = laden(f)
pe.write_arp_dict(f, d)
nachher = laden(f)
pruef(nachher == vorher, "Lesen und Zurueckschreiben aendert nichts")
pe.set_exposure(d, 1.0)
pe.write_arp_dict(f, d)
n = laden(f)
pruef(abs(n['adjustments']['exposure'] - 0.8) < 1e-9, f"1 Blende = Regler 0,8: {n['adjustments']['exposure']}")
pruef(n['rating'] == 2 and n['tags'] == ["Zeitraffer"], "Sterne und Stichwoerter bleiben")
pe.write_arp_dict(f, {'Exposure': {'Compensation': '-0.25'}})
n = laden(f)
pruef(abs(n['adjustments']['exposure'] + 0.2) < 1e-9 and n['adjustments']['contrast'] == 10,
      "nur Belichtung: die uebrigen Regler bleiben")
a = look(); a['activeTools']['basic'] = False
rrdata(f, a)
pruef('basic_aus' in pe.rr_hinweise(pe.read_arp_dict(f)), "Hinweis: Grundeinstellungen aus")
pe.write_arp_dict(f, pe.read_arp_dict(f))
pruef(laden(f)['adjustments']['activeTools']['basic'] is True, "Grundeinstellungen fuer den Deflicker eingeschaltet")
rrdata(f, look(maske=True))
pruef('masken' in pe.rr_hinweise(pe.read_arp_dict(f)), "Hinweis: Masken")
neu = os.path.join(o, "IMG_0009.NEF.rrdata")
pe.write_arp_dict(neu, pe.read_arp_dict(f))
pruef(laden(neu)['version'] == 1 and laden(neu)['adjustments']['masks'][0]['id'] == 'm1',
      "neue Datei mit vollem Profil")

print("=== Sterne ===")
k = os.path.join(o, "IMG_0002.NEF")
pruef(not pe.check_is_keyframe(pe.sidecar(k)), "ohne Datei kein Keyframe")
pe.rr_bewertung_schreiben(pe.sidecar(k), 5)
pruef(pe.check_is_keyframe(pe.sidecar(k)), "Stern gesetzt")
pruef(laden(pe.sidecar(k))['adjustments'] is None, "Stern legt kein bearbeitetes Bild an")
pe.bewertung_schreiben(k + ".xmp", 0)
pruef(pe.check_is_keyframe(pe.sidecar(k)), "eine .xmp zaehlt bei RapidRAW nicht")
pe.rr_bewertung_schreiben(pe.sidecar(k), 0)
pruef(not pe.check_is_keyframe(pe.sidecar(k)), "Stern entfernt")
rrdata(pe.sidecar(k), look(), sterne=5)
pe.write_arp_dict(pe.sidecar(k), pe.strip_rank(pe.read_arp_dict(pe.sidecar(k))))
pruef(pe.check_is_keyframe(pe.sidecar(k)), "Schreiben des Profils behaelt den Stern")

print("=== Ueberblenden ===")
A = pe.read_arp_dict(pe.sidecar(k))
rrdata(pe.sidecar(k), look(kontrast=30, hue=20, maske=True,
                           wb={"temperature": 5200, "tint": 3}), sterne=5)
B = pe.read_arp_dict(pe.sidecar(k))
B['rr']['curves/luma'] = json.dumps([{"x": 0, "y": 10}, {"x": 128, "y": 140}, {"x": 255, "y": 245}])
pe.set_exposure(A, 0.0); pe.set_exposure(B, 1.0)
m = pe.interpolate_arp_dicts(A, B, 0.25)
pruef(m['rr']['contrast'] == '15', f"ganze Zahl bleibt ganz: {m['rr']['contrast']}")
pruef(m['rr']['hsl/reds/hue'] == '5', f"verschachtelt: {m['rr']['hsl/reds/hue']}")
kurve = json.loads(m['rr']['curves/luma'])
pruef(abs(kurve[1]['y'] - 125) < 1e-6 and abs(kurve[0]['y'] - 2.5) < 1e-6, f"Kurve weich: {kurve}")
pruef(m['rr']['masks'] == A['rr']['masks'], "Maske vom naeheren Keyframe (Anfang)")
pruef(m['rr'].get('whiteBalance') == 'null' and 'whiteBalance/temperature' not in m['rr'],
      "Weissabgleich null/Objekt: als Ganzes vom naeheren Keyframe")
m2 = pe.interpolate_arp_dicts(A, B, 0.75)
pruef(json.loads(m2['rr']['masks'])[0]['id'] == 'm1', "Maske vom naeheren Keyframe (Ende)")
pruef(m2['rr'].get('whiteBalance/temperature') == '5200' and 'whiteBalance' not in m2['rr'],
      "Weissabgleich vom Ende")
pruef(pe._rr_tief(m2['rr'])['whiteBalance'] == {"temperature": 5200, "tint": 3}, "Objekt wieder zusammengesetzt")
pruef(m['rr']['toneMapper'] == '"agx"' and m['rr']['activeTools'] == '{}', "Text und Werkzeuge")
harte = dict(pe.nicht_ueberblendbar(A, B))
pruef(set(h for _s, h in pe.nicht_ueberblendbar(A, B)) >= {'masks', 'whiteBalance'},
      f"nicht weich: {pe.nicht_ueberblendbar(A, B)}")
pruef(all(h not in ('contrast', 'curves/luma', 'hsl/reds/hue')
          for _s, h in pe.nicht_ueberblendbar(A, B)), "Zahlen und Kurven gelten als weich")
A2 = {s: dict(v) for s, v in A.items()}
A2['rr'] = {k: v for k, v in A2['rr'].items() if not k.startswith('activeTools')}
A2['rr']['activeTools'] = '{}'
pruef(all(not h.startswith('activeTools') for _s, h in pe.nicht_ueberblendbar(A, A2)),
      f"activeTools {{}} und alles eingeschaltet sind dasselbe: {pe.nicht_ueberblendbar(A, A2)}")
A3 = {s: dict(v) for s, v in A2.items()}
del A3['rr']['activeTools']; A3['rr']['activeTools/curves'] = 'false'
pruef(any(h.startswith('activeTools') for _s, h in pe.nicht_ueberblendbar(A2, A3)),
      "ausgeschaltetes Werkzeug wird als harter Wechsel gemeldet")
m3 = pe.interpolate_arp_dicts(A2, A3, 0.7)
pruef(pe._rr_tief(m3['rr'])['activeTools'] == {'curves': False}, f"Werkzeuge vom naeheren: {pe._rr_tief(m3['rr'])['activeTools']}")
C = {s: dict(v) for s, v in A.items()}
C['rr']['orientationSteps'] = '1'
pruef(pe.interpolate_arp_dicts(A, C, 0.4)['rr']['orientationSteps'] == '0'
      and pe.interpolate_arp_dicts(A, C, 0.6)['rr']['orientationSteps'] == '1',
      "Vierteldrehung wird nicht gemischt")

print("=== Schnelleinstellungen, Lichter, Pruefung ===")
q = pe.read_arp_dict(pe.sidecar(k))
vorh, fehl = pe.quick_available(q, 'rr')
pruef({d_['id'] for d_ in vorh} == {'contrast', 'highlights', 'shadows', 'vibrance',
                                     'saturation', 'denoise_l', 'denoise_c'} and not fehl,
      f"Regler: {[d_['id'] for d_ in vorh]}")
w = pe.quick_read(q, 'rr')
pruef(w['contrast'] == 30 and w['highlights'] == 20 and w['vibrance'] == 0,
      f"Werte: {w}")
pe.quick_apply(q, {'highlights': 35, 'contrast': 12.5}, 'rr')
pruef(q['rr']['highlights'] == '-35' and q['rr']['contrast'] == '12.5', f"geschrieben: {q['rr']}")
pruef(not pe.hl_optionen('rr') and pe.validate_arp(q, q, "x") == [], "keine Lichter-Rekonstruktion, keine INI-Pruefung")
h = {s: dict(v) for s, v in q.items()}
pe.set_raw_hotpixel(h, True)
pruef(h == q, "Hotpixel: RapidRAW macht das selbst")
pruef(pe.bootstrap_arp_template(RR_CLI, nef) == (None, ""), "kein Basisprofil zu erzeugen")

print("=== Vorlage ===")
v = os.path.join(ARBEIT, "rapidraw_vorlage")
shutil.rmtree(v, ignore_errors=True); os.makedirs(v)
bilder = [os.path.join(v, f"IMG_{i:04d}.NEF") for i in range(4)]
pruef(pe.find_arp_template(v, bilder) == (None, ""), "ohne Bearbeitung keine Vorlage")
rrdata(bilder[0] + ".rrdata", None, sterne=5)
rrdata(bilder[1] + ".rrdata", look(kontrast=11))
rrdata(bilder[3] + ".rrdata", look(kontrast=33), sterne=5)
vl, quelle = pe.find_arp_template(v, bilder)
pruef(quelle == bilder[3] + ".rrdata" and vl['rr']['contrast'] == '33', f"Keyframe zuerst: {quelle}")

print("=== Programm finden, Flatpak, Aufrufe ===")
bindir = os.path.join(ARBEIT, "rr_bin")
shutil.rmtree(bindir, ignore_errors=True); os.makedirs(bindir)
klein = os.path.join(bindir, "rapidraw")
open(klein, "w").write("#!/bin/sh\n"); os.chmod(klein, 0o755)
alt_path = os.environ.get("PATH", "")
os.environ["PATH"] = bindir + os.pathsep + alt_path
try:
    if os.name != 'nt':
        pruef(pe.engine_suchen('rr') == klein, f"Arch-Name rapidraw: {pe.engine_suchen('rr')}")
finally:
    os.environ["PATH"] = alt_path
win = os.path.join(ARBEIT, "rr_win")
shutil.rmtree(win, ignore_errors=True)
os.makedirs(os.path.join(win, "lokal", "RapidRAW"))
exe = os.path.join(win, "lokal", "RapidRAW", "RapidRAW.exe")
open(exe, "w").write("")
pruef(pe.engine_suchen('rr', umgebung={'LOCALAPPDATA': os.path.join(win, "lokal")}, nt=True,
                       suchpfad=False) == exe, "Windows: %LOCALAPPDATA%\\RapidRAW")
pruef(pe.FLATPAK_IDS['rr'] == "io.github.CyberTimon.RapidRAW", "Flatpak-ID")
raw_dir = os.path.join(ARBEIT, "rr_fp", "bilder")
os.makedirs(os.path.join(raw_dir, "Purelapse", "x"), exist_ok=True)
cmd = pe.engine_befehl(pe.rr_export_befehl("flatpak:io.github.CyberTimon.RapidRAW",
                                           os.path.join(raw_dir, "Purelapse", "x"),
                                           os.path.join(raw_dir, "Purelapse", "y")),
                       freigaben=[raw_dir])
pruef(cmd[:3] == ["flatpak", "run", "--command=RapidRAW"], f"Flatpak-Aufruf: {cmd[:3]}")
pruef([c for c in cmd if c.startswith("--filesystem")] == [f"--filesystem={raw_dir}"],
      f"Freigabe des Bilderordners: {[c for c in cmd if c.startswith('--filesystem')]}")
pruef(pe.rr_export_befehl("R", "q", "z") == ["R", "export", "q", "--output", "z", "--format", "jpeg",
                                            "--quality", "100", "--keep-metadata"], "JPG-Aufruf")
pruef(pe.rr_export_befehl("R", "q", "z", tief=True)[5:9] == ["--format", "tiff", "--tiff-bit-depth", "16"],
      "16-Bit-Aufruf")
pruef(pe.rr_ausgabe_stamm("IMG_0001_edited.jpeg") == "IMG_0001"
      and pe.rr_ausgabe_stamm("IMG_0001_edited.tiff") == "IMG_0001"
      and pe.rr_ausgabe_stamm("IMG_0001.jpeg") is None
      and pe.rr_ausgabe_stamm("IMG_0001_edited.rrdata") is None, "Ausgabenamen")

print("=== Verknuepfen ===")
q_dir = os.path.join(v, "Purelapse", ".rapidraw_quelle")
for b in bilder:
    open(b, "wb").write(b"x")
    if not os.path.exists(b + ".rrdata"):
        rrdata(b + ".rrdata", look())
art = pm.rr_verknuepfen(bilder[:2], q_dir)
pruef(art in ('hart', 'symbolisch') and sorted(os.listdir(q_dir)) ==
      sorted(os.path.basename(x) for b in bilder[:2] for x in (b, b + ".rrdata")),
      f"Verknuepfungen: {art} {os.listdir(q_dir) if os.path.isdir(q_dir) else '-'}")
alt_link, alt_sym = os.link, os.symlink
def nein(*_a, **_k): raise OSError(1, "nicht erlaubt")
os.link = os.symlink = nein
try:
    pruef(pm.rr_verknuepfen(bilder[:2], q_dir) == '' and not os.path.exists(q_dir),
          "ohne Verknuepfungen: leer und aufgeraeumt")
finally:
    os.link, os.symlink = alt_link, alt_sym

print("=== Ablauf: Pass 1, Pass 2 ===")
N = 30
ordner = os.path.join(ARBEIT, "rapidraw_lauf")
dateien, _ = szene(ordner, n=N, flackern=0.07)
for f_ in dateien:
    os.utime(f_, (1651474098, 1651474098))      # aufgenommen am 2. Mai 2022
par = dict(engine='rr', art_cli_path=RR_CLI)
e = lauf(parameter(ordner, dateien, raw_mode='pass1', **par))
pruef(e.fehler and "RapidRAW-Bearbeitung" in e.fehler[0], f"ohne Bearbeitung: {e.fehler}")
rrdata(pe.sidecar(dateien[4]), look(kontrast=10), sterne=5, tags=["Anfang"])
rrdata(pe.sidecar(dateien[24]), look(kontrast=30, maske=True), sterne=5)
e = lauf(parameter(ordner, dateien, raw_mode='pass1', **par))
pruef(e.ok(), f"Pass 1: {e.fehler}")
pruef(all(pe.rr_sidecar_bereit(pe.sidecar(f))[0] for f in dateien), "Pass 1 legt alle .rrdata an")
evs = [laden(pe.sidecar(f))['adjustments']['exposure'] for f in dateien]
pruef(np.std(evs) > 0.04, f"Pass 1 hat keine Belichtung geschrieben: {evs[:4]}")
pruef(laden(pe.sidecar(dateien[4]))['tags'] == ["Anfang"] and pe.check_is_keyframe(pe.sidecar(dateien[4])),
      "Keyframe behaelt Sterne und Stichwoerter")
e = lauf(parameter(ordner, dateien, raw_mode='pass2', **par))
pruef(e.ok(), f"Pass 2: {e.fehler}")
zw = pl(ordner, "Deflickered_JPG")
pruef(len(glob.glob(os.path.join(zw, "*.jpg"))) == N, f"Zwischenbilder: {len(glob.glob(os.path.join(zw, '*.jpg')))}")
pruef(not os.path.exists(os.path.join(zw, ".rapidraw_quelle"))
      and not os.path.exists(os.path.join(zw, ".rapidraw_ausgabe")), "Arbeitsordner aufgeraeumt")
fl, n = ordner_flackern(zw)
pruef(n == N and fl < 0.005, f"Flackern nach RapidRAW: {fl:.4f} EV")
alt_bild = min(os.path.getmtime(x) for x in glob.glob(os.path.join(zw, "*.jpg")))
pruef(alt_bild > time.time() - 600,
      "Zwischenbilder tragen das Datum von jetzt, nicht das der Aufnahme")
pruef(len(videos(ordner)) == 1, f"Video: {videos(ordner)}")
pruef(any("RAPIDRAW-EXPORT" in z for z in e.log) and any(" export " in z for z in e.log), "Aufruf im Protokoll")
mitte = laden(pe.sidecar(dateien[14]))['adjustments']
pruef(abs(mitte['contrast'] - 20) < 0.01, f"Kontrast in der Mitte: {mitte['contrast']}")
pruef(laden(pe.sidecar(dateien[14]))['rating'] == 0, "Zwischenbild wurde kein Keyframe")
pruef(laden(pe.sidecar(dateien[12]))['adjustments']['masks'] == []
      and len(laden(pe.sidecar(dateien[16]))['adjustments']['masks']) == 1, "Maske wechselt in der Mitte")
pruef(any("Masken oder KI-Retusche" in z for z in e.log), "Hinweis auf Masken im Protokoll")
pruef(pm.ablauf_plan({'format': 'raw', 'raw_mode': 'pass2', 'engine': 'rr', 'stabilize': False,
                      'calib_rounds': 2})[:3] == ['entwicklung', 'messung', 'kalib'], "Ablaufplan")

print("=== 16 Bit ===")
e = lauf(parameter(ordner, dateien, raw_mode='pass2', tiff16=True, **par))
tifs = glob.glob(os.path.join(zw, "*.tif"))
pruef(e.ok() and len(tifs) == N, f"16-Bit-TIFFs: {len(tifs)} {e.fehler}")
if tifs:
    pruef(cv2.imread(tifs[0], cv2.IMREAD_UNCHANGED).dtype == np.uint16, "TIFF ist 16 Bit")

print("=== Ohne Verknuepfungen: jedes Bild einzeln ===")
o2 = os.path.join(ARBEIT, "rapidraw_einzeln")
d2, _ = szene(o2, n=12, flackern=0.07, seed=3)
rrdata(pe.sidecar(d2[0]), look(), sterne=5)
alt_v = pm.rr_verknuepfen
pm.rr_verknuepfen = lambda dateien_, ordner_: ''
try:
    e = lauf(parameter(o2, d2, raw_mode='pass1', **par))
    e = lauf(parameter(o2, d2, raw_mode='pass2', **par))
finally:
    pm.rr_verknuepfen = alt_v
pruef(e.ok() and len(glob.glob(os.path.join(pl(o2, "Deflickered_JPG"), "*.jpg"))) == 12,
      f"einzeln: {e.fehler}")
pruef(any("jedes Bild einzeln" in z for z in e.log), "Rueckfall wird gemeldet")

print("=== Abbruch, dann Fortsetzung ===")
o3 = os.path.join(ARBEIT, "rapidraw_abbruch")
d3, _ = szene(o3, n=40, flackern=0.07, seed=5)
rrdata(pe.sidecar(d3[0]), look(), sterne=5)
e = lauf(parameter(o3, d3, raw_mode='pass1', make_video=False, **par))
os.environ["FAKE_VERZOEGERUNG"] = "0.08"
e = lauf(parameter(o3, d3, raw_mode='pass2', **par),
         vor_start=lambda w: threading.Timer(1.5, lambda: setattr(w, '_abort', True)).start())
os.environ["FAKE_VERZOEGERUNG"] = "0"
pruef(not e.fertig and "abgebrochen" in " ".join(e.fehler).lower(), f"Abbruch: {e.fehler}")
zw3 = pl(o3, "Deflickered_JPG")
n_teil = len(glob.glob(os.path.join(zw3, "*.jpg")))
pruef(0 < n_teil < 40, f"Abbruchzeitpunkt: {n_teil}")
pruef(not os.path.exists(os.path.join(zw3, ".rapidraw_ausgabe")), "Arbeitsordner nach Abbruch aufgeraeumt")
reste = prozesse_mit(RR_CLI)
pruef(not reste, f"nach dem Abbruch laeuft RapidRAW nicht mehr: {reste}")
e = lauf(parameter(o3, d3, raw_mode='pass2', **par))
pruef(e.ok() and any(f"Fortsetzung: {n_teil} von 40" in z for z in e.log),
      f"Fortsetzung uebernimmt {n_teil}: {[z for z in e.log if 'Fortsetzung' in z]}")

# Fertige Bilder erscheinen schon waehrend des Laufs im Ausgabeordner
zw_t = os.path.join(ARBEIT, "rr_takt"); shutil.rmtree(zw_t, ignore_errors=True); os.makedirs(zw_t)
gesehen = []
os.environ["FAKE_VERZOEGERUNG"] = "0.15"
try:
    pm.rr_export_lauf(RR_CLI, d3[:12], zw_t,
                      takt=lambda n_: gesehen.append((n_, len(glob.glob(os.path.join(zw_t, "*.jpg"))))))
finally:
    os.environ["FAKE_VERZOEGERUNG"] = "0"
pruef(any(0 < a_ < 12 and a_ == b_ for a_, b_ in gesehen), f"waehrend des Laufs sichtbar: {gesehen[:8]}")
pruef(len(glob.glob(os.path.join(zw_t, "*.jpg"))) == 12 and not os.path.exists(os.path.join(zw_t, ".rapidraw_ausgabe")),
      "am Ende alle da, Arbeitsordner weg")

print("=== Zu alte Fassung (ohne export) ===")
alt_skript = os.path.join(ARBEIT, "RapidRAW_alt.py")
with open(alt_skript, "w") as f_:
    f_.write("#!/usr/bin/env python3\nimport time\nwhile True:\n    time.sleep(1)\n")
alt_cli = ausfuehrbar(alt_skript)
alt_grenze = pm.RR_STILLSTAND_SEK
pm.RR_STILLSTAND_SEK = 2
try:
    e = lauf(parameter(o2, d2, raw_mode='pass2', engine='rr', art_cli_path=alt_cli))
finally:
    pm.RR_STILLSTAND_SEK = alt_grenze
# Die Bilder sind aktuell: nichts zu entwickeln. Erst nach einer Aenderung
# muss die alte Fassung ran.
d_ = pe.read_arp_dict(pe.sidecar(d2[0])); d_['rr']['contrast'] = '44'
pe.write_arp_dict(pe.sidecar(d2[0]), d_)
pm.RR_STILLSTAND_SEK = 2
try:
    t0 = time.time()
    e = lauf(parameter(o2, d2, raw_mode='pass2', engine='rr', art_cli_path=alt_cli))
    dauer = time.time() - t0
finally:
    pm.RR_STILLSTAND_SEK = alt_grenze
pruef(e.fehler and "RapidRAW 1.6" in e.fehler[0] and dauer < 60, f"alte Fassung: {e.fehler} ({dauer:.0f} s)")
pruef(not prozesse_mit(alt_cli), "die alte Fassung laeuft nicht weiter")

print("=== Echte Vorschau ===")
erg = []
prof = pe.read_arp_dict(pe.sidecar(dateien[10]))
vorher_text = open(pe.sidecar(dateien[10])).read()
fv = pm.EngineVorschau(RR_CLI, dateien[10], prof, "x", kante=120)
fv.fertig.connect(erg.append); fv.start()
r = erg[-1] if erg else {}
pruef(r.get('rgb') is not None and max(r['rgb'].shape[:2]) == 120, f"Vorschau: {r.get('fehler')}")
pruef(open(pe.sidecar(dateien[10])).read() == vorher_text, "die Vorschau fasst die .rrdata nicht an")
hell = {s: dict(w_) for s, w_ in prof.items()}
pe.set_exposure(hell, float(prof['Exposure']['Compensation']) + 1.0)
erg2 = []
fv = pm.EngineVorschau(RR_CLI, dateien[10], hell, "y", kante=120)
fv.fertig.connect(erg2.append); fv.start()
pruef(erg2 and erg2[-1]['rgb'] is not None and erg2[-1]['rgb'].mean() > r['rgb'].mean() * 1.15,
      "Belichtung kommt in der Vorschau an")

print("=== Bildleiste: entwickelte Bilder ===")
pe.set_engine('rr')
fertig = pm.entwickelte_vorschau(ordner, dateien)
pruef(len(fertig) == N and all(x.endswith(".tif") for x in fertig.values()),
      f"nach Pass 2 (16 Bit) alle entwickelt: {len(fertig)}")
d_ = pe.read_arp_dict(pe.sidecar(dateien[7])); d_['rr']['saturation'] = '33'
pe.write_arp_dict(pe.sidecar(dateien[7]), d_)
fertig = pm.entwickelte_vorschau(ordner, dateien)
pruef(dateien[7] not in fertig and len(fertig) == N - 1, "geaendertes Profil: Zwischenbild gilt nicht mehr")
pruef(pm.entwickelte_vorschau(o2, [x + ".jpg" for x in d2]) == {}, "JPG-Serien: nichts")
# Lightroom: der Export zaehlt, wenn er juenger als die XMP ist
pe.set_engine('lr')
o4 = os.path.join(ARBEIT, "bildleiste_lr")
d4, _ = szene(o4, n=3)
for x in d4:
    open(pe.sidecar(x), "w").write("<x/>")
exp = pm.lr_export_ordner(o4); os.makedirs(exp, exist_ok=True)
for x in d4[:2]:
    cv2.imwrite(os.path.join(exp, os.path.splitext(os.path.basename(x))[0] + ".jpg"),
                np.full((20, 30, 3), 128, np.uint8))
os.utime(pe.sidecar(d4[1]), (time.time() + 60, time.time() + 60))
fl_ = pm.entwickelte_vorschau(o4, d4)
pruef(list(fl_) == [d4[0]], f"Lightroom: nur aktueller Export: {[os.path.basename(x) for x in fl_]}")
pe.set_engine('rr')
# Fenster: Keyframes kommen schon vor Pass 1 von RapidRAW
o5 = os.path.join(ARBEIT, "bildleiste_rr")
d5, _ = szene(o5, n=12, seed=7)
rrdata(pe.sidecar(d5[2]), look(kontrast=40), sterne=5)
rrdata(pe.sidecar(d5[9]), look(), sterne=0)
shutil.rmtree(os.path.join(pm.cache_ordner(), "bildleiste"), ignore_errors=True)
w = pm.MainWindow(); w.cmb_engine.setCurrentIndex(4); pe.set_engine('rr')
w.txt_art_path.setText(RR_CLI); w.rb_raw.setChecked(True)
w._set_folder(o5); pe.set_engine('rr')
kachel = {t_['name']: t_ for t_ in w.tiles}
k2 = kachel[os.path.basename(d5[2])]
pruef("RapidRAW" in (k2['img'].toolTip() or ""), f"Keyframe zeigt RapidRAWs Bild: {k2['img'].toolTip()}")
pruef(not kachel[os.path.basename(d5[9])]['img'].toolTip(), "bearbeitet, aber kein Keyframe: Kamerabild")
pruef(not kachel[os.path.basename(d5[4])]['img'].toolTip(), "unbearbeitet: Kamerabild")
cache = pm.bildleiste_cache(d5[2])
pruef(os.path.exists(cache), "Vorschau abgelegt")
zeit = os.path.getmtime(cache)
time.sleep(0.05)
w._set_folder(o5); pe.set_engine('rr')
pruef(os.path.getmtime(cache) == zeit, "erneutes Einlesen nimmt die abgelegte Vorschau")
w.tiles[5]['chk'].setChecked(True)
pruef(not w.tiles[5]['img'].toolTip(), "Stern auf unbearbeitetem Bild: weiter das Kamerabild")
rrdata(pe.sidecar(d5[6]), look(kontrast=-30))
w.tiles[6]['chk'].setChecked(True)
pruef("RapidRAW" in (w.tiles[6]['img'].toolTip() or ""), "neuer Stern auf bearbeitetem Bild: sofort RapidRAWs Bild")
pruef(pm.bildleiste_cache(d5[6]) != pm.bildleiste_cache(d5[2]), "je Bild eine eigene Vorschau")
alt_c = pm.bildleiste_cache(d5[6])
d_ = pe.read_arp_dict(pe.sidecar(d5[6])); d_['rr']['contrast'] = '10'
pe.write_arp_dict(pe.sidecar(d5[6]), d_)
pruef(pm.bildleiste_cache(d5[6]) != alt_c, "geaenderte .rrdata ergibt eine neue Vorschau")
pruef(not glob.glob(os.path.join(pm.cache_ordner(), "bildleiste", "bildleiste_*")),
      "Arbeitsordner der Bildleiste aufgeraeumt")

print("=== Oberflaeche und Texte ===")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef(pm.ENGINE_REIHE[:4] == ('art', 'rt', 'dt', 'lr') and pm.ENGINE_REIHE[4] == 'rr',
      "Reihenfolge (gespeicherte Stellen)")
pruef("rr_bewertung_schreiben(arp_path" in src, "Stern in der Bildleiste schreibt in die .rrdata")
pruef("vorlage is None and eng('kind') == 'rapidraw'" in src,
      "Keyframe einstellen ohne RapidRAW-Bearbeitung: eigener Hinweis statt \"Pass 1 laufen lassen\"")
import purelapse_texte as tx
pruef(pm.RR_HINWEIS_KURZ['de'] in tx.TRANSLATIONS, "Hinweistext ohne Uebersetzung")
pruef("RapidRAW" in tx.TRANSLATIONS_TT_EN["TT_ENGINE"], "Tooltip nennt RapidRAW")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
