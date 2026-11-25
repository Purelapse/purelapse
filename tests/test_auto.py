#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Pruefungen fuer das automatische Optimieren, das Histogramm, das
Uebernehmen von anderen Keyframes und die Keyframe-Marken im Diagramm.
"""
import io, os, ast, sys, math, shutil, collections
import numpy as np
import cv2

BASIS = os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = io.open(f"{BASIS}/purelapse_main.py", encoding="utf-8").read()
SCRATCH = os.environ.get("PURELAPSE_ARBEIT", os.path.join(__import__("tempfile").gettempdir(), "purelapse_pruefung"))

ok_n = fail_n = 0
def pruef(b, text):
    global ok_n, fail_n
    if b: ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")

def schnitt(txt, von, bis):
    a = txt.index(von)
    return txt[a:txt.index(bis, a)]

ns = {"np": np, "cv2": cv2, "math": math}
exec(schnitt(src, "VORSCHAU_BREITE = 1100", "# Ab wie vielen Bildern"), ns)
auto = ns["auto_optimieren"]
hist = ns["histogramm_bild"]

def testbild(mittel=0.2, spanne=0.3, buntheit=0.0, struktur=0.0, groesse=(120, 200)):
    """Lineares Testbild mit einstellbarer Helligkeit, Spanne und Farbe."""
    rng = np.random.default_rng(5)
    g = rng.normal(mittel, spanne / 6.0, groesse).astype(np.float32)
    if struktur:
        g = g + rng.normal(0, struktur, groesse).astype(np.float32)
    bild = np.stack([g, g, g], axis=2)
    if buntheit:
        bild[..., 0] *= (1.0 + buntheit)
        bild[..., 2] *= (1.0 - buntheit)
    return np.clip(bild, 0.0, 1.0).astype(np.float32)

print("=== 1. Automatisch optimieren: Grundverhalten ===")
w, g = auto(None)
pruef(w == {} and g == [], "ohne Bild muss es leer bleiben")
dunkel = testbild(mittel=0.05, spanne=0.1)
w, g = auto(dunkel, iso=100)
pruef(isinstance(w, dict) and isinstance(g, list), "falsche Rueckgabeform")
pruef(len(g) >= 3, f"zu wenig Begruendung: {g}")
pruef(all(isinstance(x, str) and x for x in g), "leere Begruendung")
pruef('wb_temp' not in w and 'wb_green' not in w,
      "der Weissabgleich darf nicht angefasst werden")
pruef(any("Weissabgleich" in x for x in g),
      "dass der Weissabgleich bleibt, muss gesagt werden")

print("=== 2. Helligkeit ===")
w_d, _ = auto(testbild(mittel=0.04, spanne=0.08), iso=100)
w_h, _ = auto(testbild(mittel=0.85, spanne=0.10), iso=100)
pruef(w_d.get('brightness', 0) > 0, f"dunkles Bild muss heller werden: {w_d}")
pruef(w_h.get('brightness', 0) < 0, f"helles Bild muss dunkler werden: {w_h}")
for probe in (0.02, 0.2, 0.5, 0.9):
    w_x, _ = auto(testbild(mittel=probe, spanne=0.1), iso=100)
    pruef(abs(w_x.get('brightness', 0)) <= ns["AUTO_HELLIGKEIT_MAX"],
          f"Helligkeit sprengt die Grenze bei Mittelwert {probe}")
# Ein schon passendes Bild bleibt in Ruhe
passend = testbild(mittel=0.16, spanne=0.3)
w_p, g_p = auto(passend, iso=100)
pruef(abs(w_p.get('brightness', 0)) < ns["AUTO_HELLIGKEIT_MAX"],
      "passendes Bild wird zu stark angefasst")

print("=== 3. Kontrast ===")
flach = testbild(mittel=0.25, spanne=0.06)
weit = testbild(mittel=0.3, spanne=1.4)
# Ohne Tiefen und Lichter allein nach dem Umfang des Histogramms
nur_ton = {'brightness', 'contrast', 'saturation', 'sharpen'}
w_f, g_f = auto(flach, iso=100, erlaubt=nur_ton)
w_w, g_w = auto(weit, iso=100, erlaubt=nur_ton)
pruef(w_f.get('contrast', 0) > 0, f"flaches Bild braucht Kontrast: {w_f}")
pruef(w_w.get('contrast', 0) == 0,
      f"ein voll ausgenutztes Histogramm darf nicht gestreckt werden: {w_w}")
pruef(auto(testbild(mittel=0.3, spanne=3.0), iso=100, erlaubt=nur_ton)[0].get('contrast', 0) == 0,
      "ein randvolles Histogramm erst recht nicht")
# Mit Tiefen und Lichtern: hoechstens der Ausgleich fuer den Mittelton
w_w2, g_w2 = auto(weit, iso=100)
pruef(w_w2.get('contrast', 0) <= ns["AUTO_KONTRAST_AUSGLEICH"],
      f"volles Histogramm: mehr als der Ausgleich: {w_w2}")
if w_w2.get('contrast', 0):
    pruef(any("Biss" in x for x in g_w2), f"Begruendung fehlt: {g_w2}")
pruef(any("Histogramm" in x for x in g_w), "die Begruendung nennt den Grund nicht")
for probe in (0.02, 0.1, 0.3, 0.8, 2.0):
    w_x, _ = auto(testbild(mittel=0.3, spanne=probe), iso=100)
    pruef(0 <= w_x.get('contrast', 0) <= ns["AUTO_KONTRAST_MAX"],
          f"Kontrast ausserhalb der Grenze bei Spanne {probe}")

print("=== 4. Saettigung: nicht altbacken ===")
grau = testbild(mittel=0.3, spanne=0.3, buntheit=0.0)
bunt = testbild(mittel=0.3, spanne=0.3, buntheit=0.55)
# Gibt es die Dynamik, uebernimmt sie die Farbe; die Saettigung bleibt.
w_g, _ = auto(grau, iso=100)
w_b, gb = auto(bunt, iso=100)
pruef(w_g.get('vibrance', 0) > 0, f"graues Bild braucht Dynamik: {w_g}")
pruef('saturation' not in w_g and 'saturation' not in w_b,
      f"neben der Dynamik darf die Saettigung nicht mitlaufen: {w_g} {w_b}")
pruef(w_b['vibrance'] < w_g['vibrance'],
      "ein farbkraeftiges Bild darf nicht genauso viel Dynamik bekommen")
for probe in (0.0, 0.2, 0.5, 0.9):
    w_x, _ = auto(testbild(mittel=0.3, spanne=0.3, buntheit=probe), iso=100)
    pruef(ns["AUTO_DYNAMIK_MIN"] * 0.5 <= w_x.get('vibrance', 0) <= ns["AUTO_DYNAMIK_MAX"],
          f"Dynamik ausserhalb der Grenze bei Buntheit {probe}: {w_x}")
# Ohne Dynamik im Profil wie bisher ueber die Saettigung
ohne_dyn = {'brightness', 'contrast', 'saturation', 'sharpen', 'denoise_l', 'denoise_c'}
w_g, _ = auto(grau, iso=100, erlaubt=ohne_dyn)
w_b, gb = auto(bunt, iso=100, erlaubt=ohne_dyn)
pruef(w_g.get('saturation', 0) > 0, f"graues Bild braucht Farbe: {w_g}")
pruef(w_b.get('saturation', 0) <= w_g.get('saturation', 0),
      "ein farbkraeftiges Bild darf nicht genauso aufgedreht werden")
for probe in (0.0, 0.2, 0.5, 0.9):
    w_x, _ = auto(testbild(mittel=0.3, spanne=0.3, buntheit=probe), iso=100,
                  erlaubt=ohne_dyn)
    pruef(0 <= w_x.get('saturation', 0) <= ns["AUTO_SAETTIGUNG_MAX"],
          f"Saettigung ausserhalb der Grenze bei Buntheit {probe}")
# Kontrast und Saettigung duerfen nicht beide voll aufdrehen
w_k, _ = auto(testbild(mittel=0.25, spanne=0.05, buntheit=0.0), iso=100,
              erlaubt=ohne_dyn)
pruef(not (w_k.get('contrast', 0) >= ns["AUTO_KONTRAST_MAX"]
           and w_k.get('saturation', 0) >= ns["AUTO_SAETTIGUNG_MAX"]),
      "Kontrast und Saettigung gleichzeitig am Anschlag - genau das sieht alt aus")

print("=== 5. Schaerfe und Entrauschen ===")
glatt = testbild(mittel=0.3, spanne=0.3, struktur=0.0)
rauh = testbild(mittel=0.3, spanne=0.3, struktur=0.06)
w_gl, _ = auto(glatt, iso=100)
w_ra, _ = auto(rauh, iso=100)
pruef(w_gl.get('sharpen', 0) > 0 and w_ra.get('sharpen', 0) > 0,
      "Schaerfe muss immer vorgeschlagen werden - darum geht es ja")
pruef(w_ra['sharpen'] >= w_gl['sharpen'],
      f"strukturreiches Motiv vertraegt mehr: {w_gl['sharpen']} vs {w_ra['sharpen']}")
for wv in (w_gl, w_ra):
    pruef(ns["AUTO_SCHAERFE_GLATT"] <= wv['sharpen'] <= ns["AUTO_SCHAERFE_DETAIL"],
          f"Schaerfe ausserhalb des Rahmens: {wv['sharpen']}")
en = ns["_entrauschen_aus_iso"]
pruef(en(100)[0] == 0 and en(200)[0] == 0, "ISO 100-200 braucht kein Entrauschen")
werte = [en(i)[0] for i in (200, 400, 800, 1600, 3200, 6400, 25600)]
pruef(all(a <= b for a, b in zip(werte, werte[1:])),
      f"Entrauschen muss mit ISO steigen: {werte}")
pruef(en(25600)[0] <= 100 and en(25600)[1] <= 100, "Entrauschen sprengt den Bereich")
for murks in (None, "x", -5):
    pruef(en(murks)[0] >= 0, f"ISO {murks} stuerzt ab")
w_iso, g_iso = auto(glatt, iso=3200)
pruef(w_iso.get('denoise_l', 0) > 0, "ISO 3200 muss Entrauschen vorschlagen")
pruef(any("3200" in x for x in g_iso), "der ISO-Wert fehlt in der Begruendung")

print("=== 6. Nur erlaubte Regler ===")
w_e, _ = auto(dunkel, iso=3200, erlaubt={'brightness', 'sharpen'})
pruef(set(w_e.keys()) <= {'brightness', 'sharpen'},
      f"es wurden gesperrte Regler vorgeschlagen: {sorted(w_e)}")
pruef(auto(dunkel, iso=100, erlaubt=set())[0] == {},
      "ohne erlaubte Regler darf nichts kommen")

print("=== 7. Vorgeschlagene Werte sind einsetzbar ===")
sys.path.insert(0, BASIS)
import purelapse_engines as pe
for engine in ('art', 'rt'):
    pe.set_engine(engine)
    grenzen = {d['id']: d for d in pe.quick_defs()}
    for probe in (dunkel, flach, bunt, rauh, testbild(0.9, 0.2)):
        for iso in (100, 1600, 6400):
            vor, _ = auto(probe, iso=iso)
            for kid, wert in vor.items():
                d = grenzen[kid]
                pruef(d['ui_min'] <= wert <= d['ui_max'],
                      f"{engine}/{kid}: {wert} ausserhalb {d['ui_min']}..{d['ui_max']}")
                pruef(float(wert) == float(wert), f"{engine}/{kid}: kein Zahlwert")

print("=== 8. Histogramm ===")
rng = np.random.default_rng(1)
bild = (rng.random((100, 200, 3)) * 255).astype(np.uint8)
h = hist(bild, 300, 86)
pruef(h.shape == (86, 300, 3) and h.dtype == np.uint8, f"Form/Typ: {h.shape}")
pruef(h.std() > 0, "das Histogramm ist leer")
leer = hist(np.zeros((0, 0, 3), np.uint8), 300, 86)
pruef(leer.shape == (86, 300, 3), "leeres Bild stuerzt ab")
pruef(hist(None, 120, 40).shape == (40, 120, 3), "None stuerzt ab")
# Beschnitt wird markiert
schwarz = np.zeros((50, 50, 3), np.uint8)
weiss = np.full((50, 50, 3), 255, np.uint8)
hs, hw = hist(schwarz, 200, 60), hist(weiss, 200, 60)
pruef(tuple(hs[0, 0]) == (90, 140, 255), f"zulaufende Tiefen nicht markiert: {hs[0,0]}")
pruef(tuple(hw[0, -1]) == (255, 90, 90), f"ausbrennende Lichter nicht markiert: {hw[0,-1]}")
mitte = np.full((50, 50, 3), 128, np.uint8)
hm = hist(mitte, 200, 60)
pruef(tuple(hm[0, 0]) != (90, 140, 255) and tuple(hm[0, -1]) != (255, 90, 90),
      "Mittelgrau darf keine Warnstreifen bekommen")
# Jeder Kanal taucht auf
bunt_bild = np.zeros((40, 40, 3), np.uint8)
bunt_bild[..., 0] = 200; bunt_bild[..., 1] = 100; bunt_bild[..., 2] = 50
hb = hist(bunt_bild, 256, 70)
pruef(hb.std() > 0, "einfarbiges Bild ergibt kein Histogramm")

print("=== 8b. Die drei Befunde aus dem ersten Durchlauf ===")
# Ein komplett beschnittenes Bild MUSS gewarnt werden - vorher stieg die
# Funktion vorher aus, weil die inneren Balken leer sind.
for probe, spalte, erwartet in ((np.zeros((30, 30, 3), np.uint8), 0, (90, 140, 255)),
                                (np.full((30, 30, 3), 255, np.uint8), -1, (255, 90, 90))):
    hh = hist(probe, 180, 50)
    pruef(tuple(hh[0, spalte]) == erwartet,
          f"durchweg beschnittenes Bild ohne Warnung: {hh[0, spalte]}")
    pruef(tuple(hh[25, spalte]) == erwartet, "Warnstreifen nicht durchgehend")
# Kein Kammuster mehr: bei 300 Pixeln Breite duerfen keine Luecken
# entstehen, die es bei 256 Werten gar nicht gibt.
gleich = np.full((40, 40, 3), 128, np.uint8)
hk = hist(gleich, 300, 60)
# Nur die obere Haelfte betrachten: die Grundlinie laeuft zu Recht ueber
# die ganze Breite, der Ausschlag darf es nicht.
hoch = sum(1 for x in range(300) if hk[:30, x].max() > 100)
pruef(hoch < 20, f"ein einzelner Wert ergibt {hoch} hohe Spalten")
pruef(hoch >= 1, "der Ausschlag fehlt ganz")
# und er sitzt an der richtigen Stelle (Wert 128 von 256)
spalten = [x for x in range(300) if hk[:30, x].max() > 100]
mitte = sum(spalten) / len(spalten)
pruef(abs(mitte - 300 * 128 / 255) < 12,
      f"der Ausschlag sitzt bei Spalte {mitte:.0f}, erwartet ~{300*128/255:.0f}")
rng2 = np.random.default_rng(9)
breit = (rng2.normal(128, 40, (80, 120, 3)).clip(0, 255)).astype(np.uint8)
hb2 = hist(breit, 300, 60)
leere = sum(1 for x in range(5, 295) if hb2[:, x].max() <= 80)
pruef(leere < 40, f"{leere} leere Spalten - sieht nach Kamm aus")
# Kontrast: winzige Vorschlaege unterbleiben
for spanne in (0.86, 0.88, 0.95, 1.2):
    wv, _ = auto(testbild(mittel=0.3, spanne=spanne), iso=100)
    k = wv.get('contrast', 0)
    pruef(k == 0 or k >= 5, f"Spanne {spanne}: unsichtbarer Vorschlag {k}")

print("=== 9. Dialog ===")
dlg = schnitt(src, "class QuickLookDialog", "class GalleryWorker")
pruef("def _automatisch" in dlg, "Optimieren-Knopf ohne Funktion")
pruef("btn_auto" in dlg and "ActionRole" in dlg, "Knopf nicht in der Leiste")
pruef("self.btn_auto.setEnabled(False)" in dlg,
      "der Knopf muss gesperrt sein, bevor ein Bild da ist")
au = schnitt(src, "    def _automatisch", "    def begruendung")
pruef("erlaubt=set(self.regler.keys())" in au,
      "es werden Regler vorgeschlagen, die der Dialog nicht hat")
pruef("blockSignals(True)" in au, "die Vorschau rechnet bei jedem Regler neu")
pruef("self._vorschau_zeichnen()" in au, "nach dem Vorschlag fehlt das Bild")
pruef("setToolTip" in au, "die Begruendung ist nirgends nachlesbar")
pruef("lbl_histogramm" in dlg, "kein Histogramm im Dialog")
pruef("HISTOGRAMM_HOEHE" in src, "Hoehe des Histogramms nicht festgelegt")
zeich = schnitt(src, "    def _vorschau_zeichnen", "    def closeEvent")
pruef("histogramm_bild(" in zeich, "das Histogramm wird nicht mitgezeichnet")
pruef("def resizeEvent" in dlg, "die Vorschau waechst nicht mit dem Fenster")
pruef("def _vorschau_neu_skalieren" in dlg, "keine Anpassung an die Anzeigegroesse")
sk = schnitt(src, "    def _vorschau_neu_skalieren", "    def resizeEvent")
pruef("min(voll_b, platz_b" in sk, "es wird ueber die geladene Groesse hinaus skaliert")
pruef("INTER_AREA" in sk, "beim Verkleinern falsches Verfahren")
pruef("self.resize(940, 860)" in dlg, "der Dialog startet nicht groesser")
pruef(ns["VORSCHAU_BREITE"] >= 1000, "die Ladebreite reicht zum Zoomen nicht")

print("=== 10. Von anderem Keyframe uebernehmen ===")
pruef("def _uebernehmen" in dlg, "kein Uebernehmen")
pruef("cmb_uebernehmen" in dlg, "keine Auswahlliste")
ue = schnitt(src, "    def _uebernehmen", "    def _automatisch")
pruef("quick_read(fremd)" in ue, "das fremde Profil wird nicht gelesen")
pruef("abs(wert - float(d['neutral']))" in ue,
      "Neutralwerte wuerden die eigene Arbeit ueberschreiben")
pruef("continue" in ue, "es wird ohne Auswahl uebernommen")
pruef("self._vorschau_zeichnen()" in ue, "nach dem Uebernehmen fehlt das Bild")
pruef("andere=andere" in src, "dem Dialog werden keine anderen Keyframes gegeben")
pruef("if i == ziel" in src, "das eigene Bild steht mit in der Liste")
pruef("os.path.exists(sc)" in src, "Keyframes ohne Profil landen in der Liste")

print("=== 11. Keyframe-Marken im Diagramm ===")
pruef("def _kf_linie" in src, "keine eigene Methode fuer die Marke")
kl = schnitt(src, "    def _kf_linie", "    def _setze_symbole")
pruef("stift(farbe, 2" in kl, "die Marke ist weiterhin nur ein Pixel breit")
pruef('label="★"' in kl, "kein Stern am oberen Rand")
pruef("'position': 0.96" in kl, "der Stern sitzt nicht oben")
pruef("setDefaultPadding(0.02)" in src,
      "ohne Rand verschwindet eine Marke bei Bild 0 hinter der Achse")
pruef(src.count("pg.InfiniteLine(\n                pos=index") == 0,
      "die alte Marke wird noch irgendwo gebaut")

print("=== 12. Struktur ===")
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
