# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Keyframe-Linien im Diagramm folgen dem Stern; Speicherort sitzt rechts."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
N = 60
o = os.path.join(ARBEIT, "kf_linien"); d, _ = szene(o, n=N)
f = pm.MainWindow(); f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True)
f._set_folder(o); f._go_step('smooth'); f._start(); f._set_folder(o)
def linien(): return sorted(m.value() if hasattr(m, 'value') else m._pos for m in f.kf_marker)
pos = lambda: sorted(int(getattr(m, 'pos', None) if not callable(getattr(m, 'pos', None)) else 0) for m in f.kf_marker)
pruef(len(f.kf_marker) == 0, f"anfangs {len(f.kf_marker)} Linien")
# Mischbearbeitung: Bereich in der Mitte, dann aufheben, dann Rand-Keyframes
f.list_widget.setCurrentRow(20); f._setze_bereich('start'); f.list_widget.setCurrentRow(40); f._setze_bereich('ende')
f.tiles[30]['chk'].setChecked(True)
f.list_widget.setCurrentRow(0); f._setze_bereich('start'); f.list_widget.setCurrentRow(N - 1); f._setze_bereich('ende')
f.tiles[0]['chk'].setChecked(True); f.tiles[N - 1]['chk'].setChecked(True)
pruef(len(f.kf_marker) == 3, f"nach dem Setzen {len(f.kf_marker)} Linien statt 3")
f.tiles[30]['chk'].setChecked(False)
pruef(len(f.kf_marker) == 2, f"nach dem Entfernen {len(f.kf_marker)} Linien statt 2")
f._set_folder(o)
pruef(len(f.kf_marker) == 2 and f._kf_count == 2, f"nach dem Neueinlesen {len(f.kf_marker)} Linien, {f._kf_count} Keyframes")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
a = src.index("self.spalte_rechts.addWidget(self.box_export)")
pruef("render_col.addWidget(self.box_export)" not in src and a > 0, "Speicherort steht nicht rechts")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
