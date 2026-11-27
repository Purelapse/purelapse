# -*- coding: utf-8 -*-
"""Schalter 16-Bit-Zwischenbilder: sitzt beim Video, erklaert sich und
faellt auf, solange er an ist."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

od = os.path.join(ARBEIT, "tiff16_schalter")
d, _ = szene(od, n=60)
f = pm.MainWindow(); f.rb_raw.setChecked(True); f._set_folder(od)
f._apply_language('de')
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef("gv.addWidget(self.chk_tiff16" in src and "gperf.addWidget(self.chk_tiff16" not in src,
      "Schalter gehoert in die Gruppe Video, nicht zu Engine und Leistung")
f.chk_tiff16.setChecked(False); f._update_visibility()
aus = f.lbl_tiff16.text()
pruef("nicht nötig" in aus and "Himmel" in aus, f"Hinweis aus: {aus}")
f.chk_tiff16.setChecked(True)
an = f.lbl_tiff16.text()
pruef(an.startswith("⚠") and "GB für 60 Bilder" in an and "ausschalten" in an, f"Hinweis an: {an}")
pruef(pm.THEMES[f.theme]['warn'] in f.lbl_tiff16.styleSheet(), "an: nicht hervorgehoben")
f.step = 'render'; f._update_summary()
pruef("16-Bit-Zwischenbilder" in f.lbl_summary.text(), f"Zusammenfassung: {f.lbl_summary.text()}")
f._apply_language('en')
pruef("frames" in f.lbl_tiff16.text() and "Switch off" in f.lbl_tiff16.text(), f"englisch: {f.lbl_tiff16.text()}")
f._apply_language('de')
f.chk_tiff16.setChecked(False)
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
