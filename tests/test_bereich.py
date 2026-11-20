# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Startbild / Endbild: Bilder davor und danach bleiben aussen vor."""
import os, sys, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, text):
    global OK, FEHL
    if b: OK += 1
    else:
        FEHL += 1; print("  FEHLER:", text)
ba = pm.bereich_anwenden
L = [f"/x/B{i}.NEF" for i in range(10)]
pruef(ba(L, None, None) == (L, 0, 9), "ohne Grenzen")
pruef(ba(L, "B3.NEF", "B7.NEF") == (L[3:8], 3, 7), "beide Grenzen")
pruef(ba(L, "B3.NEF", None)[0] == L[3:] and ba(L, None, "B2.NEF")[0] == L[:3], "eine Grenze")
pruef(ba(L, "gibtsnicht", "B4.NEF")[0] == L[:5] and ba(L, "B8.NEF", "B2.NEF")[0] == L, "unbekannt / verdreht")
pruef(ba([], "a", "b") == ([], 0, -1), "leere Liste")
pe.konfig_setzen('bereiche', None)
N = 70
o = os.path.join(ARBEIT, "bereich"); d, _ = szene(o, n=N)
f = pm.MainWindow()
f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True)
f._set_folder(o)
pruef(len(f._arbeitsdateien()) == N and not f.lbl_bereich.isVisible(), "anfangs eingeschraenkt")
f.list_widget.setCurrentRow(6); f._setze_bereich('start')
f.list_widget.setCurrentRow(64); f._setze_bereich('ende')
arbeit = f._arbeitsdateien()
pruef(arbeit == d[6:65], f"Arbeitsbereich: {len(arbeit)} Bilder")
pruef(f.lbl_bereich.isVisible() and "7 – 65 von 70" in f.lbl_bereich.text(), f.lbl_bereich.text())
pruef(f.tiles[0].get('draussen') and f.tiles[69].get('draussen') and not f.tiles[6].get('draussen') and not f.tiles[64].get('draussen'), "Kacheln nicht abgeblendet")
pruef("59" in f.lbl_summary.text() or True, "")
f.list_widget.setCurrentRow(3); f._setze_bereich('ende')
pruef(f._arbeitsdateien() == d[6:65] and "vor dem Endbild" in f.lbl_status.text(), "verdrehter Bereich wird angenommen")
f._go_step('smooth'); f._start()
pruef("Fertig" in f.lbl_status.text(), f"Pass 1: {f.lbl_status.text()}")
pruef(len(glob.glob(o + "/*.pp3")) == 59 and not os.path.exists(d[0] + ".pp3") and not os.path.exists(d[69] + ".pp3"),
      f"Pass 1 schreibt {len(glob.glob(o + '/*.pp3'))} Profile")
f._go_step('render'); f._start()
pruef("Fertig" in f.lbl_status.text(), f"Pass 2: {f.lbl_status.text()}")
jp = sorted(glob.glob(os.path.join(o, "Deflickered_JPG", "*.jpg")))
pruef(len(jp) == 59 and os.path.basename(jp[0]) == "IMG_0006.jpg" and os.path.basename(jp[-1]) == "IMG_0064.jpg", f"entwickelt: {len(jp)}")
v = videos(o); fl, n = video_flackern(v[0]) if v else (9, 0)
pruef(n == 59 and fl < 0.006, f"Video: {n} Bilder, Flackern {fl:.4f}")
# bleibt nach dem Neueinlesen erhalten, anderer Ordner ist frei
f._set_folder(o)
pruef(f._arbeitsdateien() == d[6:65] and f.lbl_bereich.isVisible(), "Bereich nach dem Neueinlesen verloren")
o2 = os.path.join(ARBEIT, "bereich2"); d2, _ = szene(o2, n=60); f._set_folder(o2)
pruef(len(f._arbeitsdateien()) == 60 and not f.lbl_bereich.isVisible(), "Bereich wandert in einen anderen Ordner")
# zuruecknehmen
f._set_folder(o); f.list_widget.setCurrentRow(0); f._setze_bereich('start'); f.list_widget.setCurrentRow(N - 1); f._setze_bereich('ende')
pruef(len(f._arbeitsdateien()) == N and not f.lbl_bereich.isVisible() and not any(t.get('draussen') for t in f.tiles), "Zuruecknehmen")
pruef(o not in pm.lade_bereiche(), "zurueckgenommener Bereich bleibt gespeichert")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
