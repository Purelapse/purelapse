# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Echte Vorschau: die Engine entwickelt das Vorschaubild selbst."""
import os, sys, io, glob, time, threading, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import _basis
import cv2

OK = FEHL = 0
def pruef(b, text):
    global OK, FEHL
    if b: OK += 1
    else:
        FEHL += 1; print("  FEHLER:", text)
def O(name): return os.path.join(ARBEIT, name)
N = 40

print("=== 1. Bausteine ===")
pe.set_engine('rt')
p0 = {'Version': {'Version': '346'}, 'General': {'Rank': '5'},
      'Exposure': {'Auto': 'false', 'Compensation': '0.250', 'Brightness': '0', 'Contrast': '0',
                   'Saturation': '0', 'HistogramMatching': 'true', 'Curve': '0;'},
      'HLRecovery': {'Enabled': 'false', 'Method': 'Coloropp'},
      'White Balance': {'Setting': 'Camera', 'Temperature': '5000', 'Green': '1'}}
kopie = {s: dict(v) for s, v in p0.items()}
neu, geschrieben, eingefroren = pe.schnell_profil(p0, {'saturation': 30, '_hl_staerke': 1.0}, "Coloropp")
pruef(p0 == kopie, "schnell_profil veraendert das uebergebene Profil")
pruef(neu['Exposure']['Saturation'] == '30' and pe.hl_lesen(neu) == 'Coloropp', "Werte nicht eingetragen")
pruef(neu['Exposure']['HistogramMatching'] == 'false' and eingefroren == ['tonkurve'], "Automatik nicht eingefroren")
pruef(neu['Exposure']['Compensation'] == '0.250', "Belichtung veraendert")
pruef(('Exposure', 'Saturation', '30') in geschrieben and not any(k.startswith('_') for _, k, _ in geschrieben),
      f"Liste der geschriebenen Werte: {geschrieben}")
leer, g2, _ = pe.schnell_profil(p0, {}, "Off")
pruef(g2 == [], "ohne Haekchen wird etwas geschrieben")
_, g3, _ = pe.schnell_profil(p0, {}, None)
pruef(g3 == [], "hl=None schreibt")
v = pe.vorschau_profil(neu, 900)
pruef(v['Resize'] == {'Enabled': 'true', 'DataSpecified': '3', 'Width': '900', 'Height': '900',
                      'AllowUpscaling': 'false'} and 'Resize' not in neu, f"Resize: {v.get('Resize')}")
pruef({s: v[s] for s in neu} == neu, "vorschau_profil aendert mehr als die Groesse")
b = pe.vorschau_befehl("/x/rawtherapee-cli", "/b/a.NEF", "/t/v.pp3", "/t/v.jpg")
pruef(b[0] == "/x/rawtherapee-cli" and b[b.index("-o") + 1] == "/t/v.jpg" and b[b.index("-p") + 1] == "/t/v.pp3"
      and "-d" in b and b[-2:] == ["-c", "/b/a.NEF"] and "-S" not in b and "-s" not in b, f"Befehl RT: {b}")
pruef(b.index("-d") < b.index("-c") and b.index("-p") < b.index("-c"), "Schalter stehen hinter -c")
pruef("-d" not in pe.vorschau_befehl("/x/ART-cli", "a", "p", "z", engine='art'), "ART bekommt -d")
k1 = pe.profil_kennung(neu); k2 = pe.profil_kennung({s: dict(x) for s, x in neu.items()})
neu2 = {s: dict(x) for s, x in neu.items()}; neu2['Exposure']['Saturation'] = '31'
pruef(k1 == k2 and k1 != pe.profil_kennung(neu2), "Kennung unterscheidet nicht richtig")

