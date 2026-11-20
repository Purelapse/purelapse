# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Zoombare Vorschau, ruhiges Histogramm, Bildnummern."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import QtGui, _basis, QtWidgets as _QW
import cv2
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
print("=== Histogramm ===")
rng = np.random.default_rng(3)
yy, xx = np.mgrid[0:300, 0:400].astype(np.float64)
basis = 40 + 150 * (yy / 300) * (0.6 + 0.4 * np.sin(xx / 37.0) ** 2)
glatt = np.clip(np.stack([basis * 1.05, basis, basis * 0.9], axis=2) + rng.normal(0, 3, (300, 400, 3)), 0, 255).astype(np.uint8)
ok, b = cv2.imencode(".jpg", glatt, [cv2.IMWRITE_JPEG_QUALITY, 92]); jpg = cv2.imdecode(b, cv2.IMREAD_COLOR)
stufig = (glatt // 6 * 6).astype(np.uint8)          # wie stark quantisierte Tonwerte
def hoehe(img):
    h = pm.histogramm_bild(img, 380, 86)
    hint = np.array([26, 29, 35])
    maske = np.any(np.abs(h[:, 5:-5].astype(int) - hint) > 40, axis=2) & ~np.all(h[:, 5:-5] == [70, 74, 82], axis=2)
    oben = [86 - np.where(maske[:, x])[0].min() for x in range(maske.shape[1]) if maske[:, x].any()]
    return float(np.mean(oben)) if oben else 0.0
h0, h1, h2 = hoehe(glatt), hoehe(jpg), hoehe(stufig)
print(f"   Kurvenhoehe: glatt {h0}, JPEG {h1}, stufig {h2}")
pruef(h2 > 0 and abs(h1 - h0) <= 0.12 * h0, f"JPEG verschiebt die Skala: {h0} -> {h1}")
pruef(h2 >= 0.6 * h0, f"stufige Tonwerte druecken die Kurven: {h0} -> {h2}")
pruef(pm.histogramm_bild(None, 380, 86).shape == (86, 380, 3), "leeres Bild")
print("=== Zoom ===")
z = pm.ZoomBild()
z.setPixmap(QtGui.QPixmap())
pruef(z.zoom() == 1.0 and z._pixmap is not None, "Grundzustand")
z.zoom_setzen(2.0); pruef(z.zoom() == 2.0, "zoomen")
z.zoom_setzen(50); pruef(z.zoom() == pm.ZOOM_MAX, "Obergrenze")
z.zoom_setzen(0.1); pruef(z.zoom() == 1.0, "Untergrenze")
z.setText("x"); pruef(z._pixmap is None, "setText")
print("=== Dialog und Kacheln ===")
o = os.path.join(ARBEIT, "zoom"); d, _ = szene(o, n=60)
f = pm.MainWindow(); f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True)
f._set_folder(o); f._go_step('smooth'); f._start(); f._set_folder(o)
nummern = [w.text() for w in _QW.ALLE if type(w).__name__ == 'QLabel' and w.text().isdigit()]
pruef(all(str(i) in nummern for i in (1, 30, 60)), f"Bildnummern fehlen: {nummern[:5]} ... ({len(nummern)})")
f.tiles[10]['chk'].setChecked(True); f.list_widget.setCurrentRow(10)
gesehen = {}
def bedienen(dlg):
    dlg._vorschau_zeichnen()
    gesehen['typ'] = type(dlg.lbl_vorschau).__name__
    gesehen['echt'] = dlg._gezeigt_echt
    gesehen['groesse'] = dlg._echt_bild.shape if dlg._echt_bild is not None else None
    return 0
_basis.ANTWORTEN['QuickLookDialog'] = bedienen
f._open_quick_dialog()
pruef(gesehen.get('typ') == 'ZoomBild', f"Vorschau ist {gesehen.get('typ')}")
pruef(gesehen.get('echt') and gesehen.get('groesse') and max(gesehen['groesse'][:2]) > 200, f"echtes Bild: {gesehen}")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef("setFixedWidth(HISTOGRAMM_BREITE)" in src and "kante=ECHT_KANTE" in src, "Histogrammbreite / Vorschaugroesse")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
