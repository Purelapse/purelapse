# -*- coding: utf-8 -*-
"""Tiefen aufhellen, Lichter abdunkeln, Dynamik - und die Automatik dazu.

Die drei Engines haben dafuer verschiedene Werkzeuge:
  ART          Tonwert-Equalizer, fuenf Baender
  RawTherapee  [Shadows & Highlights] und [Vibrance]
  darktable    Modul shadhi und die Dynamik in colorbalancergb
Ein Regler soll in allen dreien ungefaehr dasselbe bedeuten. Geprueft wird,
was in die Dateien kommt, was zurueckgelesen wird, ob die Naeherung in die
richtige Richtung wirkt - ohne Hoefe an Kanten - und ob die Automatik die
Regler sinnvoll setzt."""
import os, sys, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

print("=== 1. ART: Tonwert-Equalizer ===")
art = {'ToneEqualizer': {'Enabled': 'false', 'Band0': '0', 'Band1': '0', 'Band2': '0',
                         'Band3': '0', 'Band4': '0', 'Regularization': '4', 'Pivot': '0'},
       'Saturation': {'Enabled': 'false', 'Saturation': '0', 'Vibrance': '0'}}
vorh, fehl = pe.quick_available(art, 'art')
ids = {d['id'] for d in vorh}
pruef({'shadows', 'highlights', 'vibrance'} <= ids, f"Regler fehlen: {ids}")
neu, geschrieben, _ = pe.schnell_profil(art, {'shadows': 50, 'highlights': 40, 'vibrance': 20}, None, 'art')
te = neu['ToneEqualizer']
pruef(te['Enabled'] == 'true', "Equalizer nicht eingeschaltet")
pruef((te['Band0'], te['Band1'], te['Band2']) == ('18', '30', '10'), f"Tiefen-Baender: {te}")
pruef((te['Band3'], te['Band4']) == ('-8', '-20'), f"Lichter-Baender: {te}")
pruef(te['Regularization'] == '4' and te['Pivot'] == '0', "fremde Werte veraendert")
pruef(neu['Saturation']['Vibrance'] == '20' and neu['Saturation']['Saturation'] == '0', "Dynamik")
pruef(neu['Saturation']['Enabled'] == 'true', "Saettigungs-Werkzeug nicht eingeschaltet")
pruef(art['ToneEqualizer']['Band1'] == '0', "das Ausgangsprofil wurde veraendert")
w = pe.quick_read(neu, 'art')
pruef(abs(w['shadows'] - 50) < 1 and abs(w['highlights'] - 40) < 1 and w['vibrance'] == 20,
      f"Rueckgelesen: {w}")
w0 = pe.quick_read(art, 'art')
pruef(w0['shadows'] == 0 and w0['highlights'] == 0, "Neutralwert nicht 0")
nul, _g, _ = pe.schnell_profil(art, {'shadows': 0, 'highlights': 0}, None, 'art')
pruef(all(nul['ToneEqualizer'][f'Band{i}'] == '0' for i in range(5)), "0 muss alle Baender auf 0 lassen")
# Die Naeherung rechnet mit denselben Anteilen wie die Datei
art_k = pe.QUICK_KEYS['art']
tief = ((int(art_k['shadows'][1][-1]), art_k['shadows'][5]),) + tuple(
    (int(k[-1]), f) for k, f in art_k['shadows'][6])
licht = ((int(art_k['highlights'][1][-1]), art_k['highlights'][5]),) + tuple(
    (int(k[-1]), f) for k, f in art_k['highlights'][6])
pruef(tuple(pm.TE_TIEFEN) == tief and tuple(pm.TE_LICHTER) == licht,
      f"Naeherung und Datei auseinander: {pm.TE_TIEFEN} / {tief}, {pm.TE_LICHTER} / {licht}")
# Umrechnung wie in ART (iptoneequalizer.cc: conv)
pruef(abs(pm._te_band_faktor(1, 50) - 2 ** 1.5) < 1e-9, "Band1 aufwaerts: Faktor 3")
pruef(abs(pm._te_band_faktor(1, -50) - 2 ** -1.0) < 1e-9, "Band1 abwaerts: Faktor 2")
pruef(abs(pm._te_band_faktor(4, -50) - 2 ** -1.5) < 1e-9, "Band4 abwaerts: Faktor 3")
pruef(abs(pm._te_band_faktor(2, 40) - 2 ** 1.0) < 1e-9, "Band2: Faktor 2,5")
l, f = pm.tonwert_kennlinie(0, 0)
pruef(np.allclose(f, 1.0, atol=0.02), "ohne Regler muss die Kennlinie 1 sein (bis auf die Raender wie in ART)")
l, f = pm.tonwert_kennlinie(100, 0)
pruef(f[np.argmin(abs(l + 6))] > 1.8 and abs(f[np.argmin(abs(l - 0))] - 1) < 0.1,
      f"Tiefen: -6 EV {f[np.argmin(abs(l + 6))]:.2f}, 0 EV {f[np.argmin(abs(l))]:.2f}")
