# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""JPG: der Hauptknopf in "Helligkeit glaetten" fuehrt zur Seite "Video rendern"."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
o = os.path.join(ARBEIT, "jpg_schritt"); d, _ = szene(o, n=60, art="jpg")
f = pm.MainWindow(); f._set_folder(o)
pruef(f.rb_jpg.isChecked() and f.step == 'smooth', f"Schritt {f.step}")
pruef("Weiter" in f.btn_start.text(), f"Knopf: {f.btn_start.text()}")
gestartet = []
alt = f._start; f._start = lambda: gestartet.append(1)
f._primary_action()
pruef(not gestartet and f.step == 'render', f"Klick in 'glaetten' startet ({gestartet}) / Schritt {f.step}")
pruef("Zeitraffer erstellen" in f.btn_start.text(), f"Knopf auf der Render-Seite: {f.btn_start.text()}")
f._primary_action()
pruef(gestartet == [1], "auf der Render-Seite startet der Knopf nicht")
f._start = alt
f._go_step('render'); f._start()
pruef("Fertig" in f.lbl_status.text() and videos(o), f"Lauf: {f.lbl_status.text()}")
# RAW unveraendert: Pass 1 startet direkt
o2 = os.path.join(ARBEIT, "raw_schritt"); szene(o2, n=60)
g = pm.MainWindow(); g.cmb_engine.setCurrentIndex(1); g.txt_art_path.setText(RT_CLI); g.rb_raw.setChecked(True); g._set_folder(o2)
g._go_step('smooth'); n = []; g._start = lambda: n.append(1); g._primary_action()
pruef(n == [1] and g.step == 'smooth', "RAW: Pass 1 startet nicht mehr direkt")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
