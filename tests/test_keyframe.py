#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Pruefungen fuer Zeitanzeige, Lichterwarnung und die Schnelleinstellungen
der Keyframes. Laeuft ohne Qt.
"""
import io, os, re, ast, sys, time, shutil, collections

BASIS = os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = io.open(f"{BASIS}/purelapse_main.py", encoding="utf-8").read()
eng_src = io.open(f"{BASIS}/purelapse_engines.py", encoding="utf-8").read()
SCRATCH = os.environ.get("PURELAPSE_ARBEIT", os.path.join(__import__("tempfile").gettempdir(), "purelapse_pruefung"))
sys.path.insert(0, BASIS)

ok_n = fail_n = 0
def pruef(b, text):
    global ok_n, fail_n
    if b: ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")

def schnitt(txt, von, bis):
    return txt[txt.index(von):txt.index(bis)]

# ============================================================== 1. Zeitanzeige
print("=== 1. Zeitanzeige ===")
ns = {"time": time}
exec(schnitt(src, "def dauer_text(", "# =========================================================================="
             "\n#  PARALLELE ENTWICKLUNG"), ns)
dt = ns["dauer_text"]
pruef(dt(0) == "0:00", f"0 -> {dt(0)}")
pruef(dt(5) == "0:05", f"5 -> {dt(5)}")
pruef(dt(59) == "0:59", f"59 -> {dt(59)}")
pruef(dt(60) == "1:00", f"60 -> {dt(60)}")
pruef(dt(599) == "9:59", f"599 -> {dt(599)}")
pruef(dt(3599) == "59:59", f"3599 -> {dt(3599)}")
pruef(dt(3600) == "1:00:00", f"3600 -> {dt(3600)}")
pruef(dt(7325) == "2:02:05", f"7325 -> {dt(7325)}")
pruef(dt(-5) == "0:00", "negative Zeit")
pruef(dt(None) == "--:--", "None")
pruef(dt("quatsch") == "--:--", "Unsinn-Eingabe")
pruef(dt(12.6) == "0:13", f"Rundung: {dt(12.6)}")

ft = ns["fortschritt_text"]
t0 = time.time() - 60.0           # eine Minute laeuft schon
txt = ft("Analysiere RAWs", 30, 120, t0)
pruef("30/120" in txt, f"Zaehler fehlt: {txt}")
pruef("1:00 von ca. 4:00" in txt, f"Gesamtdauer falsch: {txt}")
pruef("Rest 3:00" in txt, f"Restzeit falsch: {txt}")
# Alle drei Zeiten muessen vorkommen - das war der Punkt der Aenderung
pruef(txt.count(":") >= 3, f"nicht alle drei Zeiten: {txt}")
txt0 = ft("Analysiere RAWs", 0, 120, t0)
pruef("Gesamtdauer noch unbekannt" in txt0, f"vor dem ersten Bild: {txt0}")
pruef("ca." not in txt0, "vor dem ersten Bild darf nicht geschaetzt werden")
txt_e = ft("Lese", 7, 100, time.time() - 10, zusatz="IMG_0007.NEF")
pruef("IMG_0007.NEF" in txt_e, f"Zusatz fehlt: {txt_e}")
pruef(ft("Schritt", 5, 0, time.time()).startswith("Schritt |"),
      "ohne Gesamtzahl kein Zaehler")
# Fertig = Rest 0
pruef("Rest 0:00" in ft("X", 10, 10, time.time() - 30), "am Ende Rest 0:00")
pruef(src.count("ETA:") == 0, "alte ETA-Anzeige noch vorhanden")
en = ft("Reading images", 30, 120, time.time() - 60, lang='en')
pruef("of approx." in en and "left" in en, f"englische Fassung: {en}")
pruef("von ca." not in en, f"deutsche Reste in der englischen Fassung: {en}")
pruef("not yet known" in ft("X", 0, 10, time.time(), lang='en'),
      "englische Fassung ohne Schaetzgrundlage")
pruef(src.count("em, es = divmod") == 0, "alte Zeitrechnung noch vorhanden")
pruef(src.count("fortschritt_text(") >= 2, "fortschritt_text wird kaum benutzt")
pruef(src.count("self._fortschritt(") >= 8,
      f"_fortschritt an zu wenigen Stellen ({src.count('self._fortschritt(')})")
pruef("def _schritt_fertig" in src, "_schritt_fertig fehlt")
pruef(src.count("self._schritt_fertig(") >= 4,
      f"_schritt_fertig zu selten benutzt ({src.count('self._schritt_fertig(')})")

# ============================================================== 2. Lichter
print("=== 2. Ausgefressene Lichter ===")
ns2 = {}
exec(schnitt(src, "CLIP_SCHWELLE_VORSCHAU", "# =========================================================================="
             "\n#  ZEITANZEIGE"), ns2)
la = ns2["lichter_auswerten"]
anz, ges, schl = la([0.0, 0.001, 0.02, 0.5, 0.004], 0.005)
pruef((anz, ges) == (2, 5), f"Zaehlung falsch: {anz}/{ges}")
pruef(schl[0] == (3, 0.5), f"nicht nach Staerke sortiert: {schl}")
pruef(schl[1] == (2, 0.02), f"zweiter Platz falsch: {schl}")
pruef(la([], 0.005) == (0, 0, []), "leere Liste")
pruef(la([0.0] * 100, 0.005)[0] == 0, "nichts geklippt -> keine Treffer")
pruef(la([1.0] * 100, 0.005)[0] == 100, "alles geklippt")
pruef(len(la([0.9] * 80, 0.005)[2]) == 25, "Liste nicht auf 25 begrenzt")
anz, ges, _ = la([0.01, None, "x", 0.02], 0.005)
pruef((anz, ges) == (2, 2), f"Unsinn-Werte nicht uebersprungen: {anz}/{ges}")
# Genau an der Schwelle zaehlt nicht als Treffer
pruef(la([0.005], 0.005)[0] == 0, "Wert genau auf der Schwelle")
pruef(la([0.0051], 0.005)[0] == 1, "Wert knapp ueber der Schwelle")
pruef(ns2["CLIP_SCHWELLE_RAW"] < ns2["CLIP_SCHWELLE_VORSCHAU"],
      "die RAW-Schwelle muss strenger sein als die der Vorschau")
pruef("def _zeige_lichter" in src and "def _pruefe_lichter" in src,
      "Anzeigefunktionen fehlen")
pruef("clip_report = QtCore.pyqtSignal(int, int, list)" in src,
      "Signal clip_report fehlt")
pruef(src.count("self.worker.clip_report.connect(self._on_clip_report)") == 1,
      "Signal nicht verbunden")
pruef("self.clip_report.emit(" in src, "Signal wird nie gesendet")
pass1 = schnitt(src, "def _run_raw_pass1", "def _prepare_keyframe_profiles")
pruef("CLIP_SCHWELLE_RAW" in pass1, "Pass 1 nutzt die strenge Schwelle nicht")
pruef("lbl_clip" in src and src.count("self.lbl_clip") >= 6,
      "Infofeld zu selten benutzt")
pruef("def _style_clip" in src, "Einfaerbung fehlt")
# Die Meldung muss sagen, woher sie kommt - Vorschau ist keine Diagnose
zeige = schnitt(src, "def _zeige_lichter", "def _style_clip")
pruef("vorlaeufig" in zeige, "vorlaeufige Messung wird nicht gekennzeichnet")
pruef("Sensordaten" in zeige, "genaue Messung wird nicht benannt")
pruef("quelle == 'raw'" in zeige, "Quelle wird nicht unterschieden")

# ============================================================== 3. Profilschluessel
print("=== 3. Schnelleinstellungen: Schluessel ===")
import purelapse_engines as pe
pruef(pe.ENGINES['art']['wb_custom'] == "CustomTemp",
      "ART erwartet CustomTemp (src/engine/procparams.cc)")
pruef(pe.ENGINES['rt']['wb_custom'] == "Custom",
      "RawTherapee erwartet Custom (rtengine/procparams.cc)")
pruef(pe.ENGINES['art']['wb_custom'] != pe.ENGINES['rt']['wb_custom'],
      "die beiden Engines muessen sich hier unterscheiden")
pruef("'CustomTemp' if force_custom" not in eng_src,
      "fest verdrahtetes CustomTemp noch in der Interpolation")
pruef("eng('wb_custom')" in eng_src, "Interpolation fragt die Engine nicht")

pruef(len(pe.QUICK_CONTROLS) == 11, "elf Regler erwartet")
ids = [c['id'] for c in pe.QUICK_CONTROLS]
pruef(len(set(ids)) == 11, "Regler-Kennungen nicht eindeutig")
for gewuenscht in ('wb_temp', 'brightness', 'saturation', 'sharpen',
                   'denoise_l', 'contrast'):
    pruef(gewuenscht in ids, f"Regler {gewuenscht} fehlt")
pruef('exposure' not in ids and 'compensation' not in ids,
      "die Belichtungskorrektur gehoert dem Deflicker und darf nicht dabei sein")

for e in ('art', 'rt'):
    pe.set_engine(e)
    defs = pe.quick_defs()
    pruef(len(defs) == 11, f"{e}: nicht alle Regler zugeordnet")
    for d in defs:
        pruef(d['min'] < d['max'], f"{e}/{d['id']}: Bereich verdreht")
        pruef(d['min'] <= d['neutral'] <= d['max'],
              f"{e}/{d['id']}: Neutralwert ausserhalb des Bereichs")
        pruef(d['ui_min'] >= d['min'] - 1e-9 and d['ui_max'] <= d['max'] + 1e-9,
              f"{e}/{d['id']}: Reglerbereich sprengt die Engine-Grenzen")
        pruef(d['sec'] and d['key'], f"{e}/{d['id']}: Sektion/Schluessel leer")
# Die bekannten Unterschiede zwischen den Engines
pe.set_engine('art')
a = {d['id']: (d['sec'], d['key']) for d in pe.quick_defs()}
pe.set_engine('rt')
r = {d['id']: (d['sec'], d['key']) for d in pe.quick_defs()}
pruef(a['brightness'] == ('Luminance Curve', 'Brightness'), f"ART Helligkeit: {a['brightness']}")
pruef(r['brightness'] == ('Exposure', 'Brightness'), f"RT Helligkeit: {r['brightness']}")
pruef(a['saturation'] == ('Saturation', 'Saturation'), f"ART Saettigung: {a['saturation']}")
pruef(r['saturation'] == ('Exposure', 'Saturation'), f"RT Saettigung: {r['saturation']}")
pruef(a['denoise_l'] == ('Denoise', 'Luminance'), f"ART Entrauschen: {a['denoise_l']}")
pruef(r['denoise_l'] == ('Directional Pyramid Denoising', 'Luma'),
      f"RT Entrauschen: {r['denoise_l']}")
pruef(a['contrast'] == ('Luminance Curve', 'Contrast'), f"ART Kontrast: {a['contrast']}")
pruef(r['contrast'] == ('Exposure', 'Contrast'), f"RT Kontrast: {r['contrast']}")
pe.set_engine('dt')
pruef(sorted(d['id'] for d in pe.quick_defs()) == ['brightness', 'contrast', 'highlights',
                                                    'saturation', 'shadows', 'sharpen', 'vibrance'],
      "Darktable: alle Regler ausser Weissabgleich und Entrauschen erwartet")

# ============================================================== 4. Lesen/Schreiben
print("=== 4. Schnelleinstellungen: Lesen und Schreiben ===")
pe.set_engine('art')
# Profil wie ART es schreibt
art_profil = {
    'Version': {'AppVersion': '1.25', 'Version': '350'},
    'General': {'Rank': '0'},
    'Exposure': {'Enabled': 'true', 'Compensation': '0.450', 'Black': '0'},
    'White Balance': {'Enabled': 'true', 'Setting': 'Camera',
                      'Temperature': '5200', 'Green': '1.000',
                      'Multipliers': '1.0;1.0;1.0'},
    'Luminance Curve': {'Enabled': 'false', 'Brightness': '0', 'Contrast': '0',
                        'Chromaticity': '0'},
    'Saturation': {'Enabled': 'false', 'Saturation': '0', 'Vibrance': '0'},
    'Sharpening': {'Enabled': 'false', 'Amount': '200', 'Radius': '0.5',
                   'Threshold': '20;80;2000;1200'},
    'Denoise': {'Enabled': 'false', 'Luminance': '0', 'Chrominance': '15'},
    'ToneEqualizer': {'Enabled': 'false', 'Band0': '0', 'Band1': '0', 'Band2': '0',
                      'Band3': '0', 'Band4': '0', 'Regularization': '4', 'Pivot': '0'},
    'Channel Mixer': {'Green': '0;1000;0'},
}
vorh, fehlt = pe.quick_available(art_profil)
pruef(len(vorh) == 11 and not fehlt, f"vollstaendiges ART-Profil: {len(vorh)}/{len(fehlt)}")
w = pe.quick_read(art_profil)
pruef(w['wb_temp'] == 5200.0, f"Temperatur gelesen: {w['wb_temp']}")
pruef(w['denoise_c'] == 15.0, f"Chrominanz gelesen: {w['denoise_c']}")
pruef(w['sharpen'] == 200.0, f"Schaerfe gelesen: {w['sharpen']}")

# Fehlende Sektion -> Regler gesperrt, nicht stillschweigend geschrieben
duenn = {k: v for k, v in art_profil.items() if k not in ('Denoise', 'Saturation')}
vorh2, fehlt2 = pe.quick_available(duenn)
pruef(len(fehlt2) == 4, f"vier Regler muessten fehlen, nicht {len(fehlt2)}")
pruef({d['id'] for d in fehlt2} == {'saturation', 'vibrance', 'denoise_l', 'denoise_c'},
      f"falsche Regler gesperrt: {[d['id'] for d in fehlt2]}")

# Schreiben
p = {k: dict(v) for k, v in art_profil.items()}
geschrieben = pe.quick_apply(p, {'wb_temp': 7400, 'saturation': 22,
                                 'denoise_l': 35, 'brightness': -8})
pruef(p['White Balance']['Temperature'] == '7400', f"Temperatur: {p['White Balance']['Temperature']}")
pruef(p['White Balance']['Setting'] == 'CustomTemp',
      f"ART-Weissabgleich: {p['White Balance']['Setting']}")
pruef(p['Saturation']['Saturation'] == '22', "Saettigung nicht geschrieben")
pruef(p['Saturation']['Enabled'] == 'true', "Sektion nicht eingeschaltet")
pruef(p['Denoise']['Luminance'] == '35', "Entrauschen nicht geschrieben")
pruef(p['Denoise']['Enabled'] == 'true', "Denoise nicht eingeschaltet")
pruef(p['Luminance Curve']['Brightness'] == '-8', "Helligkeit nicht geschrieben")
# Nicht uebergebene Regler bleiben unberuehrt
pruef(p['Sharpening']['Amount'] == '200', "Schaerfe wurde angefasst, ohne gefragt zu sein")
pruef(p['Sharpening']['Enabled'] == 'false', "Schaerfe-Sektion eingeschaltet ohne Grund")
pruef(p['Denoise']['Chrominance'] == '15', "Chrominanz veraendert")
# Die Belichtung des Deflickers bleibt stehen
pruef(p['Exposure']['Compensation'] == '0.450',
      "die Deflicker-Belichtung wurde ueberschrieben")
# Ganzzahlfelder bleiben ganzzahlig - daran war ART schon einmal gescheitert
pruef(p['Channel Mixer']['Green'] == '0;1000;0', "Ganzzahlliste veraendert")
for sec, key, wert in geschrieben:
    pruef('.' not in wert or key in ('Green',),
          f"[{sec}] {key} = {wert} hat unerwartet eine Kommastelle")
pruef(len(geschrieben) == 5, f"5 Eintraege erwartet (4 Regler + Setting): {len(geschrieben)}")

# Klemmen auf die Engine-Grenzen
p2 = {k: dict(v) for k, v in art_profil.items()}
pe.quick_apply(p2, {'wb_temp': 999999, 'saturation': -5000})
pruef(p2['White Balance']['Temperature'] == '60000', f"obere Grenze: {p2['White Balance']['Temperature']}")
pruef(p2['Saturation']['Saturation'] == '-100', f"untere Grenze: {p2['Saturation']['Saturation']}")
p3 = {k: dict(v) for k, v in art_profil.items()}
pe.quick_apply(p3, {'wb_green': 1.2345678})
pruef(p3['White Balance']['Green'] == '1.235',
      f"drei Dezimalstellen, kaufmaennisch gerundet: {p3['White Balance']['Green']}")
p3b = {k: dict(v) for k, v in art_profil.items()}
pe.quick_apply(p3b, {'wb_green': 1.2}) 
pruef(p3b['White Balance']['Green'] == '1.200', "immer drei Stellen")
p4 = {k: dict(v) for k, v in art_profil.items()}
pruef(pe.quick_apply(p4, {}) == [], "leere Uebergabe darf nichts schreiben")
pruef(p4 == art_profil, "leere Uebergabe hat das Profil veraendert")
p5 = {k: dict(v) for k, v in art_profil.items()}
pe.quick_apply(p5, {'wb_temp': 'quatsch', 'saturation': 10})
pruef(p5['White Balance']['Temperature'] == '5200', "Unsinn-Wert wurde geschrieben")
pruef(p5['Saturation']['Saturation'] == '10', "gueltiger Wert daneben verloren")

# RawTherapee: Setting=Custom, und kein erfundenes Enabled in [Exposure]
pe.set_engine('rt')
rt_profil = {
    'Version': {'AppVersion': '5.9', 'Version': '346'},
    'Exposure': {'Auto': 'false', 'Compensation': '0.2', 'Brightness': '0',
                 'Contrast': '5', 'Saturation': '0', 'Black': '0'},
    'White Balance': {'Setting': 'Camera', 'Temperature': '6861', 'Green': '0.92'},
    'Sharpening': {'Enabled': 'false', 'Method': 'usm', 'Amount': '125'},
    'Directional Pyramid Denoising': {'Enabled': 'false', 'Luma': '10',
                                      'Chroma': '10', 'Gamma': '2'},
}
q = {k: dict(v) for k, v in rt_profil.items()}
pe.quick_apply(q, {'wb_temp': 8000, 'brightness': 12, 'denoise_l': 25})
pruef(q['White Balance']['Setting'] == 'Custom',
      f"RawTherapee braucht Custom, nicht {q['White Balance']['Setting']}")
pruef(q['Exposure']['Brightness'] == '12', "RT Helligkeit nicht geschrieben")
pruef('Enabled' not in q['Exposure'],
      "in RawTherapees [Exposure] darf kein Enabled erfunden werden")
pruef(q['Directional Pyramid Denoising']['Luma'] == '25', "RT Entrauschen")
pruef(q['Directional Pyramid Denoising']['Enabled'] == 'true',
      "RT Denoise-Sektion nicht eingeschaltet")
pruef(q['Exposure']['Compensation'] == '0.2', "RT Belichtung ueberschrieben")

# ============================================================== 5. Datei-Rundlauf
print("=== 5. Rundlauf ueber eine echte Datei ===")
ordner = os.path.join(SCRATCH, "quicktest")
shutil.rmtree(ordner, ignore_errors=True)
os.makedirs(ordner)
pe.set_engine('art')
pfad = os.path.join(ordner, "IMG_0001.NEF.arp")
pe.write_arp_dict(pfad, art_profil)
gelesen = pe.read_arp_dict(pfad)
pruef(pe.profile_is_complete(gelesen), "geschriebenes Profil gilt als unvollstaendig")
pruef(list(gelesen.keys())[0] == 'Version', "[Version] steht nicht an erster Stelle")
pe.quick_apply(gelesen, {'wb_temp': 7400, 'saturation': 22})
pe.write_arp_dict(pfad, gelesen)
nach = pe.read_arp_dict(pfad)
pruef(nach['White Balance']['Temperature'] == '7400', "Temperatur ueberlebt die Datei nicht")
pruef(nach['White Balance']['Setting'] == 'CustomTemp', "Setting ueberlebt nicht")
pruef(nach['Saturation']['Saturation'] == '22', "Saettigung ueberlebt nicht")
pruef(list(nach.keys())[0] == 'Version', "[Version] nach dem Schreiben verrutscht")
pruef(nach['Channel Mixer']['Green'] == '0;1000;0', "Ganzzahlliste beschaedigt")
# Pass 1 darf die Schnelleinstellungen nicht wegwerfen
pe.write_arp_file(os.path.join(ordner, "IMG_0001.NEF"), -0.317, template=art_profil)
danach = pe.read_arp_dict(pfad)
pruef(danach['White Balance']['Temperature'] == '7400',
      "Pass 1 hat die Schnelleinstellung ueberschrieben")
pruef(danach['Saturation']['Saturation'] == '22',
      "Pass 1 hat die Saettigung ueberschrieben")
pruef(danach['Exposure']['Compensation'] == '-0.317',
      f"Pass 1 hat die Belichtung nicht gesetzt: {danach['Exposure'].get('Compensation')}")
# Interpolation auf ein Nachbarbild traegt die Werte weiter
neutral = {k: dict(v) for k, v in art_profil.items()}
mitte = pe.interpolate_arp_dicts(danach, neutral, 0.5)
pruef(abs(float(mitte['White Balance']['Temperature']) - (7400 + 5200) / 2) < 1.0,
      f"Temperatur nicht interpoliert: {mitte['White Balance']['Temperature']}")
pruef(mitte['White Balance']['Setting'] == 'CustomTemp',
      f"interpoliertes Setting falsch: {mitte['White Balance']['Setting']}")
pruef(abs(float(mitte['Saturation']['Saturation']) - 11.0) < 0.6,
      f"Saettigung nicht interpoliert: {mitte['Saturation']['Saturation']}")
pruef('Compensation' not in mitte.get('Exposure', {}),
      "die Interpolation darf die Belichtung nicht anfassen")
pruef(mitte['Channel Mixer']['Green'] == '0;1000;0',
      f"Ganzzahlliste durch Interpolation beschaedigt: {mitte['Channel Mixer']['Green']}")
# Dasselbe fuer RawTherapee: Setting muss Custom bleiben
pe.set_engine('rt')
rt_a = {k: dict(v) for k, v in rt_profil.items()}
pe.quick_apply(rt_a, {'wb_temp': 8000})
rt_mitte = pe.interpolate_arp_dicts(rt_a, rt_profil, 0.5)
pruef(rt_mitte['White Balance']['Setting'] == 'Custom',
      f"RT-Interpolation schreibt {rt_mitte['White Balance']['Setting']}")

# ============================================================== 6. Oberflaeche
print("=== 6. Oberflaeche ===")
pruef("class QuickLookDialog" in src, "Dialog fehlt")
dlg = schnitt(src, "class QuickLookDialog", "class GalleryWorker")
pruef("quick_available(" in dlg, "Dialog fragt nicht, was das Profil kennt")
pruef("quick_read(" in dlg, "Dialog liest die vorhandenen Werte nicht")
pruef("chk.setChecked(" in dlg, "kein Haekchen je Regler")
pruef("Nicht verfuegbar" in dlg, "gesperrte Regler werden nicht erklaert")
pruef("def werte" in dlg, "Dialog gibt keine Werte zurueck")
pruef("if chk.isChecked()" in dlg, "Dialog gibt auch nicht angekreuzte Werte zurueck")
oef = schnitt(src, "def _open_quick_dialog", "def _on_tile_selected")
pruef("schnell_profil(" in oef and "write_arp_dict(pfad, profil)" in oef, "Werte werden nicht ins Profil geschrieben")
pruef("write_arp_dict(" in oef, "Profil wird nicht gespeichert")
pruef("read_arp_dict(pfad)" in oef, "es wird nicht nachgelesen")
pruef("fehlgeschlagen" in oef, "ein stiller Fehlschlag wuerde nicht auffallen")
pruef("profile_is_complete" in oef, "duennes Profil wird nicht abgefangen")
pruef("find_arp_template" in oef, "ohne Basisprofil gibt es keinen Ausweg")
flt = schnitt(src, "def _on_filter_keyframes", "def _keyframe_zeilen")
pruef("setHidden(" in flt, "Filter entfernt Zeilen statt sie auszublenden")
pruef(".takeItem(" not in flt and ".removeItemWidget(" not in flt,
      "Filter darf keine Zeilen entfernen - das verschiebt die Indizes")
pruef("_relayout_gallery()" in flt, "Kacheln werden nach dem Filtern nicht neu gelegt")
pruef("'chk': chk_kf" in src, "Kachel merkt sich das Keyframe-Kaestchen nicht")
pruef("def _update_kf_buttons" in src, "Knopfzustand wird nicht gepflegt")
pruef("getattr(self, '_busy', False)" in src, "_busy ungesichert gelesen")
pruef('"btn_kf_filter", "btn_kf_edit", "lbl_clip"' in src,
      "neue Bedienelemente nicht in der Waisen-Wache")
ub = schnitt(src, "def _update_kf_buttons", "def _open_quick_dialog")
pruef("eng('kind') in ('ini', 'darktable')" in ub, "Knopf nicht fuer Darktable freigegeben")
# Der Darktable-Fall muss sich von selbst erklaeren - genau daran ist der
# Knopf zuletzt stillschweigend haengengeblieben.
pruef("Darktable" in ub, "der Darktable-Fall wird dem Nutzer nicht erklaert")
pruef("Noch kein Keyframe markiert" in ub,
      "der haeufigste Fall - kein Keyframe - wird nicht erklaert")

print("=== 7. Doppelte Definitionen und Schluessel ===")
for datei, txt in (("purelapse_main.py", src), ("purelapse_engines.py", eng_src)):
    tree = ast.parse(txt)
    for kn in ast.walk(tree):
        if isinstance(kn, (ast.ClassDef, ast.Module)):
            namen = [k.name for k in kn.body
                     if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))]
            d = [n for n, c in collections.Counter(namen).items() if c > 1]
            pruef(not d, f"{datei}/{getattr(kn, 'name', 'Modul')}: doppelt -> {d}")
        if isinstance(kn, ast.Dict):
            sch = [k.value for k in kn.keys
                   if isinstance(k, ast.Constant) and isinstance(k.value, str)]
            d = [n for n, c in collections.Counter(sch).items() if c > 1]
            pruef(not d, f"{datei} Zeile {kn.lineno}: doppelte Schluessel -> {d[:5]}")

print(f"\n{'='*52}\n{ok_n} Pruefungen bestanden, {fail_n} fehlgeschlagen")
sys.exit(1 if fail_n else 0)