l, f = pm.tonwert_kennlinie(0, 100)
pruef(f[np.argmin(abs(l - 0))] < 0.6 and abs(f[np.argmin(abs(l + 8))] - 1) < 0.1,
      f"Lichter: 0 EV {f[np.argmin(abs(l))]:.2f}, -8 EV {f[np.argmin(abs(l + 8))]:.2f}")

print("=== 2. RawTherapee ===")
rt = {'Shadows & Highlights': {'Enabled': 'false', 'Highlights': '0', 'HighlightTonalWidth': '70',
                               'Shadows': '0', 'ShadowTonalWidth': '30', 'Radius': '40', 'Lab': 'false'},
      'Vibrance': {'Enabled': 'false', 'Pastels': '0', 'Saturated': '0', 'PSThreshold': '0;75;'}}
neu, _g, _ = pe.schnell_profil(rt, {'shadows': 50, 'highlights': 40, 'vibrance': 20}, None, 'rt')
sh = neu['Shadows & Highlights']
pruef(sh['Enabled'] == 'true' and sh['Shadows'] == '15' and sh['Highlights'] == '30', f"{sh}")
pruef(sh['Radius'] == '40' and sh['ShadowTonalWidth'] == '30', "fremde Werte veraendert")
v = neu['Vibrance']
pruef(v['Enabled'] == 'true' and v['Pastels'] == '20' and v['Saturated'] == '20', f"Dynamik: {v}")
w = pe.quick_read(neu, 'rt')
pruef(abs(w['shadows'] - 50) < 2 and abs(w['highlights'] - 40) < 1 and w['vibrance'] == 20,
      f"Rueckgelesen: {w}")
ohne = {'Exposure': {'Brightness': '0', 'Contrast': '0', 'Saturation': '0'}}
_v, fehl = pe.quick_available(ohne, 'rt')
pruef({'shadows', 'highlights', 'vibrance'} <= {d['id'] for d in fehl},
      "ohne die Sektionen muessen die Regler gesperrt sein")

print("=== 3. darktable: shadhi und Dynamik ===")
dt = {pe.DT_STAPEL: {'reihenfolge': ''}}
neu, _g, _ = pe.schnell_profil(dt, {'shadows': 50}, None, 'dt')
sek = neu.get('dt:shadhi#0')
pruef(sek is not None and sek['~enabled'] == '1' and sek['~modversion'] == '5', f"Modul fehlt: {sek}")
if sek:
    pruef(abs(float(sek['shadows']) - 30.0) < 1e-6, f"Tiefen: {sek['shadows']}")
    pruef(float(sek['highlights']) == 0.0,
          "ein neues Modul darf nur das tun, was eingestellt ist (Darktables -50 waeren schon Wirkung)")
    roh = bytes.fromhex(sek['~params'])
    werte = struct.unpack('<iffffffffIfi', roh)
    pruef(werte == (0, 100.0, 30.0, 0.0, 0.0, 0.0, 50.0, 100.0, 50.0, 127,
                    struct.unpack('<f', struct.pack('<f', 0.000001))[0], 1),
          f"Feldwerte: {werte}")
    pruef('dt:shadhi#0' in neu[pe.DT_STAPEL]['reihenfolge'], "nicht im Stapel")
neu, _g, _ = pe.schnell_profil(dt, {'highlights': 40, 'vibrance': 25}, None, 'dt')
pruef(abs(float(neu['dt:shadhi#0']['highlights']) + 24.0) < 1e-6,
      f"Lichter muessen negativ werden: {neu['dt:shadhi#0']['highlights']}")
pruef(abs(float(neu['dt:colorbalancergb#0']['vibrance']) - 0.25) < 1e-6, "Dynamik")
w = pe.quick_read(neu, 'dt')
pruef(abs(w['highlights'] - 40) < 1e-3 and abs(w['vibrance'] - 25) < 1e-3, f"Rueckgelesen: {w}")

