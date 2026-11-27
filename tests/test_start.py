# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Startdialog und Ladeschirm."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import _basis
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
o = os.path.join(ARBEIT, "start"); d, _ = szene(o, n=60)
pm.save_last_path(o)
st = pm.workflow_stand(o)
pruef("60 RAW" in st and "zuletzt" in st and "Pass 1" not in st, st)
f = pm.MainWindow()
pruef(not f.tiles and f.target_dir in (None, ""), "das Fenster laedt ohne Rueckfrage")
# 1) letzten laden
_basis.ANTWORTEN['StartDialog'] = lambda dlg: dlg._waehle('weiter')
f._startauswahl()
pruef(f.target_dir == o and len(f.tiles) == 60, f"letzter Arbeitsgang nicht geladen: {f.target_dir} / {len(f.tiles)}")
pruef(not f.lade_schirm.isVisible(), "der Ladeschirm bleibt nach dem Laden stehen")
# Ladeschirm war waehrend des Ladens sichtbar
gesehen = []
alt = f._on_gallery_progress
def merke(a, b):
    alt(a, b); gesehen.append(f.lade_schirm.isVisible())
f._on_gallery_progress = merke
f._refresh_preview()
pruef(gesehen and all(gesehen), f"Ladeschirm waehrend des Ladens: {gesehen[:3]}")
pruef(not f.lade_schirm.isVisible(), "Ladeschirm nach dem Neueinlesen sichtbar")
# 2) neu: oeffnet den Ordnerdialog
g = pm.MainWindow(); aufgerufen = []
g._browse = lambda: aufgerufen.append(1)
_basis.ANTWORTEN['StartDialog'] = lambda dlg: dlg._waehle('neu')
g._startauswahl()
pruef(aufgerufen == [1] and not g.tiles, "Neu beginnen oeffnet keine Ordnerauswahl")
# 3) ohne Ordner
h = pm.MainWindow()
_basis.ANTWORTEN['StartDialog'] = lambda dlg: dlg._waehle(None)
h._startauswahl()
pruef(not h.tiles, "ohne Ordner wird trotzdem geladen")
# 4) leerer Ordner: Ladeschirm verschwindet
leer = os.path.join(ARBEIT, "start_leer"); os.makedirs(leer, exist_ok=True)
h._set_folder(leer)
pruef(not h.lade_schirm.isVisible(), "Ladeschirm bleibt bei leerem Ordner stehen")
# 5) Stand nach Pass 1
f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True); f._set_folder(o)
f._go_step('smooth'); f._start()
pruef("Pass 1 erledigt" in pm.workflow_stand(o), pm.workflow_stand(o))
pruef(pm.workflow_stand("/gibt/es/nicht") is None, "fehlender Ordner")
# 6) Zwei Bildschirme: Dialog mittig ueber dem Hauptfenster, ganz im Bild
links, rechts = (0, 0, 1920, 1080), (1920, 0, 2560, 1440)
haupt = (2200, 100, 1800, 1100)
x, y = pm.mittig_auf((560, 220), haupt, rechts)
pruef((x, y) == (2200 + (1800 - 560) // 2, 100 + (1100 - 220) // 2) and x >= 1920,
      f"nicht mittig auf dem rechten Bildschirm: {(x, y)}")
x, y = pm.mittig_auf((900, 700), (3900, 1000, 500, 400), rechts)
pruef(x + 900 <= 1920 + 2560 and y + 700 <= 1440 and x >= 1920, f"ragt aus dem Bildschirm: {(x, y)}")
x, y = pm.mittig_auf((560, 220), (-100, -50, 400, 300), links)
pruef(x >= 0 and y >= 0, f"links/oben ausserhalb: {(x, y)}")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef("app_instance.installEventFilter(platzierer)" in src, "Platzierer nicht eingebaut")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
