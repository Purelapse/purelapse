# -*- coding: utf-8 -*-
"""Helligkeitsmessung der entwickelten Bilder bei viel Ausgebranntem.

Fall aus der Praxis (Kerzenlicht, Slider, 400 NEF): Kaum ein Block blieb in
allen Bildern unbeschaedigt, also entschied jedes Bild selbst, was zaehlt.
Wurde ein Bild heller, brannte mehr aus, fiel aus der Messung - und das
Bild mass sich DUNKLER. Die Nachkalibrierung machte es noch heller, bis zum
Anschlag: einzelne Bilder sprangen um fast eine Blende."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

# Eine Szene mit hellen Flaechen (Kerze, Holz, Tuer), die bei mehr Licht ausbrennen
rng = np.random.default_rng(7)
B, H = 1600, 900
yy, xx = np.mgrid[0:H, 0:B]
szene_lin = 0.06 + 0.30 * (xx / B) + 0.9 * np.exp(-((xx - 1100) ** 2 + (yy - 450) ** 2) / 6e4)
szene_lin += 0.55 * ((xx // 120) % 2) * (yy > 420)
szene_lin += 0.45 * ((yy // 90) % 2) * (yy <= 420) * ((xx // 200) % 2)
szene_lin += rng.normal(0, 0.01, szene_lin.shape)
szene_lin = np.clip(szene_lin, 0.005, None)

def bild(versatz, k):
    lin = np.clip(szene_lin[:, versatz:versatz + 1000] * k, 0, 1)
    g = (lin ** (1 / 2.2) * 255).astype(np.uint8)
    return np.dstack([g, g, g])

o = os.path.join(ARBEIT, "messung_lichter"); shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
N = 60
pfade, faktor = [], []
for i in range(N):
    k = 1.0 if i < 40 else [0.7, 0.85, 1.2, 1.45, 1.7][i % 5]
    p = os.path.join(o, f"b{i:03d}.jpg")
    cv2.imwrite(p, bild(int(i * 590 / (N - 1)), k), [cv2.IMWRITE_JPEG_QUALITY, 95])
    pfade.append(p); faktor.append(k)
bloecke = [pm.jpg_bloecke(p) for p in pfade]

print("=== 1. Die Ausgangslage ===")
frei = np.ones(bloecke[0][0].shape, bool)
for b in bloecke: frei &= ~b[1]
pruef(frei.mean() < pm.MESS_MIN_ANTEIL, f"Szene brennt nicht genug aus, Pruefung waere wirkungslos ({frei.mean():.2f})")

print("=== 2. Heller gemacht misst sich heller ===")
w = pm.sequenz_helligkeit(bloecke)
bezug = np.mean(w[34:40])
for i in range(40, N):
    r = w[i] / bezug
    if faktor[i] > 1.05:
        pruef(r > 1.05, f"Bild {i}: {faktor[i]}x heller gemacht, gemessen {r:.2f}")
    elif faktor[i] < 0.95:
        pruef(r < 0.95, f"Bild {i}: {faktor[i]}x dunkler gemacht, gemessen {r:.2f}")
pruef(all(v is not None for v in w), "einzelne Bilder ohne Messwert")

print("=== 3. Die Nachkalibrierung laeuft nicht weg ===")
# Ein Bild, das in Wahrheit stimmt, wird so lange korrigiert, wie die Messung es verlangt
k = 1.0
for runde in range(4):
    p = os.path.join(o, "lauf.jpg")
    cv2.imwrite(p, bild(300, k), [cv2.IMWRITE_JPEG_QUALITY, 95])
    reihe = [pm.jpg_bloecke(x) for x in pfade[15:35]] + [pm.jpg_bloecke(p)]
    m = pm.sequenz_helligkeit(reihe)
    soll = np.mean(m[:-1])
    k *= soll / m[-1]
pruef(0.85 < k < 1.18, f"Nachkalibrierung laeuft weg: Faktor {k:.2f} nach 4 Runden")

print("=== 4. Median ohne NaN ===")
a = rng.random((25, 300)); a[a < 0.3] = np.nan; a[:, 5] = np.nan
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    soll = np.nanmedian(a, axis=0)
pruef(np.allclose(pm._nan_median_spalten(a), soll, equal_nan=True), "eigener Median weicht ab")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