print("=== 3b. darktable: Modul nur in einem Keyframe wird weich ueberblendet ===")
kf1, _g, _ = pe.schnell_profil(dt, {'shadows': 50, 'vibrance': 30}, None, 'dt')
kf2 = {pe.DT_STAPEL: {'reihenfolge': ''}}
for t, soll in ((0.0, 30.0), (0.25, 22.5), (0.5, 15.0), (0.75, 7.5), (1.0, 0.0)):
    m = pe.interpolate_arp_dicts(kf1, kf2, t)
    sek = m.get('dt:shadhi#0')
    pruef(sek is not None and abs(float(sek['shadows']) - soll) < 1e-4,
          f"t={t}: Tiefen {None if sek is None else sek['shadows']}, erwartet {soll}")
    if sek:
        pruef(sek['~params'] == pe._dt_felder_packen('shadhi', sek), f"t={t}: Daten passen nicht")
    cb = m.get('dt:colorbalancergb#0')
    pruef(cb is not None and abs(float(cb['vibrance']) - 0.3 * (1 - t)) < 1e-4,
          f"t={t}: Dynamik {None if cb is None else cb['vibrance']}")
pruef(not pe.nicht_ueberblendbar(kf1, kf2),
      f"es darf keine Umschalt-Warnung mehr kommen: {pe.nicht_ueberblendbar(kf1, kf2)}")
m = pe.interpolate_arp_dicts(kf2, kf1, 0.5)
pruef(abs(float(m['dt:shadhi#0']['shadows']) - 15.0) < 1e-4, "umgekehrte Richtung")
# Ein Modul, das sich nicht neutral stellen laesst, schaltet weiter um
pruef(pe.dt_neutral_gegenstueck('dt:sharpen#0', kf1.get('dt:sharpen#0') or {'~modversion': '1'}) is None,
      "Schaerfen hat keinen Nullwert und darf nicht ergaenzt werden")
aus = dict(kf1['dt:shadhi#0']); aus['~enabled'] = '0'
pruef(pe.dt_neutral_gegenstueck('dt:shadhi#0', aus) is None,
      "ein ausgeschaltetes Modul bleibt, wie es ist")

print("=== 4. Naeherung ===")
rng = np.random.default_rng(3)
B, H = 400, 240
x = np.linspace(0, 1, B, dtype=np.float32)
bild = np.empty((H, B, 3), np.float32)
bild[:] = np.where(x < 0.5, 0.015, 0.7)[None, :, None]     # dunkel | hell
bild *= (1 + rng.normal(0, 0.02, (H, B, 1))).astype(np.float32)
links, rechts = (slice(None), slice(20, 150)), (slice(None), slice(250, 380))
t = pm.tiefen_lichter(bild, 60, 0)
pruef(t[links].mean() > bild[links].mean() * 1.6, "Tiefen werden nicht hell genug")
pruef(abs(t[rechts].mean() / bild[rechts].mean() - 1) < 0.05, "Tiefen duerfen das Helle nicht anfassen")
t = pm.tiefen_lichter(bild, 0, 60)
pruef(t[rechts].mean() < bild[rechts].mean() * 0.8, "Lichter werden nicht dunkler")
pruef(abs(t[links].mean() / bild[links].mean() - 1) < 0.05, "Lichter duerfen das Dunkle nicht anfassen")
# Kein Hof: das Dunkle direkt an der Kante verhaelt sich wie das weit weg
an_kante = t[:, 190:199].mean() / bild[:, 190:199].mean()
weit_weg = t[:, 20:60].mean() / bild[:, 20:60].mean()
pruef(abs(an_kante - weit_weg) < 0.05, f"Hof an der Kante: {an_kante:.3f} gegen {weit_weg:.3f}")
an_kante = pm.tiefen_lichter(bild, 60, 0)[:, 201:210].mean() / bild[:, 201:210].mean()
pruef(abs(an_kante - 1) < 0.06, f"Aufhellung strahlt ueber die Kante: {an_kante:.3f}")
pruef(pm.tiefen_lichter(bild, 0, 0) is not None and
      np.array_equal(pm.tiefen_lichter(bild, 0, 0), bild), "ohne Regler muss das Bild bleiben")
# Dynamik: blasse Farben gewinnen mehr als satte, Grau bleibt grau
blass = np.array([[[0.30, 0.27, 0.25]]], np.float32)
satt = np.array([[[0.60, 0.15, 0.05]]], np.float32)
grau = np.array([[[0.30, 0.30, 0.30]]], np.float32)
def abstand(p):
    return float(p.max() - p.min())
