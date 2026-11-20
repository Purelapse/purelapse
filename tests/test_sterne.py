# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Sternebewertung: vorhandene XMP-Dateien bleiben erhalten."""
import os, sys, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
DT = ('<?xml version="1.0" encoding="UTF-8"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.4.0-Exiv2">\n'
      '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
      '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:darktable="http://darktable.sf.net/" '
      'xmlns:dc="http://purl.org/dc/elements/1.1/" xmp:Rating="1" darktable:history_end="2">\n'
      '<darktable:history><rdf:Seq><rdf:li darktable:num="0" darktable:operation="sigmoid" darktable:enabled="1"/>'
      '<rdf:li darktable:num="1" darktable:operation="sharpen" darktable:enabled="1"/></rdf:Seq></darktable:history>\n'
      '</rdf:Description></rdf:RDF></x:xmpmeta>\n')
o = os.path.join(ARBEIT, "sterne"); d, _ = szene(o, n=60)
for engine, idx in (('dt', 2), ('rt', 1)):
    for f in d[:3]:
        open(f + ".xmp", "w").write(DT)
    if os.path.exists(d[3] + ".xmp"): os.remove(d[3] + ".xmp")
    w = pm.MainWindow(); w.cmb_engine.setCurrentIndex(idx); pe.set_engine(engine); w.txt_art_path.setText(RT_CLI); w.rb_raw.setChecked(True)
    w._set_folder(o); pe.set_engine(engine)
    for i in (0, 3):
        w.tiles[i]['chk'].setChecked(True)
    inhalt = open(d[0] + ".xmp").read()
    pruef('Rating="5"' in inhalt and 'Rating="1"' not in inhalt, f"{engine}: Bewertung nicht gesetzt: {inhalt[:200]}")
    pruef('operation="sigmoid"' in inhalt and 'operation="sharpen"' in inhalt and inhalt.count("rdf:li") == 2,
          f"{engine}: Darktable-Verlauf veraendert")
    pruef("ns0:" not in inhalt and "darktable:history" in inhalt, f"{engine}: Namensraeume verdorben")
    pruef(pe.check_is_keyframe(pe.sidecar(d[0])), f"{engine}: Keyframe nicht erkannt")
    pruef(os.path.exists(d[3] + ".xmp") and 'Rating="5"' in open(d[3] + ".xmp").read(), f"{engine}: ohne XMP keine Bewertung angelegt")
    pruef(pe.check_is_keyframe(pe.sidecar(d[3])), f"{engine}: Keyframe ohne XMP nicht erkannt")
    w.tiles[0]['chk'].setChecked(False)
    inhalt = open(d[0] + ".xmp").read()
    pruef('Rating="0"' in inhalt and inhalt.count("rdf:li") == 2, f"{engine}: Zuruecknehmen")
    pruef(not pe.check_is_keyframe(pe.sidecar(d[0])), f"{engine}: zurueckgenommener Stern zaehlt noch")
    pruef(open(d[1] + ".xmp").read() == DT, f"{engine}: unbeteiligte XMP veraendert")
    for f in d:
        for ext in (".xmp", ".pp3"):
            if os.path.exists(f + ext): os.remove(f + ext)
pe.set_engine('rt')
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
