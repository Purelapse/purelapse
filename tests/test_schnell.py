# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Schnellvorschau und einrastende Bildleiste."""
import os, sys, glob, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
import cv2
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
N = 80
print("=== 1. Bausteine ===")
lut = pm.helligkeit_lut(2.0)
pruef(lut[0] == 0 and lut[255] == 255 and lut[100] > 100, "LUT")
x = np.full((4, 4, 3), 118, np.uint8)
l1 = float(pm.srgb_to_linear(x).mean()); l2 = float(pm.srgb_to_linear(cv2.LUT(x, lut)).mean())
pruef(abs(l2 / l1 - 2.0) < 0.03, f"Faktor in linearem Licht: {l2/l1:.3f}")
pruef(np.array_equal(cv2.LUT(x, pm.helligkeit_lut(1.0)), x), "Faktor 1 veraendert das Bild")
for art in ("raw", "jpg"):
    o = os.path.join(ARBEIT, f"schnell_{art}"); d, wahr = szene(o, n=N, art=art)
    b, l = pm.schnell_bild_laden(d[0], 1280)
    pruef(b is not None and l > 0, f"{art}: Bild nicht lesbar")
    img = cv2.imdecode(np.frombuffer(b, np.uint8), cv2.IMREAD_COLOR)
    pruef(img.shape[1] <= 1280, f"{art}: zu breit {img.shape}")
pruef(pm.schnell_bild_laden("/gibt/es/nicht.NEF", 640) == (None, None), "fehlende Datei")
pruef(pm.ablauf_plan({'mode': 'schnell'}) == ['schnell_lesen', 'schnell_video'], "Plan")
pruef(pm.phase_schluessel("Schnellvorschau lesen") == 'schnell_lesen' and pm.status_zerlegen(pm.fortschritt_text("Schnellvorschau Video", 3, 9, time.time()))[0] == "Schnellvorschau Video", "Status")

print("=== 2. Im Fenster ===")
for art in ("raw", "jpg"):
    o = os.path.join(ARBEIT, f"schnell_{art}"); d = sorted(glob.glob(o + ("/*.NEF" if art == "raw" else "/*.jpg")))
    for v in videos(o): os.remove(v)
    f = pm.MainWindow()
    if art == "raw":
        f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True)
    f._set_folder(o)
    vorher = set(os.listdir(o))
    t0 = time.time(); f._start_schnell(); dauer = time.time() - t0
    pruef("Schnellvorschau fertig" in f.lbl_status.text(), f"{art}: {f.lbl_status.text()} {[z for z in f.txt_log._zeilen if 'FEHLER' in z or '✕' in z][:2]}")
    v = [x for x in videos(o) if "Schnellvorschau" in x]
    pruef(len(v) == 1, f"{art}: Videos {videos(o)}")
    if v:
        fl, n = video_flackern(v[0])
        roh = flackern([helligkeit_ev(cv2.imread(x)) for x in d]) if art == "jpg" else None
        pruef(n == N and fl < 0.012, f"{art}: {n} Bilder, Flackern {fl:.4f}")
        cap = cv2.VideoCapture(v[0]); ok, fr = cap.read(); cap.release()
        pruef(ok and fr.shape[1] <= 1280 and abs(fr.shape[1] / fr.shape[0] - 16 / 9) < 0.02, f"{art}: Format {fr.shape if ok else None}")
        print(f"   {art}: {n} Bilder in {dauer:.1f} s, Flackern {fl:.4f} EV")
    neu = set(os.listdir(o)) - vorher
    im_pl = set(os.listdir(pl(o))) if os.path.isdir(pl(o)) else set()
    pruef(neu <= {"Purelapse"} and im_pl == {os.path.basename(x) for x in v} and not glob.glob(o + "/*.pp3"),
          f"{art}: Schnellvorschau hinterlaesst weitere Dateien: {neu} / Purelapse: {im_pl}")
    f._start_schnell()
    pruef(len([x for x in videos(o) if "Schnellvorschau" in x]) == 1, f"{art}: zweiter Lauf legt eine weitere Datei an")
    pruef(f.btn_schnell.isEnabled() and f.btn_start.isEnabled(), "Knoepfe bleiben gesperrt")
    pruef(any("Vorschaubilder lesen" in x[0] for x in f.ablauf_leiste.texte()), f"Ablauf: {f.ablauf_leiste.texte()}")

print("=== 3. Bildleiste rastet ein ===")
sb = f.list_widget.verticalScrollBar()
pitch = f._zeilen_abstand()
pruef(pitch == f.list_widget.KACHEL_H, f"Reihenabstand {pitch}")
sb.setValue(57)
pruef(sb.value() % pitch == 0 and sb.value() == 0, f"57 -> {sb.value()}")
sb.setValue(200)
pruef(sb.value() == 260 or sb.value() == 130, f"200 -> {sb.value()}")
pruef(sb.value() % pitch == 0, "nicht auf einer Reihe")
w = sb.value(); f._gallerie_rad(-120)
pruef(sb.value() == w + pitch, f"Rad nach unten: {w} -> {sb.value()}")
f._gallerie_rad(60); pruef(sb.value() == w + pitch, "halbe Raste bewegt schon")
f._gallerie_rad(60); pruef(sb.value() == w, "zwei halbe Rasten bewegen nicht")
sb.setValue(sb.maximum()); pruef(sb.value() == sb.maximum(), "das Ende ist nicht erreichbar")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
