# -*- coding: utf-8 -*-
"""Bildleiste zeigt den Look der Engine: Keyframes von ART, RawTherapee und
darktable selbst entwickelt (verkleinert, abgelegt), nach Pass 2 die
entwickelten Zwischenbilder - nur solange das Profil unveraendert ist."""
import os, sys, shutil, glob, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
import numpy as np, cv2
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

ablage = os.path.join(pm.cache_ordner(), "bildleiste")

def fenster(ordner, engine, idx, cli):
    w = pm.MainWindow(); w.cmb_engine.setCurrentIndex(idx); pe.set_engine(engine)
    w.txt_art_path.setText(cli); w.rb_raw.setChecked(True)
    w._set_folder(ordner); pe.set_engine(engine)
    return w, {t_['name']: t_ for t_ in w.tiles}

for engine, idx, cli, label in (('rt', 1, RT_CLI, "RawTherapee"), ('art', 0, ART_CLI, "ART")):
    print(f"=== {label}: Keyframes vor Pass 2 ===")
    o = os.path.join(ARBEIT, f"bildleiste_{engine}")
    d, _ = szene(o, n=10, seed=11)
    pe.set_engine(engine)
    e = lauf(parameter(o, d, raw_mode='pass1', make_video=False, engine=engine, art_cli_path=cli))
    pruef(e.ok(), f"{label} Pass 1: {e.fehler}")
    shutil.rmtree(ablage, ignore_errors=True)
    w, k = fenster(o, engine, idx, cli)
    pruef(all(not t_['img'].toolTip() for t_ in w.tiles), "ohne Keyframe: ueberall das Kamerabild")
    pruef(not os.path.isdir(ablage) or not os.listdir(ablage), "ohne Keyframe wird nichts entwickelt")
    vorher = w.tiles[3]['qimg']
    w.tiles[3]['chk'].setChecked(True)
    pruef(f"Von {label} entwickelt" in (w.tiles[3]['img'].toolTip() or ""),
          f"Stern: Kachel zeigt das Bild der Engine: {w.tiles[3]['img'].toolTip()!r}")
    pruef(w.tiles[3]['qimg'] is not vorher, "Kachelbild ersetzt")
    pruef(not w.tiles[4]['img'].toolTip(), "Nachbar bleibt beim Kamerabild")
    c = pm.bildleiste_cache(d[3])
    pruef(os.path.exists(c) and max(cv2.imread(c).shape[:2]) <= pm.BILDLEISTE_KANTE,
          "verkleinert abgelegt")
    pruef(open(pe.sidecar(d[3])).read().count("Resize") == 0, "die Begleitdatei bekommt keine Verkleinerung")
    zeit = os.path.getmtime(c)
    time.sleep(0.05)
    w, k = fenster(o, engine, idx, cli)
    pruef(f"Von {label} entwickelt" in (w.tiles[3]['img'].toolTip() or "")
          and os.path.getmtime(c) == zeit, "erneutes Einlesen: abgelegtes Bild, nicht neu entwickelt")
    pe.set_engine(engine)
    pr = pe.read_arp_dict(pe.sidecar(d[3]))
    pe.quick_apply(pr, {'saturation': 50})
    pe.write_arp_dict(pe.sidecar(d[3]), pr)
    pruef(pm.bildleiste_cache(d[3]) != c, "geaendertes Profil: neues Vorschaubild")
    pruef(not glob.glob(os.path.join(pm.cache_ordner(), "darktable_bildleiste", "*.lock")), "")

    print(f"=== {label}: nach Pass 2 ===")
    e = lauf(parameter(o, d, raw_mode='pass2', make_video=False, engine=engine, art_cli_path=cli))
    pruef(e.ok(), f"{label} Pass 2: {e.fehler}")
    w, k = fenster(o, engine, idx, cli)
    pruef(all("Pass 2" in (t_['img'].toolTip() or "") for t_ in w.tiles),
          f"alle Kacheln zeigen das entwickelte Bild: {[t_['img'].toolTip() for t_ in w.tiles][:3]}")
    pe.set_engine(engine)
    pr = pe.read_arp_dict(pe.sidecar(d[6]))
    pe.quick_apply(pr, {'contrast': 30})
    pe.write_arp_dict(pe.sidecar(d[6]), pr)
    w, k = fenster(o, engine, idx, cli)
    pruef(not w.tiles[6]['img'].toolTip() and "Pass 2" in (w.tiles[5]['img'].toolTip() or ""),
          "geaendertes Profil: Kamerabild statt veraltetem Zwischenbild")

