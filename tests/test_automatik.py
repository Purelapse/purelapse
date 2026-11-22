# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Bildweise Automatik der Engines: finden, einfrieren, im Ablauf pruefen."""
import os, sys, io, glob, subprocess, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
import cv2

OK = FEHL = 0
def pruef(b, text):
    global OK, FEHL
    if b: OK += 1
    else:
        FEHL += 1; print("  FEHLER:", text)
def O(name): return os.path.join(ARBEIT, name)
def leeren():
    for alt in glob.glob(os.path.join(pe.daten_ordner(), "basis_*")):
        os.remove(alt)
    for k in ('art', 'rt', 'dt'):
        pe.konfig_setzen('engines', k, 'profil', None)

print("=== 1. Erkennen und Einfrieren (RawTherapee) ===")
pe.set_engine('rt')
def rt(**exp):
    d = {'Version': {'Version': '346'}, 'General': {}, 'Exposure': {'Auto': 'false', 'Compensation': '0.1',
         'Brightness': '0', 'Contrast': '0'}, 'White Balance': {'Setting': 'Camera'}}
    d['Exposure'].update(exp); return d
p = rt(HistogramMatching='true', CurveFromHistogramMatching='false', Curve='0;', CurveMode='Standard')
pruef(pe.automatik_finden(p) == ['tonkurve'], f"Auto-Kurve nicht erkannt: {pe.automatik_finden(p)}")
pruef(pe.automatik_einfrieren(p) == ['tonkurve'], "Einfrieren meldet nichts")
pruef(p['Exposure']['HistogramMatching'] == 'false', "HistogramMatching bleibt an")
pruef(p['Exposure']['Curve'] == pe.FILMKURVE['rt'][1] and p['Exposure']['CurveMode'] == 'FilmLike',
      "Filmkurve nicht eingesetzt")
pruef(p['Exposure']['Compensation'] == '0.1', "die Belichtung wurde angefasst")
pruef(pe.automatik_finden(p) == [] and pe.automatik_einfrieren(p) == [], "zweiter Durchgang aendert noch etwas")
p = rt()                                   # Schluessel fehlt: mit -d gilt das Standardprofil
pruef(pe.automatik_finden(p) == ['tonkurve'], "fehlender Schluessel gilt bei RawTherapee nicht als Automatik")
pe.automatik_einfrieren(p)
pruef(p['Exposure']['HistogramMatching'] == 'false', "fehlender Schluessel wird nicht ausdruecklich gesetzt")
eigene = "1;0;0;0.2;0.15;0.8;0.9;1;1;"
p = rt(HistogramMatching='true', CurveFromHistogramMatching='false', Curve=eigene, CurveMode='Standard')
pe.automatik_einfrieren(p)
pruef(p['Exposure']['Curve'] == eigene and p['Exposure']['CurveMode'] == 'Standard',
      "eine vorhandene eigene Kurve wird ueberschrieben")
p = rt(HistogramMatching='true', CurveFromHistogramMatching='true', Curve=eigene, CurveMode='Standard', Curve2='1;0;0;1;1;')
pruef(pe.automatik_finden(p) == ['tonkurve_fest'], "festgeschriebene Auto-Kurve nicht erkannt")
pe.automatik_einfrieren(p)
pruef(p['Exposure']['Curve'] == eigene, "festgeschriebene Kurve veraendert")
pruef(p['Exposure']['HistogramMatching'] == 'false' and p['Exposure']['CurveMode'] == 'FilmLike'
      and p['Exposure']['Curve2'] == '0;', "festgeschriebene Kurve nicht aus dem Auto-Modus geloest")
p = rt(HistogramMatching='false', Curve='0;')
pruef(pe.automatik_finden(p) == [] and pe.automatik_einfrieren(p) == [] and p['Exposure']['Curve'] == '0;',
      "eine bewusst lineare Kurve wird angefasst")
duenn = {'Exposure': {'Compensation': '0.2'}}
pruef(pe.automatik_einfrieren(duenn) == [] and duenn == {'Exposure': {'Compensation': '0.2'}},
      "ein unvollstaendiges Profil wird veraendert")

print("=== 2. Erkennen und Einfrieren (ART) ===")
pe.set_engine('art')
def art(tc=None, log=None):
    d = {'Version': {'Version': '1040'}, 'General': {}, 'Exposure': {'Compensation': '0'},
         'White Balance': {'Setting': 'Camera'}}
    if tc is not None: d['ToneCurve'] = tc
    if log is not None: d['LogEncoding'] = log
    return d