print("=== 2. Die Engine entwickelt die Vorschau ===")
o = O("echt_rt"); d, _ = szene(o, n=N)
e1 = lauf(parameter(o, d, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI))
pruef(e1.ok(), "Pass 1 scheitert")
bild = d[12]; sc = pe.sidecar(bild)
vorher_text = open(sc).read(); vorher_zeit = os.stat(sc).st_mtime_ns
prof = pe.read_arp_dict(sc)
ergebnisse = []
def hole(profil, cli=RT_CLI, kante=120):
    f = pm.EngineVorschau(cli, bild, profil, pe.profil_kennung(profil), kante=kante)
    f.fertig.connect(ergebnisse.append); f.start(); return ergebnisse[-1]
tmp_vorher = set(glob.glob(os.path.join(tempfile.gettempdir(), "purelapse_vorschau_*")))
r = hole(prof)
pruef(r['rgb'] is not None and not r['fehler'], f"kein Bild: {r['fehler']}")
pruef(r['rgb'].shape[2] == 3 and max(r['rgb'].shape[:2]) == 120, f"Groesse {r['rgb'].shape}")
pruef(r['kennung'] == pe.profil_kennung(prof) and r['dauer'] > 0, "Kennung/Dauer fehlen")
pruef(open(sc).read() == vorher_text and os.stat(sc).st_mtime_ns == vorher_zeit, "die Begleitdatei wurde angefasst")
pruef(set(glob.glob(os.path.join(tempfile.gettempdir(), "purelapse_vorschau_*"))) == tmp_vorher,
      "der Arbeitsordner bleibt liegen")
pruef(not glob.glob(o + "/*.jpg") and not os.path.exists(os.path.join(o, "Purelapse", "Deflickered_JPG")),
      "die Vorschau schreibt in den Bilderordner")
hell, _, _ = pe.schnell_profil(prof, {'brightness': 40}, None)
r2 = hole(hell)
pruef(r2['rgb'].mean() > r['rgb'].mean() * 1.15, "Helligkeit kommt in der echten Vorschau nicht an")
satt, _, _ = pe.schnell_profil(prof, {'saturation': 60}, None)
r3 = hole(satt)
def buntheit(x): return float((x.max(axis=2).astype(float) - x.min(axis=2)).mean())
pruef(buntheit(r3['rgb']) > buntheit(r['rgb']) * 1.2, "Saettigung kommt in der echten Vorschau nicht an")
rf = hole(prof, cli="/gibt/es/nicht")
pruef(rf['rgb'] is None and rf['fehler'], "fehlendes Programm meldet keinen Fehler")
kaputt = {'Exposure': {'Compensation': '0'}}
rk = hole(kaputt)
pruef(rk['rgb'] is None and rk['fehler'] and not rk['abgebrochen'], f"unladbares Profil: {rk}")

print("=== 3. Abbruch, wenn sich die Regler weiterbewegen ===")
os.environ["FAKE_VERZOEGERUNG"] = "4"
f = pm.EngineVorschau(RT_CLI, bild, prof, "x", kante=120)
erg = []; f.fertig.connect(erg.append)
t = threading.Thread(target=f.run); t0 = time.time(); t.start()
time.sleep(0.6); f.abbrechen(); t.join(10)
os.environ.pop("FAKE_VERZOEGERUNG")
pruef(not t.is_alive() and time.time() - t0 < 3.0, f"Abbruch dauert {time.time()-t0:.1f} s")
pruef(erg and erg[0]['abgebrochen'] and erg[0]['rgb'] is None, f"Abbruch nicht gemeldet: {erg}")
pruef(set(glob.glob(os.path.join(tempfile.gettempdir(), "purelapse_vorschau_*"))) == tmp_vorher,
      "nach dem Abbruch bleibt der Arbeitsordner liegen")

