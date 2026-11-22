# -*- coding: utf-8 -*-
"""Ordnerwahl mit Vorschau: Bilder finden, scrollbares Raster mit Laden nur\ndes sichtbaren Bereichs, Vorschaubilder fuer RAW und JPG, Dialog im Hauptfenster."""
import os, sys, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import _basis
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

print("=== 1. Bilder eines Ordners ===")
o = os.path.join(ARBEIT, "wahl_raw"); d, _ = szene(o, n=60)
open(os.path.join(o, "notiz.txt"), "w").write("x")
bilder, art = pm.ordner_bilder(o)
pruef(art == 'raw' and len(bilder) == 60 and bilder == sorted(bilder), f"RAW: {art} {len(bilder)}")
oj = os.path.join(ARBEIT, "wahl_jpg"); dj, _ = szene(oj, n=12, art="jpg")
bilder_j, art_j = pm.ordner_bilder(oj)
pruef(art_j == 'jpg' and len(bilder_j) == 12, f"JPG: {art_j} {len(bilder_j)}")
leer = os.path.join(ARBEIT, "wahl_leer"); shutil.rmtree(leer, ignore_errors=True); os.makedirs(leer)
pruef(pm.ordner_bilder(leer) == ([], None), "leerer Ordner")
pruef(pm.ordner_bilder(os.path.join(ARBEIT, "gibt_es_nicht")) == ([], None), "fehlender Ordner")

print("=== 2. Sichtbarer Bereich des Rasters ===")
B, H = pm.ORDNER_KACHEL_B, pm.ORDNER_KACHEL_H
r = pm.raster_bereich(0, 3 * H, 3 * B, 894)
# drei Zeilen sichtbar, die angeschnittene vierte und eine Zeile Vorlauf
pruef(r == list(range(15)), f"oben: {r[:5]} ... {len(r)}")
r = pm.raster_bereich(100 * H, 3 * H, 3 * B, 894)
# Zeilen 100 bis 103 sichtbar, je eine Zeile Vorlauf: 99 bis 104
pruef(r[0] == 99 * 3 and r[-1] == 105 * 3 - 1 and len(r) == 18, f"mitten: {r[0]} .. {r[-1]} ({len(r)})")
r = pm.raster_bereich(10 ** 6, 3 * H, 3 * B, 894)
pruef(r == [] or max(r) <= 893, "unten ueber das Ende hinaus")
r = pm.raster_bereich(297 * H, 3 * H, 3 * B, 894)
pruef(r and r[-1] == 893, f"letzte Zeile: {r[-3:]}")
pruef(pm.raster_bereich(0, 400, 50, 10) == list(range(5)), "schmaler als eine Kachel: eine Spalte")
pruef(pm.raster_bereich(0, 400, 600, 0) == [] and pm.raster_bereich(0, 0, 600, 9) == [], "leer")
pruef(len(pm.raster_bereich(0, 3 * H, 3 * B, 5000)) == len(pm.raster_bereich(0, 3 * H, 3 * B, 50)),
      "die Zahl der geladenen Kacheln haengt von der Ordnergroesse ab")

print("=== 3. Vorschaubilder ===")
for pfad in (bilder[0], bilder_j[0]):
    img = pm.ordner_vorschau_bild(pfad, kante=200)
    pruef(img is not None and max(img.shape[:2]) <= 200 and img.shape[2] == 3, f"{os.path.basename(pfad)}: {None if img is None else img.shape}")
pruef(pm.ordner_vorschau_bild(os.path.join(o, "notiz.txt")) is None, "kaputte Datei liefert ein Bild")

