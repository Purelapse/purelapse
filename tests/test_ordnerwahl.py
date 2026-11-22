# -*- coding: utf-8 -*-
"""Ordnerwahl mit Vorschau: Bilder finden, Auswahl ueber die Serie,
Vorschaubilder fuer RAW und JPG, Dialog im Hauptfenster."""
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

print("=== 2. Auswahl ueber die Serie ===")
a = pm.ordner_auswahl(bilder)
pruef(len(a) == 6 and a[0] == bilder[0] and a[-1] == bilder[-1] and len(set(a)) == 6, f"Auswahl: {[os.path.basename(x) for x in a]}")
pruef(pm.ordner_auswahl(bilder[:4]) == bilder[:4], "wenige Bilder")
pruef(pm.ordner_auswahl([]) == [], "keine Bilder")

print("=== 3. Vorschaubilder ===")
for pfad in (bilder[0], bilder_j[0]):
    img = pm.ordner_vorschau_bild(pfad, kante=200)
    pruef(img is not None and max(img.shape[:2]) <= 200 and img.shape[2] == 3, f"{os.path.basename(pfad)}: {None if img is None else img.shape}")
pruef(pm.ordner_vorschau_bild(os.path.join(o, "notiz.txt")) is None, "kaputte Datei liefert ein Bild")

print("=== 4. Lader im Hintergrund ===")
gesehen = []
lader = pm.OrdnerVorschauLader(7, a)
lader.bild.connect(lambda n, i, img: gesehen.append((n, i, img is not None)))
lader.start()
pruef(gesehen == [(7, i, True) for i in range(6)], f"Lader: {gesehen}")
gesehen.clear()
lader = pm.OrdnerVorschauLader(8, a); lader.bild.connect(lambda n, i, img: gesehen.append(i))
lader.abbrechen(); lader.start()
pruef(gesehen == [], "abgebrochener Lader liefert weiter")

print("=== 5. Im Hauptfenster ===")
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