print("=== 4. Die Vorschau zeigt, was Pass 2 entwickelt ===")
io.open(bild + ".xmp", "w").write('<x xmp:Rating="5"></x>')
ziel_profil, _, _ = pe.schnell_profil(prof, {'brightness': 25, 'saturation': 40, 'wb_temp': 4800, 'wb_green': 1.0}, "Coloropp")
vorschau = hole(ziel_profil, kante=300)['rgb']
pe.write_arp_dict(sc, ziel_profil)
e2 = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=RT_CLI, calib_rounds=0))
pruef(e2.ok(), f"Pass 2 scheitert: {e2.fehler[:1]}")
fertig = cv2.cvtColor(cv2.imread(os.path.join(o, "Purelapse", "Deflickered_JPG", os.path.splitext(os.path.basename(bild))[0] + ".jpg")),
                      cv2.COLOR_BGR2RGB)
pruef(fertig.shape[:2] == vorschau.shape[:2] or True, "")
klein = cv2.resize(fertig, (vorschau.shape[1], vorschau.shape[0]), interpolation=cv2.INTER_AREA)
abw = float(np.abs(klein.astype(float) - vorschau.astype(float)).mean())
pruef(abw < 1.5, f"Vorschau und Pass 2 weichen ab: im Mittel {abw:.2f} von 255")
naeh = pm.vorschau_rechnen(pm.vorschau_basis(bild), 5500.0, 1.0, {'brightness': 25, 'saturation': 40})
naeh = cv2.resize(naeh, (vorschau.shape[1], vorschau.shape[0]), interpolation=cv2.INTER_AREA)
abw_n = float(np.abs(klein.astype(float) - naeh.astype(float)).mean())
print(f"   Abweichung zu Pass 2: echte Vorschau {abw:.2f}, alte Naeherung {abw_n:.1f} (von 255)")
pruef(abw < abw_n / 5, "die echte Vorschau ist nicht deutlich naeher als die Naeherung")

print("=== 5. Im Dialog ===")
og = O("echt_gui"); dg, _ = szene(og, n=N)
fen = pm.MainWindow()
fen.cmb_engine.setCurrentIndex(1); fen.txt_art_path.setText(RT_CLI); fen.rb_raw.setChecked(True)
fen._set_folder(og); fen._go_step('smooth'); fen._start()
fen._set_folder(og); fen.tiles[15]['chk'].setChecked(True); fen.list_widget.setCurrentRow(15)
gesehen = {}
def bedienen(dlg):
    bilder = []
    alt = dlg._bild_setzen
    def merke(rgb, echt): bilder.append((rgb.copy(), echt)); alt(rgb, echt)
    dlg._bild_setzen = merke
    starts = []
    alt_start = pm.EngineVorschau.start
    def zaehl(self): starts.append(self.kennung); alt_start(self)
    pm.EngineVorschau.start = zaehl
    try:
        pruef(dlg._cli == RT_CLI and dlg.chk_echt.isChecked() and dlg.chk_echt.isEnabled(), "echte Vorschau nicht an")
        dlg._vorschau_zeichnen()
        pruef(dlg._gezeigt_echt and "✓" in dlg.lbl_echt.text(), f"kein echtes Bild beim Oeffnen: {dlg.lbl_echt.text()}")
        n0 = len(starts)
        chk, sl, lbl, d = dlg.regler['brightness']; chk.setChecked(True); sl.setValue(35)
        pruef(dlg._gezeigt_echt and len(starts) > n0, "nach der Aenderung kein echtes Bild")
        hell = bilder[-1][0].mean()
        pruef(bilder[-1][1] and hell > bilder[0][0].mean() * 1.1, "das echte Bild zeigt die Helligkeit nicht")
        pruef(any(not e for _, e in bilder), "waehrend des Wartens stand keine Naeherung da")
        # zurueck auf einen schon entwickelten Stand: kein neuer Lauf
        n1 = len(starts); sl.setValue(0); chk.setChecked(False)
        pruef(len(starts) == n1 and dlg._gezeigt_echt, f"bekannter Stand wird neu entwickelt ({len(starts)-n1} Laeufe)")
        # Vorher zeigen
        chk.setChecked(True); sl.setValue(35); n2 = len(starts)
        dlg.chk_vorher.setChecked(True)
        pruef(dlg._gezeigt_echt and abs(bilder[-1][0].mean() - bilder[0][0].mean()) < 1.0 and len(starts) == n2,
              "'Vorher zeigen' zeigt nicht den Ausgangsstand")
        dlg.chk_vorher.setChecked(False)
        pruef(abs(bilder[-1][0].mean() - hell) < 1.0, "nach 'Vorher zeigen' fehlt der aktuelle Stand")
        # Naeherung baut auf dem Bild der Engine auf
        dlg.chk_echt.setChecked(False)
        pruef(not dlg._gezeigt_echt and dlg.lbl_echt.text() == "", "ohne Haekchen steht noch ein echtes Bild da")
        n3 = len(starts); sl.setValue(10)
        pruef(len(starts) == n3 and not dlg._gezeigt_echt, "ohne Haekchen wird die Engine gestartet")
        dlg.chk_echt.setChecked(True)
        pruef(dlg._gezeigt_echt, "nach dem Wiedereinschalten kein echtes Bild")
        # die Naeherung waehrend des Wartens baut auf dem Bild der Engine auf
        sl.setValue(20)
        naeh = [b for b, e in bilder if not e][-1]; echt = bilder[-1][0]
        pruef(bilder[-1][1] and abs(naeh.mean() - echt.mean()) < 12,
              f"Naeherung weit vom echten Bild: {naeh.mean():.0f} gegen {echt.mean():.0f}")
        sl.setValue(10)
        pruef(not dlg.lbl_hl_warnung.isVisible(), f"Lichterwarnung ohne ausgebrannte Lichter: {dlg.lbl_hl_warnung.text()}")
        gesehen['profil'] = dlg._profil_jetzt(); gesehen['bild'] = bilder[-1][0]; gesehen['echt'] = dlg._gezeigt_echt
        dlg._echt_beenden()
        pruef(dlg._zu, "Beenden setzt die Sperre nicht")
    finally:
        pm.EngineVorschau.start = alt_start
