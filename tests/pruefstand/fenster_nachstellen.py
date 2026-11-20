# -*- coding: utf-8 -*-
"""Stellt den gemeldeten Fehler nach: Keyframe markieren, Ordner neu
einlesen - bleibt die Engine stehen?  Aufruf: python3 ... <projektordner>"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if len(sys.argv) > 1:
    os.environ["PURELAPSE_PROJEKT"] = sys.argv[1]      # andere Programmfassung
import stand
from stand import *
pm, pe = stand.pm, stand.pe

ordner = os.path.join(ARBEIT, "N_nachstellen")
dateien, _ = szene(ordner, n=55)
f = pm.MainWindow()
f.cmb_engine.setCurrentIndex(1)                 # RawTherapee
f.txt_art_path.setText(RT_CLI)
print(f"Version {pm.VERSION}")
print("  eingestellt:", f.cmb_engine.currentText(), "| intern:", pe.ENGINE)
f._set_folder(ordner)
print("  nach dem Einlesen:", f.cmb_engine.currentText(), "| Kacheln:", len(f.tiles))
f.tiles[10]['chk'].setChecked(True)              # Keyframe markieren
print("  Keyframe gesetzt -> Dateien:", sorted(x for x in os.listdir(ordner) if not x.endswith('.NEF')))
f._set_folder(ordner)                            # Ordner neu einlesen
print("  nach erneutem Einlesen:", f.cmb_engine.currentText(), "| intern:", pe.ENGINE)
umgestellt = [z for z in f.txt_log._zeilen if "umgestellt" in z]
print("  Protokoll:", umgestellt[-1][:110] if umgestellt else "(keine Umstellung)")
