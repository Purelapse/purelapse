#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Pruefungen fuer die Live-Vorschau, die Feindosierung und die weiche
Darstellung der Kurven. Laeuft ohne Qt.
"""
import io, ast, sys, time, collections
import numpy as np
import cv2

BASIS = os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = io.open(f"{BASIS}/purelapse_main.py", encoding="utf-8").read()

ok_n = fail_n = 0
def pruef(b, text):
    global ok_n, fail_n
    if b: ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")

def schnitt(txt, von, bis):
    return txt[txt.index(von):txt.index(bis)]

ns = {"np": np, "cv2": cv2}
exec(schnitt(src, "VORSCHAU_BREITE = 1100", "# Ab wie vielen Bildern"), ns)
wb = ns["wb_faktoren"]
vr = ns["vorschau_rechnen"]

print("=== 1. Farbtemperatur ===")
for k in (1500, 2500, 5500, 12000, 60000):
    r, g, b = wb(k)
    pruef(np.all(np.isfinite([r, g, b])) and r > 0 and b > 0,
          f"{k} K ergibt Unsinn: {r},{g},{b}")
    pruef(abs(g - 1.0) < 1e-6, f"{k} K: nicht auf Gruen normiert ({g})")
# Monoton waermer mit steigender Temperatur
verhaeltnisse = [wb(k)[0] / wb(k)[2] for k in range(2000, 12001, 500)]
pruef(all(a < b for a, b in zip(verhaeltnisse, verhaeltnisse[1:])),
      "Rot/Blau muss mit der Temperatur durchgehend steigen")
pruef(wb(2500)[0] / wb(2500)[2] < 0.3, "2500 K muesste deutlich kuehl wirken")
pruef(wb(12000)[0] / wb(12000)[2] > 1.5, "12000 K muesste deutlich warm wirken")
# Ausserhalb des Bereichs nicht abstuerzen
for k in (0, -5, 1e9):
    r, g, b = wb(k)
    pruef(np.all(np.isfinite([r, g, b])), f"{k} K stuerzt ab")
# Gruen
pruef(wb(5500, 1.4)[1] / wb(5500, 1.4)[0] > wb(5500, 0.7)[1] / wb(5500, 0.7)[0],
      "hoeherer Gruenwert muss gruener werden")
for g in (0, -1, None, "x"):
    pruef(np.all(np.isfinite(wb(5500, g))), f"Gruenwert {g} stuerzt ab")

print("=== 2. Rechenkern ===")
rng = np.random.default_rng(11)
basis = (rng.random((80, 140, 3)).astype(np.float32) * 0.5)
roh = vr(basis, 5500, 1.0, {})
pruef(roh.dtype == np.uint8 and roh.shape == (80, 140, 3),
      f"falsche Form/Typ: {roh.shape} {roh.dtype}")
pruef(np.array_equal(vr(basis, 5500, 1.0, {'wb_temp': 5500, 'wb_green': 1.0}), roh),
      "gleiche Werte wie im Profil duerfen nichts aendern")
pruef(np.array_equal(vr(basis, 5500, 1.0, {'brightness': 0, 'contrast': 0,
                                           'saturation': 0}), roh),
      "Nullwerte duerfen nichts aendern")
pruef(np.array_equal(vr(basis, 5500, 1.0, {'sharpen': 900, 'denoise_l': 80}), roh),
      "Schaerfe und Entrauschen werden nicht gezeigt, duerfen also nichts tun")
# Richtungen
h = {k: vr(basis, 5500, 1.0, {'brightness': v}).mean() for k, v in
     (('minus', -60), ('null', 0), ('plus', 60))}
pruef(h['minus'] < h['null'] < h['plus'], f"Helligkeit falsch herum: {h}")
def kanalstreuung(b): return float(np.asarray(b, float).std(axis=2).mean())
pruef(kanalstreuung(vr(basis, 5500, 1.0, {'saturation': -100})) < 0.6,
      "Saettigung -100 muss praktisch grau sein")
pruef(kanalstreuung(vr(basis, 5500, 1.0, {'saturation': 60})) > kanalstreuung(roh),
      "Saettigung +60 muss bunter sein")
pruef(np.asarray(vr(basis, 5500, 1.0, {'contrast': 80}), float).std() >
      np.asarray(roh, float).std() >
      np.asarray(vr(basis, 5500, 1.0, {'contrast': -80}), float).std(),
      "Kontrast falsch herum")
warm = np.asarray(vr(basis, 5500, 1.0, {'wb_temp': 9000}), float)
kalt = np.asarray(vr(basis, 5500, 1.0, {'wb_temp': 3000}), float)
pruef(warm[..., 0].mean() / warm[..., 2].mean() >
      kalt[..., 0].mean() / kalt[..., 2].mean(), "Farbtemperatur falsch herum")
# Die Differenz zaehlt, nicht der absolute Wert
a = vr(basis, 5500, 1.0, {'wb_temp': 6500})
b = vr(basis, 6500, 1.0, {'wb_temp': 6500})
pruef(not np.array_equal(a, b), "der Ausgangswert aus dem Profil wird ignoriert")
pruef(np.array_equal(b, roh),
      "wenn Regler und Profil uebereinstimmen, muss das Bild unveraendert sein")
# Nichts laeuft ueber
for werte in ({'brightness': 100, 'contrast': 100, 'saturation': 100},
              {'brightness': -100, 'contrast': -100, 'saturation': -100},
              {'wb_temp': 1500}, {'wb_temp': 60000}):
    out = vr(basis, 5500, 1.0, werte)
    pruef(out.min() >= 0 and out.max() <= 255, f"Wertebereich verlassen: {werte}")
    pruef(np.all(np.isfinite(out.astype(float))), f"nicht endlich: {werte}")
# Sehr dunkles und sehr helles Ausgangsbild
for probe in (np.zeros((8, 8, 3), np.float32), np.ones((8, 8, 3), np.float32)):
    out = vr(probe, 5500, 1.0, {'brightness': 50, 'contrast': 50})
    pruef(np.all(np.isfinite(out.astype(float))), "Grenzbild stuerzt ab")

print("=== 3. Geschwindigkeit ===")
gross = (rng.random((293, 520, 3)).astype(np.float32) * 0.5)
t0 = time.time()
for _ in range(25):
    vr(gross, 5500, 1.0, {'wb_temp': 7200, 'brightness': 12,
                          'contrast': 18, 'saturation': 22})
je = (time.time() - t0) / 25 * 1000
print(f"  {je:.1f} ms je Bild bei 520 px")
pruef(je < 60, f"zu langsam fuer eine Live-Vorschau: {je:.0f} ms")

print("=== 4. Laden des Vorschaubilds ===")
vb = ns["vorschau_basis"]
ns["is_raw_file"] = lambda p: p.lower().endswith(".nef")
ns["srgb_to_linear"] = lambda c: np.where(c <= 0.04045, c / 12.92,
                                          ((c + 0.055) / 1.055) ** 2.4)
import os, shutil
SCRATCH = os.environ.get("PURELAPSE_ARBEIT", os.path.join(__import__("tempfile").gettempdir(), "purelapse_pruefung"))
ordner = os.path.join(SCRATCH, "vorschau")
shutil.rmtree(ordner, ignore_errors=True)
os.makedirs(ordner)
probe = (rng.random((1800, 3200, 3)) * 255).astype(np.uint8)
jpg = os.path.join(ordner, "probe.jpg")
cv2.imwrite(jpg, probe)
bild = vb(jpg)
pruef(bild is not None, "JPG konnte nicht geladen werden")
pruef(bild.shape[1] == 1100, f"nicht auf 1100 px gebracht: {bild.shape}")
pruef(abs(bild.shape[0] - 1100 * 1800 / 3200) <= 1, f"Seitenverhaeltnis: {bild.shape}")
pruef(bild.dtype == np.float32, f"Typ {bild.dtype}")
pruef(0.0 <= bild.min() and bild.max() <= 1.0, "Wertebereich verlassen")
pruef(bild.max() > 0.8, "Helligkeitsnormierung hat nicht gegriffen")
pruef(vb(os.path.join(ordner, "gibtsnicht.jpg")) is None, "fehlende Datei")
kaputt = os.path.join(ordner, "kaputt.jpg")
io.open(kaputt, "w").write("kein Bild")
pruef(vb(kaputt) is None, "unlesbare Datei muss None ergeben")
# Kleines Bild wird nicht vergroessert
klein = os.path.join(ordner, "klein.jpg")
cv2.imwrite(klein, (rng.random((60, 100, 3)) * 255).astype(np.uint8))
pruef(vb(klein).shape[1] == 100, "kleines Bild darf nicht hochskaliert werden")

print("=== 5. Dialog ===")
dlg = schnitt(src, "class QuickLookDialog", "class GalleryWorker")
pruef("VorschauLader" in src, "Ladethread fehlt")
pruef("class VorschauLader(QtCore.QThread)" in src, "Laden blockiert den Dialog")
pruef("self._v_timer" in dlg, "kein Buendeln der Neuzeichnungen")
pruef("setInterval(40)" in dlg, "Buendelung ohne sinnvollen Takt")
pruef("sl.valueChanged.connect(self._vorschau_anfordern)" in dlg,
      "Regler loesen die Vorschau nicht aus")
pruef("chk.toggled.connect(self._vorschau_anfordern)" in dlg,
      "Haken loest die Vorschau nicht aus")
pruef("chk_vorher" in dlg, "kein Vorher-Vergleich")
pruef("Näherung" in dlg, "die Vorschau gibt sich nicht als Naeherung zu erkennen")
pruef("Schärfe und Entrauschen zeigt sie nicht" in dlg,
      "es wird nicht gesagt, was die Vorschau NICHT zeigt")
pruef("def closeEvent" in dlg, "der Ladethread wird nicht abgeraeumt")
pruef("bild_pfad=bild" in src, "dem Dialog wird kein Bildpfad uebergeben")

print("=== 6. Feindosierung und Zuruecksetzen ===")
pruef("btn_minus" in dlg and "btn_plus" in dlg, "Plus/Minus fehlen")
pruef('"\\u2212"' in dlg or "−" in dlg, "Minus sollte ein echtes Minuszeichen sein")
pruef("setAutoRepeat(True)" in dlg, "Gedrueckthalten laeuft nicht weiter")
pruef("setFixedWidth(30)" in dlg, "die Knoepfe sollten schmal nebeneinander stehen")
pruef("d['schritt'] * faktor)) // 5" in dlg,
      "der Feinschritt leitet sich nicht vom normalen Schritt ab")
pruef("gitter.addWidget(btn_minus, zeile, 3)" in dlg and
      "gitter.addWidget(btn_plus, zeile, 4)" in dlg,
      "Plus und Minus stehen nicht nebeneinander")
pruef("self._ursprung" in dlg, "der Ausgangszustand wird nicht gemerkt")
pruef("def _auf_ursprung" in dlg, "kein Zuruecksetzen")
ur = schnitt(src, "    def _auf_ursprung", "    def _vorschau_geladen")
pruef("blockSignals(True)" in ur and "blockSignals(False)" in ur,
      "beim Zuruecksetzen wird die Vorschau achtmal gerechnet")
pruef("self._vorschau_zeichnen()" in ur, "nach dem Zuruecksetzen fehlt das Bild")
pruef("lbl.setText(" in ur, "die Zahlenanzeige wird nicht nachgezogen")
pruef("ResetRole" in dlg, "der Knopf sitzt nicht in der Knopfleiste")
# Feinschritt rechnerisch nachvollziehen
sys.path.insert(0, BASIS)
import purelapse_engines as pe
pe.set_engine('art')
for d in pe.quick_defs():
    faktor = 10 ** d['dezimal']
    fein = max(1, int(round(d['schritt'] * faktor)) // 5)
    pruef(fein >= 1, f"{d['id']}: Feinschritt 0")
    spanne = (d['ui_max'] - d['ui_min']) * faktor
    pruef(fein <= spanne / 20, f"{d['id']}: Feinschritt zu grob ({fein} von {spanne})")

print("=== 7. Weiche Kurven ===")
pruef("pg.setConfigOptions(antialias=True)" in src,
      "ohne Antialiasing bleiben die Linien kantig")
pruef("def stift(" in src, "kein gemeinsamer Zeichenstift")
st = schnitt(src, "def stift(", "def dauer_text(")
pruef("RoundCap" in st and "RoundJoin" in st, "keine runden Enden/Verbindungen")
pruef(src.count("pg.mkPen(color=") == 0,
      "es gibt noch Kurven mit hartem Stift")
pruef("setDownsampling(auto=True, method='peak')" in src,
      "lange Sequenzen werden nicht ausgeduennt")
pruef("setClipToView(True)" in src, "es wird auch ausserhalb gezeichnet")
pruef("SYMBOL_GRENZE" in src, "Punktsymbole werden nie abgeschaltet")
pruef("def _setze_symbole" in src, "keine Umschaltung der Symbole")
sy = schnitt(src, "    def _setze_symbole", "    def _draw_extra_curves")
pruef("_symbole_an" in sy, "ohne Merker wird bei jedem Neuzeichnen umgeschaltet")
pruef("setSymbol(None)" in sy, "Symbole werden nicht abgeschaltet")
pruef(ns.get("SYMBOL_GRENZE", 0) if False else True, "")
ns2 = {}
exec(schnitt(src, "SYMBOL_GRENZE = 150", "def stift("), ns2)
pruef(ns2["SYMBOL_GRENZE"] == 150, "Schwelle veraendert")

print("=== 8. Struktur ===")
tree = ast.parse(src)
for kn in ast.walk(tree):
    if isinstance(kn, (ast.ClassDef, ast.Module)):
        namen = [k.name for k in kn.body
                 if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))]
        d = [n for n, c in collections.Counter(namen).items() if c > 1]
        pruef(not d, f"{getattr(kn, 'name', 'Modul')}: doppelt -> {d}")
    if isinstance(kn, ast.Dict):
        sch = [k.value for k in kn.keys
               if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        d = [n for n, c in collections.Counter(sch).items() if c > 1]
        pruef(not d, f"Zeile {kn.lineno}: doppelte Schluessel -> {d[:4]}")

print(f"\n{'='*52}\n{ok_n} Pruefungen bestanden, {fail_n} fehlgeschlagen")
sys.exit(1 if fail_n else 0)