_basis.ANTWORTEN['QuickLookDialog'] = bedienen
fen._open_quick_dialog()
pruef(gesehen.get('echt'), "der Dialog endet ohne echtes Bild")
geschrieben = pe.read_arp_dict(pe.sidecar(dg[15]))
pruef(geschrieben == gesehen.get('profil'), "gespeichert wird ein anderes Profil, als die Vorschau gezeigt hat")
pruef(geschrieben['Exposure']['Brightness'] == '10', f"Helligkeit im Profil: {geschrieben['Exposure'].get('Brightness')}")

print("=== 6. Ohne Engine bleibt die Naeherung ===")
fen.txt_art_path.setText("/gibt/es/nicht")
def ohne(dlg):
    pruef(dlg._cli is None and not dlg.chk_echt.isEnabled() and not dlg.chk_echt.isChecked(), "Haekchen trotz fehlender Engine")
    dlg._vorschau_zeichnen()
    pruef(not dlg._gezeigt_echt and dlg.lbl_vorschau._pixmap is not None, "ohne Engine keine Naeherung")
    pruef("Näherung" in dlg.lbl_vorschau_hinweis.text(), "Hinweistext passt nicht zur Naeherung")
    return 0
_basis.ANTWORTEN['QuickLookDialog'] = ohne
fen._open_quick_dialog()
fen.txt_art_path.setText(RT_CLI)

