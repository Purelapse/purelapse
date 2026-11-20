#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Pruefungen fuer die Lichter-Rekonstruktion: Erkennung des Farbstichs,
Naeherung in der Vorschau, Profilschluessel beider Engines, Warnungen.
"""
import io, os, ast, sys, math, shutil, collections
import numpy as np
import cv2

BASIS = os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = io.open(f"{BASIS}/purelapse_main.py", encoding="utf-8").read()
sys.path.insert(0, BASIS)
import purelapse_engines as pe

ok_n = fail_n = 0
def pruef(b, text):
    global ok_n, fail_n
    if b: ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")

def schnitt(txt, von, bis):
    return txt[txt.index(von):txt.index(bis)]

ns = {"np": np, "cv2": cv2, "math": math}
exec(schnitt(src, "VORSCHAU_BREITE = 1100", "# Ab wie vielen Bildern"), ns)
stich = ns["lichter_farbstich"]
bleichen = ns["lichter_ausbleichen"]
vr = ns["vorschau_rechnen"]

def sonnenbild(rosa=True, groesse=(200, 300), radius=28):
    """Dunkles Bild mit einem hellen Fleck - wahlweise weiss oder magenta."""
    h, w = groesse
    bild = np.full((h, w, 3), 0.12, dtype=np.float32)
    yy, xx = np.ogrid[:h, :w]
    scheibe = (yy - h // 2) ** 2 + (xx - w // 2) ** 2 <= radius ** 2
    if rosa:
        # Gruen steht am Anschlag und bleibt zurueck, Rot und Blau nicht
        bild[scheibe] = (1.0, 0.72, 0.98)
    else:
        bild[scheibe] = (1.0, 0.99, 1.0)
    return bild

print("=== 1. Farbstich erkennen ===")
a_rosa, flaeche_r, richtung_r = stich(sonnenbild(rosa=True))
a_weiss, flaeche_w, richtung_w = stich(sonnenbild(rosa=False))
pruef(a_rosa > 0.9, f"der rosa Fleck wird nicht erkannt: {a_rosa:.2f}")
pruef(richtung_r == 'magenta', f"Richtung falsch bestimmt: {richtung_r}")
pruef(a_weiss == 0.0, f"ein weisser Fleck darf nicht melden: {a_weiss:.2f}")
pruef(richtung_w == "", f"Richtung ohne Treffer: {richtung_w}")
pruef(0.0 < flaeche_r < 0.2, f"Flaechenanteil unplausibel: {flaeche_r:.3f}")
# Gruenstich wird als solcher erkannt
gruenstich = sonnenbild(rosa=False)
gruenstich[gruenstich[..., 1] > 0.9] = 0.0
gb = np.full((60, 60, 3), 0.1, np.float32); gb[20:40, 20:40] = (0.75, 1.0, 0.78)
# Gemeldet wird nur das Muster des rosa Sonnenballs. Helle, bunte Stellen
# anderer Farbe (Gruen, Orange eines Abendhimmels) sind echte Farben.
pruef(stich(gb)[0] == 0.0, f"gruene helle Flaeche als Fehler gemeldet: {stich(gb)}")
orange = np.full((60, 60, 3), 0.1, np.float32); orange[10:50, 10:50] = (1.0, 0.78, 0.5)
pruef(stich(orange)[0] == 0.0, f"Abendhimmel als verfaerbt gemeldet: {stich(orange)}")
# Grenzfaelle
pruef(stich(None) == (0.0, 0.0, ""), "None stuerzt ab")
pruef(stich(np.zeros((0, 0, 3), np.float32)) == (0.0, 0.0, ""), "leer stuerzt ab")
pruef(stich(np.zeros((30, 30, 3), np.float32)) == (0.0, 0.0, ""),
      "ein durchweg dunkles Bild hat keine Lichter")
pruef(stich(np.full((30, 30, 3), 0.5, np.float32)) == (0.0, 0.0, ""),
      "mittelhelles Grau hat keine Lichter")
# uint8-Eingang
rosa8 = (sonnenbild(rosa=True) * 255).astype(np.uint8)
a8 = stich(rosa8, linear=False)[0]
pruef(a8 > 0.9, f"uint8-Eingang wird nicht erkannt: {a8:.2f}")
pruef(abs(a8 - a_rosa) < 0.05, "uint8 und float kommen zu verschiedenen Zahlen")
# Ein schwacher Stich bleibt unter der Schwelle
schwach = np.full((60, 60, 3), 0.1, np.float32)
schwach[20:40, 20:40] = (1.0, 0.95, 0.99)
pruef(stich(schwach)[0] == 0.0, "ein Stich von 0.05 darf nicht melden")

print("=== 2. Naeherung der Rekonstruktion ===")
rosa = sonnenbild(rosa=True)
geheilt = bleichen(rosa, 1.0)
pruef(stich(geheilt)[0] < 0.1,
      f"nach der Rekonstruktion ist noch Stich da: {stich(geheilt)[0]:.2f}")
kern = geheilt[100, 150]
pruef(float(kern.max() - kern.min()) < 0.05,
      f"der Fleck ist nicht weiss geworden: {kern}")
# Die dunklen Teile bleiben unberuehrt
pruef(abs(float(geheilt[5, 5].mean()) - 0.12) < 1e-4,
      "die Rekonstruktion faerbt auch dunkle Bereiche um")
pruef(np.allclose(bleichen(rosa, 0.0), rosa), "Staerke 0 muss nichts tun")
def kernabstand(b):
    k = b[100, 150]
    return float(k.max() - k.min())
teil = bleichen(rosa, 0.5)
pruef(kernabstand(rosa) > kernabstand(teil) > kernabstand(geheilt),
      f"halbe Staerke liegt nicht dazwischen: {kernabstand(rosa):.3f} / "
      f"{kernabstand(teil):.3f} / {kernabstand(geheilt):.3f}")
pruef(abs(kernabstand(teil) - kernabstand(rosa) / 2) < 0.02,
      "halbe Staerke halbiert den Abstand nicht")
# Der Melder schlaegt bei halber Staerke noch an - das ist richtig so,
# 0.14 Rest liegen ueber seiner Schwelle von 0.12.
pruef(stich(teil)[0] > 0, "bei halber Korrektur bleibt ein Rest sichtbar")
pruef(stich(geheilt)[0] == 0, "bei voller Korrektur darf nichts bleiben")
for probe in (np.zeros((9, 9, 3), np.float32), np.ones((9, 9, 3), np.float32)):
    pruef(np.all(np.isfinite(bleichen(probe, 1.0))), "Grenzbild stuerzt ab")
pruef(float(bleichen(rosa, 1.0).max()) <= 1.0 + 1e-6, "Wertebereich verlassen")

print("=== 3. Vorschau beruecksichtigt die Lichter ===")
ohne = vr(rosa, 5500, 1.0, {})
mit = vr(rosa, 5500, 1.0, {'_hl_staerke': 1.0})
pruef(not np.array_equal(ohne, mit), "die Vorschau zeigt den Unterschied nicht")
pruef(stich(mit, linear=False)[0] < stich(ohne, linear=False)[0],
      "die Vorschau zeigt den Stich weiterhin")
pruef(np.array_equal(vr(rosa, 5500, 1.0, {'_hl_staerke': 0.0}), ohne),
      "Staerke 0 darf nichts aendern")

print("=== 4. Profilschluessel beider Engines ===")
art = {'Version': {'Version': '350'},
       'Exposure': {'Enabled': 'true', 'Compensation': '0.4',
                    'HLRecovery': 'Off', 'Black': '0'}}
rt = {'Version': {'Version': '346'},
      'Exposure': {'Compensation': '0.2', 'Brightness': '0'},
      'HLRecovery': {'Enabled': 'false', 'Method': 'Blend', 'Hlth': '1'}}

pe.set_engine('art')
pruef(pe.hl_verfuegbar(art), "ART-Profil mit HLRecovery wird nicht erkannt")
pruef(not pe.hl_verfuegbar({'Exposure': {'Compensation': '0'}}),
      "ohne den Schluessel darf es nicht angeboten werden")
pruef(pe.hl_lesen(art) == "Off", f"ART gelesen: {pe.hl_lesen(art)}")
p = {k: dict(v) for k, v in art.items()}
g = pe.hl_schreiben(p, "Color")
pruef(p['Exposure']['HLRecovery'] == "Color", f"ART geschrieben: {p['Exposure']}")
pruef(g == [('Exposure', 'HLRecovery', 'Color')], f"Rueckmeldung: {g}")
pruef(pe.hl_lesen(p) == "Color", "zurueckgelesen stimmt nicht")
pruef(p['Exposure']['Compensation'] == '0.4',
      "die Belichtung des Deflickers wurde angefasst")
pe.hl_schreiben(p, "Off")
pruef(p['Exposure']['HLRecovery'] == "Off", "Ausschalten geht nicht")
pruef(pe.hl_empfohlen('art') == "Color", "ART-Empfehlung falsch")

pe.set_engine('rt')
pruef(pe.hl_verfuegbar(rt), "RT-Profil mit [HLRecovery] wird nicht erkannt")
pruef(not pe.hl_verfuegbar({'Exposure': {}}), "RT ohne die Sektion")
pruef(pe.hl_lesen(rt) == "Off", f"Enabled=false muss Off ergeben: {pe.hl_lesen(rt)}")
q = {k: dict(v) for k, v in rt.items()}
g = pe.hl_schreiben(q, "Coloropp")
pruef(q['HLRecovery']['Enabled'] == "true", "RT: Enabled nicht gesetzt")
pruef(q['HLRecovery']['Method'] == "Coloropp", f"RT: Method {q['HLRecovery']}")
pruef(len(g) == 2, f"RT schreibt zwei Schluessel, gemeldet: {g}")
pruef(pe.hl_lesen(q) == "Coloropp", "RT zurueckgelesen")
pruef(q['HLRecovery']['Hlth'] == '1', "RT: fremder Schluessel veraendert")
pe.hl_schreiben(q, "Off")
pruef(q['HLRecovery']['Enabled'] == "false", "RT: Ausschalten setzt Enabled nicht")
pruef(pe.hl_lesen(q) == "Off", "RT: ausgeschaltet nicht erkannt")
pruef(pe.hl_empfohlen('rt') == "Coloropp", "RT-Empfehlung falsch")
pruef(pe.hl_empfohlen('art') != pe.hl_empfohlen('rt'),
      "die Engines muessen sich hier unterscheiden")

pe.set_engine('dt')
pruef(pe.hl_optionen() == [], "Darktable darf nichts anbieten")
pruef(not pe.hl_verfuegbar(art), "Darktable darf ART-Schluessel nicht annehmen")

# Die Verfahren muessen zu dem passen, was die Engines kennen
pruef([o[0] for o in pe.hl_optionen('art')] == ["Off", "Blend", "Color", "Balanced"],
      f"ART-Verfahren: {[o[0] for o in pe.hl_optionen('art')]}")
pruef([o[0] for o in pe.hl_optionen('rt')] == ["Off", "Blend", "Color", "Coloropp"],
      f"RT-Verfahren: {[o[0] for o in pe.hl_optionen('rt')]}")
for e in ('art', 'rt'):
    for schluessel, name, erklaerung in pe.hl_optionen(e):
        pruef(name and erklaerung, f"{e}/{schluessel}: Beschreibung fehlt")
    pruef(pe.hl_empfohlen(e) in [o[0] for o in pe.hl_optionen(e)],
          f"{e}: die Empfehlung steht nicht in der Liste")

print("=== 5. Rundlauf ueber eine Datei ===")
SCRATCH = os.environ.get("PURELAPSE_ARBEIT", os.path.join(__import__("tempfile").gettempdir(), "purelapse_pruefung"))
ordner = os.path.join(SCRATCH, "hltest")
shutil.rmtree(ordner, ignore_errors=True)
os.makedirs(ordner)
pe.set_engine('rt')
pfad = os.path.join(ordner, "IMG.NEF.pp3")
voll = {k: dict(v) for k, v in rt.items()}
pe.hl_schreiben(voll, "Coloropp")
pe.quick_apply(voll, {'saturation': 15})
pe.write_arp_dict(pfad, voll)
zurueck = pe.read_arp_dict(pfad)
pruef(pe.hl_lesen(zurueck) == "Coloropp", "ueberlebt das Schreiben nicht")
pruef(zurueck['Exposure']['Saturation'] == '15', "Saettigung daneben verloren")
pruef(list(zurueck.keys())[0] == 'Version', "[Version] verrutscht")
# Pass 1 darf es nicht wegwerfen
pe.write_arp_file(os.path.join(ordner, "IMG.NEF"), -0.25, template=rt)
danach = pe.read_arp_dict(pfad)
pruef(pe.hl_lesen(danach) == "Coloropp", "Pass 1 hat die Rekonstruktion geloescht")
pruef(danach['Exposure']['Compensation'] == '-0.250', "Pass 1 hat nicht gesetzt")
# Interpolation traegt es weiter
nachbar = pe.interpolate_arp_dicts(danach, rt, 0.5)
pruef(nachbar.get('HLRecovery', {}).get('Enabled') == 'true',
      f"Nachbarbild bekommt die Rekonstruktion nicht: {nachbar.get('HLRecovery')}")

print("=== 6. Automatik ===")
auto = ns["auto_optimieren"]
w_r, g_r = auto(sonnenbild(rosa=True), iso=100)
w_w, g_w = auto(sonnenbild(rosa=False), iso=100)
pruef(w_r.get('_hl') is True, f"die Automatik erkennt den rosa Ball nicht: {w_r}")
pruef(any("Lichter rekonstruieren" in x for x in g_r),
      "die Begruendung nennt es nicht")
pruef(not w_w.get('_hl'), "bei weissen Lichtern darf sie es nicht vorschlagen")

print("=== 7. Oberflaeche ===")
dlg = schnitt(src, "class QuickLookDialog", "class GalleryWorker")
pruef("self.cmb_hl" in dlg and "self.chk_hl" in dlg, "kein Bedienelement")
pruef("hl_verfuegbar(profil)" in dlg, "es wird nicht geprueft, ob das Profil es kennt")
pruef("hl_empfohlen()" in dlg, "die Empfehlung wird nicht vorausgewaehlt")
pruef("def hl_wert" in dlg, "der Dialog gibt den Wert nicht heraus")
pruef("def _hl_pruefen" in dlg, "keine Warnung im Dialog")
hp = schnitt(src, "    def _hl_pruefen", "class GalleryWorker")
pruef("lichter_farbstich(self._basis)" in hp, "es wird nicht gemessen")
pruef("verfärbt" in hp or "verf\\u00e4rbt" in hp, "die Warnung nennt das Problem nicht")
pruef("_hl_staerke" in dlg, "die Vorschau bekommt die Rekonstruktion nicht mit")
import purelapse_engines as _pe
_pe.set_engine('rt')
_p = {'Version': {}, 'General': {}, 'Exposure': {'HistogramMatching': 'false'}, 'HLRecovery': {'Enabled': 'false'}}
_n, _g, _ = _pe.schnell_profil(_p, {'_hl_staerke': 1.0}, "Coloropp")
pruef(_pe.hl_lesen(_n) == "Coloropp" and ('HLRecovery', 'Method', 'Coloropp') in _g, "es wird nichts ins Profil geschrieben")
pruef(not any('_hl' in k for sek in _n.values() for k in sek),
      "die internen Vorschauwerte wuerden ins Profil wandern")
pruef("self._hl_ursprung" in dlg, "Zuruecksetzen laesst die Lichter stehen")
pruef("lbl_farbstich" in src, "kein Infofeld im Hauptfenster")
pf = schnitt(src, "    def _pruefe_farbstich", "    def _on_clip_report")
pruef("v > 0.15" in pf, "keine Schwelle fuer die Sequenzmeldung")
pruef("Keyframe einstellen" in pf, "die Meldung sagt nicht, was zu tun ist")
pruef("hl_bunt" in src, "die Galerie misst den Farbstich nicht mit")

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