p = art({'Enabled': 'true', 'HistogramMatching': 'true', 'CurveMode': 'Neutral', 'Curve2': '0;'})
pruef(pe.automatik_finden(p) == ['tonkurve'], "ART: Auto-Kurve nicht erkannt")
pe.automatik_einfrieren(p)
pruef(p['ToneCurve']['HistogramMatching'] == 'false' and p['ToneCurve']['Curve'] == pe.FILMKURVE['art'][1]
      and p['ToneCurve']['CurveMode'] == 'Neutral', f"ART: nicht eingefroren: {p['ToneCurve']}")
pruef('HistogramMatching' not in p['Exposure'], "ART: Schluessel in die falsche Sektion geschrieben")
p = art({'Enabled': 'true', 'HistogramMatching': 'true', 'CurveFromHistogramMatching': 'true', 'Curve': eigene})
vorher = dict(p['ToneCurve'])
pruef(pe.automatik_finden(p) == [] and pe.automatik_einfrieren(p) == [] and p['ToneCurve'] == vorher,
      "ART: in der Oberflaeche festgeschriebene Kurve wird angefasst")
p = art()                                  # ohne -d: fehlende Sektion heisst aus
pruef(pe.automatik_finden(p) == [] and 'ToneCurve' not in p, "ART: fehlende Sektion gilt als Automatik")
p = art({'Enabled': 'true', 'Curve': '0;'})
pruef(pe.automatik_finden(p) == [], "ART: fehlender Schluessel gilt als Automatik")
p = art({'Enabled': 'false', 'HistogramMatching': 'true'})
pruef(pe.automatik_finden(p) == [], "ART: abgeschaltete Tonkurve gemeldet")
p = art(log={'Enabled': 'true', 'Auto': 'true', 'Gain': '1.5'})
pruef(pe.automatik_finden(p) == ['log'], "ART: Log-Automatik nicht erkannt")
pe.automatik_einfrieren(p)
pruef(p['LogEncoding'] == {'Enabled': 'true', 'Auto': 'false', 'Gain': '1.5'}, "ART: Log-Automatik nicht abgeschaltet")
p = art(log={'Enabled': 'false', 'Auto': 'true'})
pruef(pe.automatik_finden(p) == [], "ART: abgeschaltetes Log-Mapping gemeldet")
pe.set_engine('dt')
pruef(pe.automatik_finden({'Version': {}, 'Exposure': {'HistogramMatching': 'true'}}) == [], "Darktable betroffen")

print("=== 3. Harte Umschaltungen zwischen Keyframes ===")
pe.set_engine('rt')
a = rt(Curve="1;0;0;0.5;0.5;1;1;", CurveMode='Standard', Brightness='0')
b = rt(Curve="1;0;0;0.5;0.6;1;1;", CurveMode='Standard', Brightness='30')
pruef(pe.nicht_ueberblendbar(a, b) == [], f"gleich lange Kurven gelten als hart: {pe.nicht_ueberblendbar(a, b)}")
b['Exposure']['Curve'] = "1;0;0;0.3;0.2;0.7;0.8;1;1;"
pruef(pe.nicht_ueberblendbar(a, b) == [('Exposure', 'Curve')], f"verschieden lange Kurven nicht gemeldet: {pe.nicht_ueberblendbar(a, b)}")
b['Exposure']['Curve'] = a['Exposure']['Curve']; b['Exposure']['CurveMode'] = 'FilmLike'
pruef(pe.nicht_ueberblendbar(a, b) == [('Exposure', 'CurveMode')], "Textwert nicht gemeldet")
b['Exposure']['CurveMode'] = 'Standard'; b['White Balance']['Setting'] = 'Custom'
pruef(pe.nicht_ueberblendbar(a, b) == [], "Weissabgleich-Umstellung faelschlich gemeldet")