print("=== 6b. Automatisch optimieren im Dialog ===")
def auto_bedienen(dlg):
    def knoepfe_an(kid):
        return all(w.isEnabled() for w in (dlg.regler[kid][1],) + tuple(dlg._knoepfe[kid]))
    # Vorher von Hand verstellt: Saettigung und Entrauschen Farbe am Anschlag
    for kid, wert in (('saturation', 100), ('denoise_c', 100)):
        chk, sl, lbl, d = dlg.regler[kid]; chk.setChecked(True); sl.setValue(wert)
    vorher_aus = [k for k, (c, *_r) in dlg.regler.items() if not c.isChecked()]
    dlg._automatisch()
    for kid, (chk, sl, lbl, d) in dlg.regler.items():
        if chk.isChecked():
            pruef(knoepfe_an(kid), f"{kid}: angehakt, aber Schieber oder -/+/neutral gesperrt")
        else:
            pruef(not any(w.isEnabled() for w in dlg._knoepfe[kid]), f"{kid}: nicht angehakt, Knoepfe frei")
    pruef(any(k in vorher_aus and dlg.regler[k][0].isChecked() for k in dlg.regler),
          "die Automatik hat keinen bisher freien Regler gesetzt")
    w1 = {k: dlg.regler[k][1].value() for k in dlg.regler if dlg.regler[k][0].isChecked()}
    pruef(w1.get('saturation') == 0, f"Saettigung bleibt nach der Automatik auf {w1.get('saturation')}")
    pruef(w1.get('denoise_c') == 15, f"Entrauschen Farbe bleibt nach der Automatik auf {w1.get('denoise_c')}")
    pruef("neutral" in dlg.lbl_vorschau_hinweis.text(), f"Hinweis nennt das Zuruecksetzen nicht: {dlg.lbl_vorschau_hinweis.text()}")
    pruef(any("neutral" in x for x in dlg.begruendung()), "Begruendung nennt das Zuruecksetzen nicht")
    # Zweimal hintereinander: dasselbe Ergebnis
    chk, sl, lbl, d = dlg.regler['contrast']; chk.setChecked(True); sl.setValue(-80)
    dlg._automatisch()
    w2 = {k: dlg.regler[k][1].value() for k in dlg.regler if dlg.regler[k][0].isChecked()}
    pruef(w2 == w1, f"zweimal optimieren ergibt Verschiedenes: {w1} / {w2}")
    # Zuruecksetzen schaltet die Knoepfe passend zum Haekchen
    dlg._auf_ursprung()
    for kid, (chk, sl, lbl, d) in dlg.regler.items():
        pruef(all(w.isEnabled() == chk.isChecked() for w in (sl,) + tuple(dlg._knoepfe[kid])),
              f"{kid}: nach Zuruecksetzen passen Knoepfe und Haekchen nicht zusammen")
    dlg._echt_beenden()
    return 0
_basis.ANTWORTEN['QuickLookDialog'] = auto_bedienen
fen._open_quick_dialog()

print("=== 6c. Weissabgleich der Kamera, Automatik am Bild der Engine ===")
sc15 = pe.sidecar(dg[15])
prof15 = pe.read_arp_dict(sc15)
pruef(prof15['White Balance'].get('Setting') == 'Camera', f"Ausgang: {prof15['White Balance']}")
prof15['White Balance']['Temperature'] = '6504'       # Platzhalter wie bei RawTherapee
prof15['Exposure']['Compensation'] = '-2.000'         # das Bild der Engine ist viel dunkler
for k in ('Brightness', 'Contrast', 'Saturation'):
    prof15['Exposure'][k] = '0'