zb = abstand(pm.dynamik(blass, 40)) / abstand(blass)
zs = abstand(pm.dynamik(satt, 40)) / abstand(satt)
pruef(zb > zs > 1.0, f"Dynamik: blass x{zb:.2f}, satt x{zs:.2f}")
pruef(np.allclose(pm.dynamik(grau, 40), grau, atol=1e-5), "Grau bekommt Farbe")
pruef(np.array_equal(pm.dynamik(blass, 0), blass), "Dynamik 0 veraendert das Bild")
pruef(abstand(pm.dynamik(blass, -60)) < abstand(blass), "negative Dynamik muss entsaettigen")
# vorschau_rechnen nimmt die neuen Regler mit
v0 = pm.vorschau_rechnen(bild, 5500, 1.0, {})
v1 = pm.vorschau_rechnen(bild, 5500, 1.0, {'shadows': 60})
pruef(v1[links].mean() > v0[links].mean() + 10, "Vorschau ignoriert die Tiefen")
v2 = pm.vorschau_rechnen(bild, 5500, 1.0, {'highlights': 60})
pruef(v2[rechts].mean() < v0[rechts].mean() - 10, "Vorschau ignoriert die Lichter")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
na = src[src.index("    def _naeherung"):src.index("    def _echt_zeigen")]
pruef(all(f"'{k}'" in na for k in ('shadows', 'highlights', 'vibrance')),
      "die Naeherung auf dem Bild der Engine kennt die neuen Regler nicht")

print("=== 5. Automatik ===")
auto = pm.auto_optimieren
def szene_bild(dunkel=0.3, hell=0.2, iso_rauschen=0.0):
    """Linear: ein Teil dunkel, ein Teil hell, Rest Mitte."""
    b = np.full((240, 400, 3), 0.18, np.float32)
    n_d = int(400 * dunkel); n_h = int(400 * hell)
    b[:, :n_d] = 0.006
    b[:, 400 - n_h:] = 0.95
    b[..., 0] *= 1.05; b[..., 2] *= 0.95
    return np.clip(b * (1 + rng.normal(0, 0.03, b.shape)).astype(np.float32), 0, 1)
w_d, g_d = auto(szene_bild(dunkel=0.4, hell=0.0), iso=100)
pruef(w_d.get('shadows', 0) >= 30, f"viel Dunkles braucht Aufhellung: {w_d}")
w_h, g_h = auto(szene_bild(dunkel=0.0, hell=0.3), iso=100)
pruef(w_h.get('highlights', 0) >= 30, f"viel Helles braucht Zeichnung: {w_h}")
pruef(w_h.get('shadows', 0) < w_d.get('shadows', 0), "ohne Dunkles keine Aufhellung noetig")
w_n, g_n = auto(szene_bild(dunkel=0.8, hell=0.02), iso=100)
pruef(w_n.get('shadows', 0) <= 15, f"eine Nacht darf nicht grau werden: {w_n}")
pruef(any("Nacht" in x for x in g_n), f"die Nacht wird nicht genannt: {g_n}")
pruef(w_n.get('contrast', 0) <= pm.AUTO_KONTRAST_NACHT, f"Kontrast in der Nacht: {w_n}")
w_i, g_i = auto(szene_bild(dunkel=0.4, hell=0.0), iso=6400)
pruef(w_i.get('shadows', 0) < w_d.get('shadows', 0), f"hohe ISO: weniger aufhellen {w_i} / {w_d}")
pruef(any("ISO" in x and "Tiefen" in x for x in g_i), f"Begruendung fehlt: {g_i}")
for probe in (szene_bild(0.9, 0.0), szene_bild(0.0, 0.9), szene_bild(0.5, 0.5)):
    wx, _ = auto(probe, iso=100)
    pruef(0 <= wx.get('shadows', 0) <= pm.AUTO_TIEFEN_MAX and
          0 <= wx.get('highlights', 0) <= pm.AUTO_LICHTER_MAX, f"ausserhalb der Grenzen: {wx}")
wx, _ = auto(szene_bild(0.4, 0.3), iso=100, erlaubt={'brightness', 'contrast'})
pruef(set(wx) <= {'brightness', 'contrast'}, f"gesperrte Regler vorgeschlagen: {wx}")
en, _ = auto(szene_bild(0.4, 0.3), iso=100, lang='en')
pruef(any("Lift shadows" in x for x in _) or 'shadows' not in en, "englische Begruendung fehlt")
# Kein Wort ueber andere Programme in der Automatik (Quelltext und
# Begruendung). "Adobe" nirgends; Lightroom ist seit 2.46 eine Engine und
# darf im uebrigen Programm vorkommen - nur nicht in der Automatik.
import re as _re
def _abschnitt(kopf):
    i = src.index(kopf)
    m = _re.compile(r"\n(    )?def |\nclass ").search(src, i + len(kopf))
    return src[i:m.start() if m else len(src)]
auto_src = "".join(_abschnitt(k) for k in (
    "def auto_optimieren", "    def _automatisch", "    def _auto_ausgangsprofil",
    "    def _auto_engine_fertig", "    def _auto_anwenden"))
pruef(len(auto_src) > 2000, "Automatik im Quelltext nicht gefunden")
pruef("adobe" not in src.lower(), "'adobe' steht im Quelltext")
for wort in ("lightroom", "camera raw"):
    pruef(wort not in auto_src.lower(), f"'{wort}' steht in der Automatik")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