print("=== 4. Ablauf: Profile aus einer aelteren Version (Automatik noch an) ===")
N = 60
for engine, cli, sek in (('rt', RT_CLI, 'Exposure'), ('art', ART_CLI, 'ToneCurve')):
    o = O("auto_" + engine); d, _ = szene(o, n=N); leeren()
    pe.set_engine(engine)
    if engine == 'art':
        t = tempfile.mkdtemp()
        subprocess.run([cli, "-O", t, "-d", "-Y", "-c", d[0]], capture_output=True)
        pe.save_arp_template_path(glob.glob(t + "/*.arp")[0])
    e1 = lauf(parameter(o, d, raw_mode='pass1', make_video=False, art_cli_path=cli, engine=engine))
    pruef(e1.ok(), f"{engine}: Pass 1 scheitert")
    prof = [pe.read_arp_dict(pe.sidecar(f)) for f in d]
    pruef(all(p[sek].get('HistogramMatching') == 'false' for p in prof),
          f"{engine}: Pass 1 schreibt Profile mit Auto-Kurve")
    # Zustand wie nach einer aelteren Version herstellen
    for f in d:
        p = pe.read_arp_dict(pe.sidecar(f))
        p[sek]['HistogramMatching'] = 'true'; p[sek]['Curve'] = '0;'
        pe.write_arp_dict(pe.sidecar(f), p)
    for i, hell in ((10, 0), (40, 30)):
        p = pe.read_arp_dict(pe.sidecar(d[i]))
        pe.quick_apply(p, {'saturation': 20, 'brightness': hell})
        pe.write_arp_dict(pe.sidecar(d[i]), p)
        io.open(d[i] + ".xmp", "w").write('<x xmp:Rating="5"></x>')
    e2 = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=cli, engine=engine))
    pruef(e2.ok(), f"{engine}: Pass 2 scheitert: {e2.fehler[:1]}")
    zeilen = [z for z in e2.log if "Auto-angepasste Tonkurve" in z]
    pruef(len(zeilen) == 1 and f"in {N} Profilen" in zeilen[0], f"{engine}: Meldung fehlt oder falsch: {zeilen}")
    prof = [pe.read_arp_dict(pe.sidecar(f)) for f in d]
    pruef(all(p[sek]['HistogramMatching'] == 'false' for p in prof), f"{engine}: nicht alle Profile eingefroren")
    pruef(len({p[sek]['Curve'] for p in prof}) == 1 and prof[0][sek]['Curve'] == pe.FILMKURVE[engine][1],
          f"{engine}: die Bilder haben nicht alle dieselbe Kurve")
    out = os.path.join(o, "Purelapse", "Deflickered_JPG")
    fl, n = ordner_flackern(out); him, vor = tonwert_flackern(out)
    pruef(n == N and fl < 0.005, f"{engine}: Flackern gesamt {fl:.4f}")
    pruef(him < 0.005 and vor < 0.005, f"{engine}: Himmel {him:.4f}, Vordergrund {vor:.4f}")
    jp = sorted(glob.glob(out + "/*.jpg"))
    ev = [helligkeit_ev(cv2.imread(x)) for x in jp]
    pruef(ev[40] - ev[10] > 0.3, f"{engine}: Helligkeit des Keyframes kommt nicht an ({ev[40]-ev[10]:+.2f})")
    pruef(not any("ueberblenden" in z for z in e2.log), f"{engine}: Fehlalarm harte Umschaltung")
    print(f"   {engine}: gesamt {fl:.4f}, Himmel {him:.4f}, Vordergrund {vor:.4f} EV")
    # zweiter Lauf: nichts mehr zu tun, keine Meldung, keine Neuentwicklung
    e3 = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=cli, engine=engine))
    pruef(e3.ok() and not any("Auto-angepasste" in z for z in e3.log), f"{engine}: zweiter Lauf meldet erneut")
    pruef(any("wird uebersprungen" in z or "Alle Bilder sind aktuell" in z for z in e3.log),
          f"{engine}: zweiter Lauf entwickelt neu")

print("=== 5. Ablauf: Keyframes mit verschiedenen Kurven werden gemeldet ===")
pe.set_engine('rt')
p = pe.read_arp_dict(pe.sidecar(d[40])) if False else None
o = O("auto_rt"); d = sorted(glob.glob(o + "/*.NEF"))
p = pe.read_arp_dict(pe.sidecar(d[40])); p['Exposure']['Curve'] = "1;0;0;0.5;0.5;1;1;"
pe.write_arp_dict(pe.sidecar(d[40]), p)
e = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=RT_CLI, engine='rt'))
z = [x for x in e.log if "nicht weich ueberblenden" in x]
pruef(e.ok() and len(z) == 1 and "[Exposure] Curve" in z[0] and "IMG_0010" in z[0] and "IMG_0040" in z[0],
      f"harte Umschaltung nicht gemeldet: {z}")

print("=== 6. Quelltext ===")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
a = src.index("def _run_raw_pass2"); b = src.index("def ", a + 10)
teil = src[a:src.index("max_rounds", a)]
pruef(teil.index("self._automatik_einfrieren(files)") < teil.index("self._prepare_keyframe_profiles(files)"),
      "Einfrieren steht nicht vor der Keyframe-Verteilung")
a = src.index("def _open_quick_dialog")
teil = src[a:src.index("def _on_tile_selected", a)]
pruef(teil.index("schnell_profil(") < teil.index("write_arp_dict(pfad, profil)"),
      "Schnelleinstellungen frieren nicht vor dem Schreiben ein")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