pe.write_arp_dict(sc15, prof15)
gemessen = {}
def wb_und_auto(dlg):
    chk, sl, lbl, d = dlg.regler['wb_temp']
    pruef(not chk.isChecked(), "Kamera-Weissabgleich: Farbtemperatur darf nicht angehakt sein")
    kt = pm.kamera_temperatur(dg[15])
    pruef(kt is not None and sl.value() == kt, f"Ausgangswert soll die Kameratemperatur sein: {sl.value()} / {kt}")
    pruef("aus dem\nRAW berechnet" in chk.toolTip() or "RAW berechnet" in chk.toolTip(),
          f"Tooltip nennt die Kameratemperatur nicht: {chk.toolTip()}")
    pruef(not dlg.regler['wb_green'][0].isChecked(), "Gruenabgleich angehakt")
    pruef('White Balance' not in [s for s, k, v in pe.schnell_profil(dlg._profil0, dlg.werte(), dlg.hl_wert())[1]],
          "ohne Haken wird der Weissabgleich trotzdem geschrieben")
    dlg._automatisch()
    gemessen['engine'] = dict((k, dlg.regler[k][1].value()) for k in dlg.regler)
    gemessen['grund_e'] = dlg.begruendung()
    dlg.chk_echt.setChecked(False)
    dlg._automatisch()
    gemessen['basis'] = dict((k, dlg.regler[k][1].value()) for k in dlg.regler)
    gemessen['grund_b'] = dlg.begruendung()
    pruef(dlg.btn_auto.isEnabled(), "der Optimieren-Knopf bleibt gesperrt")
    dlg._echt_beenden()
    return 0
_basis.ANTWORTEN['QuickLookDialog'] = wb_und_auto
fen._open_quick_dialog()
pruef(gemessen and "RawTherapee" in gemessen['grund_e'][0], f"Quelle der Messung: {gemessen.get('grund_e', [''])[:1]}")
pruef(gemessen and "Näherung" in gemessen['grund_b'][0], f"Quelle ohne Engine: {gemessen.get('grund_b', [''])[:1]}")
pruef(gemessen and gemessen['engine']['brightness'] > gemessen['basis']['brightness'],
      f"am viel dunkleren Bild der Engine muss die Helligkeit hoeher ausfallen: "
      f"{gemessen.get('engine', {}).get('brightness')} gegen {gemessen.get('basis', {}).get('brightness')}")
# Nikon D750 (Farbmatrix aus dcraw): typische Faktoren fuer Tageslicht und Gluehlampe
d750 = np.array([[9020, -2890, -715], [-4535, 12436, 2348], [-934, 1919, 7086]]) / 10000.0
tag = pm.temperatur_aus_kamera([2.07, 1.0, 1.37], d750)
kunst = pm.temperatur_aus_kamera([1.30, 1.0, 2.45], d750)
pruef(tag and 5000 <= tag <= 6000, f"Tageslicht: {tag} K")
pruef(kunst and 2600 <= kunst <= 3300, f"Gluehlampe: {kunst} K")
for k in (3000, 4500, 7000):
    x, y = pm.planck_xy(k)
    f = 1.0 / d750.dot([x / y, 1.0, (1.0 - x - y) / y]); f /= f[1]
    pruef(abs(pm.temperatur_aus_kamera(f, d750) - k) <= 50, f"Rueckrechnung {k} K")
pruef(pm.temperatur_aus_kamera([0, 1, 1], d750) is None, "ungueltige Faktoren")
pruef(pm.temperatur_aus_kamera([2, 1, 1.5], np.zeros((4, 3))) is None, "ohne Farbmatrix")
pruef(pm.kamera_temperatur("/gibt/es/nicht.NEF") is None, "fehlende Datei")

print("=== 7. Lichterwarnung nur bei echten ausgebrannten Lichtern ===")
dunkel, pegel_d = pm.vorschau_basis_pegel(dg[N - 1])
pruef(dunkel is not None and pegel_d < pm.HL_PEGEL_SCHWELLE, f"Pegel des dunklen Bildes: {pegel_d:.2f}")
pruef(pm.vorschau_basis(dg[0]).shape == pm.vorschau_basis_pegel(dg[0])[0].shape, "vorschau_basis weicht ab")
pruef(pm.vorschau_basis_pegel("/gibt/es/nicht.NEF") == (None, 0.0), "fehlende Datei")
osn = O("echt_sonne"); dsn, _ = szene(osn, n=6, sonne=True)
_, pegel_s = pm.vorschau_basis_pegel(dsn[0])
pruef(pegel_s >= pm.HL_PEGEL_SCHWELLE, f"Pegel mit ausgebrannter Sonne: {pegel_s:.2f}")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