print("=== 4. Lader im Hintergrund ===")
gesehen = []
lader = pm.OrdnerRasterLader(7, bilder, kante=120)
lader.bild.connect(lambda n, i, img: gesehen.append((n, i, img is not None and max(img.shape[:2]) <= 120)))
pruef(lader.wuenschen([5, 2, 9, 999]), "neuer Lader nimmt keine Wuensche an")
lader.start()
pruef(gesehen == [(7, 5, True), (7, 2, True), (7, 9, True)], f"Reihenfolge der Wunschliste: {gesehen}")
pruef(lader.wuenschen([1]) is False, "fertiger Lader nimmt noch Wuensche an - sie gingen verloren")
gesehen.clear()
lader = pm.OrdnerRasterLader(8, bilder); lader.bild.connect(lambda n, i, img: gesehen.append(i))
lader.wuenschen([1, 2, 3]); lader.abbrechen(); lader.start()
pruef(gesehen == [], "abgebrochener Lader liefert weiter")
# Wunschliste waehrend des Ladens ersetzen: das Neue zuerst, das Alte faellt weg
gesehen.clear()
lader = pm.OrdnerRasterLader(9, bilder)
def mitten(n, i, img):
    gesehen.append(i)
    if i == 0: lader.wuenschen([40, 41])
lader.bild.connect(mitten); lader.wuenschen([0, 1, 2]); lader.start()
pruef(gesehen == [0, 40, 41], f"ersetzte Wunschliste: {gesehen}")

print("=== 5. Der Dialog ===")
dlg = pm.OrdnerDialog(None, "x", o, 'de')
dlg._ordner = o; dlg._laden()
pruef(dlg.raster.count() == 60, f"nicht alle Bilder im Raster: {dlg.raster.count()}")
sicht = dlg.raster.viewport()
soll = set(pm.raster_bereich(0, sicht.height(), sicht.width(), 60))
pruef(dlg._fertig == soll and 0 < len(soll) < 60, f"geladen: {sorted(dlg._fertig)} statt {sorted(soll)}")
pruef("60 Bilder (NEF)" in dlg.lbl_v_info.text(), f"Info: {dlg.lbl_v_info.text()!r}")
rb = dlg.raster.verticalScrollBar()
rb.setValue(rb.maximum()); dlg._sichtbare_laden()
unten = set(pm.raster_bereich(rb.value(), sicht.height(), sicht.width(), 60))
pruef(rb.value() > 0 and unten <= dlg._fertig and min(unten) > max(soll), f"nach dem Scrollen nicht nachgeladen: {sorted(unten - dlg._fertig)}")
pruef(len(dlg._fertig) < 60, "es wurde mehr geladen als sichtbar war")
dlg._ordner = leer; dlg._laden()
pruef(dlg.raster.count() == 0 and "Keine Bilder" in dlg.lbl_v_info.text(), "leerer Ordner im Dialog")
dlg._ordner = o; dlg._laden(); alt = dlg._nummer
dlg._ordner = oj; dlg._laden()
vorher = set(dlg._fertig); dlg._bild_da(alt, 3, None)
pruef(dlg._fertig == vorher, "ein Bild aus dem vorigen Ordner landet im Raster")
pruef(dlg.raster.count() == 12, "JPG-Ordner im Dialog")

print("=== 6. Im Hauptfenster ===")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
rumpf = src.split("    def _browse(self):")[1].split("\n    def ")[0]
pruef("OrdnerDialog(" in rumpf and "getExistingDirectory" not in rumpf, "Hauptfenster nutzt den neuen Dialog nicht")
dlg_src = src.split("class OrdnerDialog")[1].split("\nclass ")[0]
pruef("0.7" in dlg_src and "DontUseNativeDialog" in dlg_src and "ShowDirsOnly" in dlg_src, "Groesse oder Optionen fehlen")
pruef("l.wait(" in dlg_src, "Lader werden beim Schliessen nicht abgewartet")
f = pm.MainWindow()
f._browse()     # Pruefstand: Dialog wird abgebrochen, nichts passiert
pruef(f.target_dir == "", "abgebrochene Ordnerwahl setzt einen Ordner")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
