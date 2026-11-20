import os  # fuer die Pfade der Pruefumgebung
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
o = os.path.join(ARBEIT, "referenz"); d, _ = szene(o, n=60)
f = pm.MainWindow(); f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True); f._set_folder(o)
pruef(f._referenzbild() == d[0], "ohne Bereich nicht das erste Bild")
f.list_widget.setCurrentRow(9); f._setze_bereich('start')
f.list_widget.setCurrentRow(3)
pruef(f._referenzbild() == d[9], f"Bild ausserhalb des Bereichs gewaehlt: {f._referenzbild()}")
f.list_widget.setCurrentRow(25)
pruef(f._referenzbild() == d[25], "gewaehltes Bild im Bereich wird nicht genommen")
gesehen = []
alt = pm.load_preview_image
pm.load_preview_image = lambda p, max_width=None: (gesehen.append(p), None)[1]
f.list_widget.setCurrentRow(2); f._select_roi()
pm.load_preview_image = alt
pruef(gesehen == [d[9]], f"ROI-Dialog laedt {gesehen}")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