print("=== Veraltet, Engine-Wechsel ===")
o = os.path.join(ARBEIT, "bildleiste_rt")
d = sorted(glob.glob(os.path.join(o, "*.NEF")))
w, k = fenster(o, 'rt', 1, RT_CLI)
pruef("Pass 2" in (w.tiles[2]['img'].toolTip() or ""), "Ausgang: entwickeltes Bild")
pe.set_engine('rt')
pr = pe.read_arp_dict(pe.sidecar(d[2])); pe.quick_apply(pr, {'contrast': -20})
pe.write_arp_dict(pe.sidecar(d[2]), pr)
w._entwickelte_zeigen(); pe.set_engine('rt')
pruef(not w.tiles[2]['img'].toolTip() and w.tiles[2]['qimg'] is w.tiles[2]['qimg_kamera'],
      "Profil geaendert, ohne neu einzulesen: Kachel zeigt wieder das Kamerabild")
pruef("Pass 2" in (w.tiles[1]['img'].toolTip() or ""), "die anderen bleiben")
w.cmb_engine.setCurrentIndex(0); pe.set_engine('art')
pruef(all("Pass 2" not in (t_['img'].toolTip() or "") for t_ in w.tiles),
      "Engine gewechselt: keine Bilder der vorigen Engine mehr")
w.cmb_engine.setCurrentIndex(1); pe.set_engine('rt')

print("=== Fehlendes Programm, Lightroom ===")
o = os.path.join(ARBEIT, "bildleiste_rt")
shutil.rmtree(ablage, ignore_errors=True)
w, k = fenster(o, 'rt', 1, "/gibt/es/nicht")
pruef(not w.tiles[3]['img'].toolTip() or "Pass 2" in w.tiles[3]['img'].toolTip(),
      "ohne Programm: kein Engine-Bild, kein Absturz")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef("if art in ('ini', 'darktable', 'rapidraw') and engine_vorhanden(self.cli):" in src, "Lightroom wird nicht aufgerufen")

print("=== Verkleinern: Einheit fuer ART ===")
vp = pe.vorschau_profil({'Version': {'AppVersion': '1.25'}, 'Resize': {'Unit': 'cm', 'PPI': '300'}}, 480)
pruef(vp['Resize']['Unit'] == 'px' and vp['Resize']['Width'] == '480' and vp['Resize']['DataSpecified'] == '3'
      and vp['Resize']['Enabled'] == 'true', f"Vorschau-Profil: {vp['Resize']}")

print("=== darktable ===")
od = os.path.join(ARBEIT, "bildleiste_dt")
dd, _ = szene(od, n=4, seed=12)
fake = os.path.join(ARBEIT, "darktable-cli-bildleiste")
open(fake, "w").write('''#!/usr/bin/env python3
import sys, numpy as np, cv2, os
a = sys.argv[1:]
xmp, out = a[1], a[2]
k = int(a[a.index("--width") + 1])
assert "--configdir" in a and "darktable_bildleiste" in a[a.index("--configdir") + 1]
cv2.imwrite(out, np.full((k * 2 // 3, k, 3), 77, np.uint8))
''')
fake = ausfuehrbar(fake)
DT = ('<?xml version="1.0" encoding="UTF-8"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.4.0-Exiv2">\n'
      '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
      '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:darktable="http://darktable.sf.net/" '
      'xmp:Rating="5" darktable:history_end="1">\n'
      '<darktable:history><rdf:Seq><rdf:li darktable:num="0" darktable:operation="sharpen" darktable:enabled="1" '
      'darktable:modversion="1" darktable:params="0000003f0000003f00000000" darktable:multi_priority="0"/>'
      '</rdf:Seq></darktable:history>\n</rdf:Description></rdf:RDF></x:xmpmeta>\n')
open(dd[1] + ".xmp", "w").write(DT)
shutil.rmtree(ablage, ignore_errors=True)
w, k = fenster(od, 'dt', 2, fake)
pruef("Von Darktable entwickelt" in (w.tiles[1]['img'].toolTip() or ""),
      f"darktable-Keyframe: {w.tiles[1]['img'].toolTip()!r}")
c = pm.bildleiste_cache(dd[1])
pruef(os.path.exists(c) and abs(float(cv2.imread(c).mean()) - 77) < 2, "Bild von darktable abgelegt")
pe.set_engine('rt')

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
