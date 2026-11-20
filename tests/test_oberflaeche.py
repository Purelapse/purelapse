# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Oberflaeche: Ablauf-Anzeige, Protokoll mit Zeitstempel, Farbschema."""
import os, sys, io, re, glob, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import _basis

OK = FEHL = 0
def pruef(b, text):
    global OK, FEHL
    if b: OK += 1
    else:
        FEHL += 1; print("  FEHLER:", text)
def O(name): return os.path.join(ARBEIT, name)

print("=== 1. Statuszeile zerlegen ===")
z = pm.status_zerlegen
pruef(z("Entwicklung: 12/963 | 0:10 von ca. 9:00 | Rest 8:50") == ("Entwicklung", 12, 963, ""), str(z("Entwicklung: 12/963 | 0:10 von ca. 9:00 | Rest 8:50")))
pruef(z("Rendere Video: 5/60 | Blur 3 | 0:01 von ca. 0:10 | Rest 0:09") == ("Rendere Video", 5, 60, "Blur 3"), "Zusatz geht verloren")
pruef(z("Schreibe Sidecar: IMG_0001.NEF") == ("Schreibe Sidecar", 0, 0, ""), str(z("Schreibe Sidecar: IMG_0001.NEF")))
pruef(z("Vergleichsvideo wird erstellt...")[0].startswith("Vergleichsvideo"), "Text ohne Zaehler")
pruef(z("Suche defekte Pixel: 3/12") == ("Suche defekte Pixel", 3, 12, ""), "Zaehler ohne Zeiten")
pruef(z("")[0] == "" and z(None)[0] == "", "leere Zeile")
# jede Zeile, die fortschritt_text baut, muss sich wieder zerlegen lassen
import time as _t
for lab, f, g, zus in (("Messe Ergebnis", 0, 50, ""), ("Nachkalibrierung 2", 7, 9, ""), ("Lese Daten", 3, 0, ""), ("Rendere Video", 9, 9, "x")):
    for lang in ('de', 'en'):
        txt = pm.fortschritt_text(lab, f, g, _t.time() - 5, zus, lang)
        erg = z(txt)
        pruef(erg[0] == lab and (erg[1], erg[2]) == ((f, g) if g else (0, 0)) and erg[3] == zus, f"{txt!r} -> {erg}")
k = pm.status_kurz
pruef(k("Entwicklung: 12/963 | 0:10 von ca. 9:00 | Rest 8:50") == "Entwicklung  \u00b7  12 von 963", k("Entwicklung: 12/963 | 0:10 von ca. 9:00 | Rest 8:50"))
pruef("of 963" in k("Entwicklung: 12/963 | 0:10 of approx. 9:00 | 8:50 left", 'en'), "englische Kurzfassung")
pruef(k("Fertig \u2714") == "Fertig \u2714" and k("Schreibe Sidecar: A.NEF") == "Schreibe Sidecar: A.NEF", "andere Texte werden veraendert")
pruef("Blur 3" in k("Rendere Video: 5/60 | Blur 3 | 0:01 von ca. 0:10 | Rest 0:09"), "Zusatz fehlt in der Kurzfassung")

print("=== 2. Plan ===")
P = pm.ablauf_plan
pruef(P({'format': 'raw', 'raw_mode': 'pass2', 'make_video': True, 'calib_rounds': 2}) == ['entwicklung', 'messung', 'kalib', 'video'], str(P({'format': 'raw', 'raw_mode': 'pass2', 'make_video': True, 'calib_rounds': 2})))
pruef(P({'format': 'raw', 'raw_mode': 'pass2', 'make_video': True, 'calib_rounds': 0, 'stabilize': True}) == ['entwicklung', 'messung', 'stab', 'video'], "ohne Nachkalibrierung, mit Stabilisierung")
pruef(P({'format': 'raw', 'raw_mode': 'pass1'}) == ['analyse', 'schreiben'], "Pass 1")
pruef(P({'format': 'jpg', 'make_video': True}) == ['lesen', 'video'] and P({'format': 'jpg', 'make_video': False}) == ['lesen'], "JPG")
pruef(P({'mode': 'plain'}) == ['roh'] and P({'mode': 'compare'}) == ['vergleich'] and P({'mode': 'preview'}) == [], "Sonderlaeufe")
bekannt = {key for _a, key, _d, _e in pm.PHASEN}
pruef(all(k in bekannt for p in ({'format': 'raw', 'raw_mode': 'pass2', 'stabilize': True}, {'format': 'jpg', 'stabilize': True}, {'mode': 'plain'}) for k in P(p)), "Plan nennt unbekannte Schritte")

print("=== 3. Ablauf ===")
A = pm.Ablauf(['entwicklung', 'messung', 'kalib', 'video'], jetzt=1000.0)
pruef([s['zustand'] for s in A.schritte] == ['offen'] * 4 and A.aktiver() is None, "Anfangszustand")
A.melde("Entwicklung", 1, 100, 1002.0); A.melde("Entwicklung", 50, 100, 1052.0)
e = A.schritte[0]
pruef(e['zustand'] == 'aktiv' and abs(A.dauer(e, 1052.0) - 50) < 1e-6, f"laufender Schritt: {e}")
pruef(abs(A.rest(e, 1052.0) - 50) < 1e-6, f"Restzeit {A.rest(e, 1052.0)}")
A.melde("Messe Ergebnis", 1, 100, 1102.0)
pruef(e['zustand'] == 'fertig' and abs(e['dauer'] - 100) < 1e-6 and e['ende'] == 1102.0, f"abgeschlossener Schritt: {e}")
pruef(A.schritte[1]['zustand'] == 'aktiv', "Messung nicht aktiv")
A.melde("Nachkalibrierung 1", 3, 20, 1130.0)
pruef(A.schritte[1]['zustand'] == 'fertig' and A.schritte[2]['zustand'] == 'aktiv' and A.schritte[2]['runde'] == 1, "Nachkalibrierung")
A.melde("Messe Ergebnis", 5, 20, 1140.0)
pruef(A.schritte[2]['zustand'] == 'aktiv' and A.schritte[1]['zustand'] == 'fertig' and abs(A.schritte[1]['dauer'] - 28) < 1e-6,
      "die Messung nach der Nachkalibrierung springt zurueck")
pruef(abs(A.rest(A.schritte[2], 1150.0) - 30) < 1e-6, f"Restzeit rechnet nicht ab dem Teilschritt: {A.rest(A.schritte[2], 1150.0)}")
A.melde("Nachkalibrierung 2", 1, 5, 1160.0)
pruef(A.schritte[2]['runde'] == 2 and len(A.schritte) == 4, "zweite Runde legt einen neuen Schritt an")
A.melde("Rendere Video", 10, 100, 1200.0)
pruef(abs(A.schritte[2]['dauer'] - 70) < 1e-6 and A.schritte[3]['zustand'] == 'aktiv', "Uebergang zum Video")
A.abschliessen(True, 1300.0)
pruef([s['zustand'] for s in A.schritte] == ['fertig'] * 4 and A.ende == 1300.0 and A.erfolg, "Abschluss")
pruef(abs(A.gesamt_dauer(9999.0) - 300) < 1e-6, "Gesamtdauer laeuft nach dem Ende weiter")
pruef(abs(sum(s['dauer'] for s in A.schritte) - 298) < 1e-6, f"Summe der Schritte: {sum(s['dauer'] for s in A.schritte)}")
A.melde("Entwicklung", 1, 2, 1400.0)
pruef(A.schritte[0]['zustand'] == 'fertig', "nach dem Ende wird noch etwas geaendert")
# Schritt entfaellt, unerwarteter Schritt kommt dazu
B = pm.Ablauf(['entwicklung', 'messung', 'kalib', 'video'], jetzt=0.0)
B.melde("Entwicklung", 1, 5, 1.0); B.melde("Messe Ergebnis", 1, 5, 10.0); B.melde("Analysiere Kamera-Wackeln", 1, 5, 20.0)
pruef([s['key'] for s in B.schritte] == ['entwicklung', 'messung', 'stab', 'kalib', 'video'], f"unerwarteter Schritt falsch eingereiht: {[s['key'] for s in B.schritte]}")
B.melde("Rendere Video", 1, 5, 30.0)
pruef(B.schritte[3]['zustand'] == 'entfallen', "uebersprungener Schritt nicht als entfallen markiert")
B.abschliessen(False, 40.0)
pruef(B.schritte[4]['zustand'] == 'fehler' and B.erfolg is False, "Abbruch")
C = pm.Ablauf(['analyse', 'schreiben'], jetzt=0.0); C.melde("Analysiere RAWs", 2, 10, 5.0); C.abschliessen(False, 6.0)
pruef([s['zustand'] for s in C.schritte] == ['fehler', 'offen'], "nach einem Abbruch gilt der Rest als entfallen")
D = pm.Ablauf([], jetzt=0.0); D.melde("Etwas ganz Neues", 1, 3, 1.0); D.melde("Rendere Video", 1, 3, 2.0)
pruef([s['key'] for s in D.schritte] == ["Etwas ganz Neues", 'video'], "ohne Plan")
pruef(pm.phase_titel("Etwas ganz Neues") == "Etwas ganz Neues" and pm.phase_titel('video', 'en') == "Render video", "Titel")

print("=== 4. Beschriftung ===")
A2 = pm.Ablauf(['entwicklung', 'messung', 'kalib', 'video'], jetzt=1000.0)
A2.melde("Entwicklung", 1, 100, 1000.0); A2.melde("Messe Ergebnis", 40, 100, 1761.0)
tx = [pm.ablauf_texte(A2, s, 'de', 1801.0) for s in A2.schritte]
pruef(tx[0][0].startswith("\u2713") and "12:41" in tx[0][1] and "bis " in tx[0][1], f"erledigt: {tx[0]}")
pruef(tx[1][0].startswith("\u25cf") and "seit 0:40" in tx[1][1] and "Rest ca. 1:00" in tx[1][1], f"laufend: {tx[1]}")
pruef(tx[2][0].startswith("\u25cb") and tx[2][1] == "steht aus", f"ausstehend: {tx[2]}")
pruef("40 / 100" in tx[1][2] and "begonnen" in tx[1][2], f"Tooltip: {tx[1][2]!r}")
en = [pm.ablauf_texte(A2, s, 'en', 1801.0) for s in A2.schritte]
pruef("left" in en[1][1] and en[2][1] == "pending" and "Development" in en[0][0], f"englisch: {en}")
pruef(not any(w in " ".join(x[0] + x[1] for x in en) for w in ("seit", "Rest", "steht", "bis ")), "deutsche Reste in der englischen Fassung")
kopf = pm.ablauf_kopf(A2, 'de', 1801.0)
pruef("gestartet" in kopf and "l\u00e4uft seit 13:21" in kopf, kopf)
A2.abschliessen(True, 1900.0)
pruef("Dauer 15:00" in pm.ablauf_kopf(A2, 'de') and "\u2013" in pm.ablauf_kopf(A2, 'de'), pm.ablauf_kopf(A2, 'de'))
pruef(pm.ablauf_kopf(None) == "", "ohne Ablauf")
pruef(pm.ablauf_texte(A2, A2.schritte[2], 'de')[1] == "nicht n\u00f6tig", "entfallen")

print("=== 5. Protokoll ===")
t = pm.thema_mit_schritt('dark', 'render')
w = datetime.datetime(2026, 11, 16, 21, 4, 13)
pruef(pm.log_stempel(w) == "16.11. 21:04:13", pm.log_stempel(w))
la = pm.log_art
pruef(la("purelapse@engine:~$ INIT PROCESS (v2.24.0)") == ('kopf', "INIT PROCESS (v2.24.0)"), str(la("purelapse@engine:~$ INIT PROCESS (v2.24.0)")))
pruef(la("purelapse@engine:~$ ABBRUCH DURCH BENUTZER ANGEFORDERT...")[0] == 'fehler', "Abbruch")
pruef(la("> WARNUNG: Keine Keyframes gefunden.") == ('warnung', "WARNUNG: Keine Keyframes gefunden."), "Warnung")
pruef(la("> ACHTUNG: 3 Formatabweichungen")[0] == 'warnung' and la("[FEHLER] kaputt")[0] == 'fehler', "Achtung/Fehler")
pruef(la("    [Exposure] Saturation = 22") == ('fort', "[Exposure] Saturation = 22"), "Fortsetzungszeile")
pruef(la("/usr/bin/ffmpeg -y -f rawvideo -i - out.mp4")[0] == 'befehl' and la("/x/ART-cli -S -Y -o /a -c <Bilderliste>")[0] == 'befehl', "Befehlszeile")
pruef(la("> Ziel erreicht, keine weitere Nachkalibrierung noetig.")[0] == 'ok', "Erfolg")
pruef(la("> Restflackern nach Entwicklung: 0.0042 EV (Sigma)") == ('text', "Restflackern nach Entwicklung: 0.0042 EV (Sigma)"), "normale Zeile")
pruef(la("> Hinweis: keine Warnung im Text")[0] == 'text', "'Warnung' mitten im Satz faerbt die Zeile")
h = pm.log_html("> Starte RAW Pass 2 (Rendern)...", w, t)
pruef("16.11. 21:04:13" in h and "Starte RAW Pass 2" in h and "&gt; " not in h, h)
h = pm.log_html("\n[FEHLER] a < b & c", w, t)
pruef("a &lt; b &amp; c" in h and t['err'] in h and h.count("16.11.") == 1, f"Sonderzeichen/Fehler: {h}")
h = pm.log_html("> 3 Prozesse parallel\n/x/ART-cli -S -o /a -c <Bilderliste>\n", w, t)
pruef(h.count("<br>") == 1 and h.count("21:04:13") == 1 and "&lt;Bilderliste&gt;" in h, f"mehrzeilig: {h}")
pruef(pm.log_html("\n\n", w, t) == "" and pm.log_html("", w, t) == "", "leere Meldung erzeugt eine Zeile")
for art_ in ('accent', 'err', 'warn', 'ok', 'faint', 'dim', 'log_fg'):
    for thema in ('dark', 'light'):
        tt = pm.thema_mit_schritt(thema, 'render')
        pruef(pm.kontrast(tt[art_], tt['log_bg']) >= (2.6 if art_ == 'faint' else 4.0),
              f"{thema}: Protokollfarbe {art_} zu kontrastarm ({pm.kontrast(tt[art_], tt['log_bg']):.1f})")

print("=== 6. Farbschema ===")
for thema in ('dark', 'light'):
    for schritt in ('load', 'smooth', 'keys', 'render'):
        tt = pm.thema_mit_schritt(thema, schritt)
        qss = pm.build_stylesheet(tt)
        pruef(qss.count("{") == qss.count("}"), f"{thema}/{schritt}: Klammern unausgeglichen")
        pruef("border-top: 5px solid" not in qss, "der Rahmen-Trick fuer den Pfeil ist noch da")
        bilder = re.findall(r"url\(([^)]*)\)", qss)
        pruef(len(bilder) >= 6 and all(b and os.path.exists(b) for b in bilder), f"{thema}/{schritt}: Bilder fehlen: {bilder}")
        for name in ("QFrame#statuscard", "QLabel#statustitel", 'QFrame#phase[zustand="aktiv"]', "QFrame#phasenstrich",
                     'QLabel#phasename[zustand="offen"]', "QLabel#badge", "QFrame#trenner", "QLabel#prozent"):
            pruef(name in qss, f"{thema}: Regel {name} fehlt")
        pruef(pm.kontrast(tt['text'], tt['panel']) >= 7 and pm.kontrast(tt['dim'], tt['panel']) >= 4.5,
              f"{thema}: Schrift auf Flaeche zu kontrastarm")
        pruef(pm.kontrast(tt['faint'], tt['panel']) >= 2.5, f"{thema}: blasse Schrift nicht mehr lesbar")
        pruef(pm.kontrast(tt['accent'], pm.farbe_mischen(tt['panel2'], tt['accent'], 0.10)) >= 4.0, f"{thema}/{schritt}: aktiver Schritt zu kontrastarm")
    th = pm.THEMES[thema]
    pruef(len({th['bg'], th['panel'], th['panel2']}) >= 2 and all(k in th for k in ('hover', 'border2', 'faint', 'err')), f"{thema}: Farben fehlen")
import cv2
pf = pm.ui_bild('haken', "#0d1117"); img = cv2.imread(pf, cv2.IMREAD_UNCHANGED)
pruef(img is not None and img.shape == (11, 11, 4) and img[..., 3].max() > 200 and img[0, 0, 3] == 0, "Haken-Bild")
pruef(pm.ui_bild('gibtsnicht', "#fff") == "" and pm.ui_bild('pfeil_ab', "#8d95a3") == pm.ui_bild('pfeil_ab', "#8d95a3"), "Bild-Zwischenspeicher")

print("=== 7. Im Fenster ===")
N = 60
o = O("ui_gui"); d, _ = szene(o, n=N)
f = pm.MainWindow()
f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True)
f._set_folder(o)
pruef(not f.ablauf_leiste.isVisible() and f.lbl_lauf.text() == "", "vor dem ersten Lauf steht schon ein Ablauf da")
gesehen = []
alt = f._on_status
def merke(text):
    alt(text); gesehen.append((text, f.lbl_status.text(), f.ablauf_leiste.texte(), f.lbl_lauf.text()))
f._on_status = merke
f._go_step('smooth'); f._start()
pruef("Fertig" in f.lbl_status.text(), f"Pass 1: {f.lbl_status.text()}")
tx = f.ablauf_leiste.texte()
pruef(f.ablauf_leiste.isVisible() and len(tx) >= 1 and tx[0][2] == 'fertig' and tx[0][0].startswith("\u2713"), f"Ablauf nach Pass 1: {tx}")
pruef("Dauer" in f.lbl_lauf.text(), f"Laufzeit nach dem Ende: {f.lbl_lauf.text()}")
zeilen = f.txt_log._zeilen
pruef(zeilen and all(re.match(r"^\d\d\.\d\d\. \d\d:\d\d:\d\d  ", z) for z in zeilen), f"Protokollzeilen ohne Zeitstempel: {[z for z in zeilen if not re.match(r'^[0-9]', z)][:2]}")
pruef(not any("purelapse@engine" in z for z in zeilen), "die Eingabeaufforderung steht noch im Protokoll")
pruef(len(f._log_eintraege) == len(zeilen), "Eintraege und Zeilen laufen auseinander")
f.tiles[15]['chk'].setChecked(True)
f._go_step('render'); f._start()
pruef("Fertig" in f.lbl_status.text(), f"Pass 2: {f.lbl_status.text()}")
tx = f.ablauf_leiste.texte()
namen = [x[0] for x in tx]
pruef(any("Entwicklung" in n for n in namen) and any("Video rendern" in n for n in namen), f"Schritte von Pass 2: {namen}")
pruef(all(x[2] in ('fertig', 'entfallen') for x in tx), f"nach dem Ende noch offene Schritte: {tx}")
pruef(all("bis " in x[1] for x in tx if x[2] == 'fertig'), f"erledigte Schritte ohne Zeit: {tx}")
lauf_ = [g for g in gesehen if g[0].startswith("Rendere Video")]
pruef(lauf_ and all(" | " not in g[1] for g in lauf_), f"Zeiten stehen noch in der Statuszeile: {lauf_[:1]}")
pruef(lauf_ and any(x[2] == 'aktiv' and "Video rendern" in x[0] and "seit" in x[1] for x in lauf_[-1][2]), f"laufender Schritt nicht hervorgehoben: {lauf_[-1][2] if lauf_ else ''}")
pruef(lauf_ and "gestartet" in lauf_[-1][3] and "l\u00e4uft seit" in lauf_[-1][3], f"Laufzeit waehrend des Laufs: {lauf_[-1][3] if lauf_ else ''}")
mitte = [g for g in gesehen if g[0].startswith("Messe Ergebnis")]
pruef(mitte and any(x[2] == 'offen' for x in mitte[0][2]) and any(x[2] == 'fertig' for x in mitte[0][2]),
      f"waehrend des Laufs fehlen erledigte oder ausstehende Schritte: {mitte[0][2] if mitte else ''}")
pruef(videos(o), "es entstand kein Video")
# Farbschema wechseln: das Protokoll bleibt vollstaendig
n_vor = len(f.txt_log._zeilen); text_vor = list(f.txt_log._zeilen)
f._apply_theme('light')
pruef(f.txt_log._zeilen == text_vor, "nach dem Wechsel des Farbschemas fehlt Protokoll")
f._apply_theme('dark')
# Englisch
f._apply_language('en') if hasattr(f, '_apply_language') else None
f._ablauf_zeigen()
txe = f.ablauf_leiste.texte()
pruef(any("Render video" in x[0] for x in txe) and "took" in f.lbl_lauf.text(), f"englische Fassung: {txe} / {f.lbl_lauf.text()}")
f._apply_language('de'); f._ablauf_zeigen()
# neuer Ordner: der alte Ablauf verschwindet
o2 = O("ui_gui2"); szene(o2, n=60); f._set_folder(o2)
pruef(not f.ablauf_leiste.isVisible() and f.lbl_lauf.text() == "", "der Ablauf des alten Ordners bleibt stehen")
# Abbruch
f._set_folder(o); f._go_step('render')
def kaputt(self): raise RuntimeError("Probe")
alt_run = pm.Worker._run_raw_pass2; pm.Worker._run_raw_pass2 = kaputt
_basis.ANTWORTEN['kritisch'] = None
try:
    f._start()
finally:
    pm.Worker._run_raw_pass2 = alt_run
pruef("Fehler" in f.lbl_status.text() and f._ablauf is not None and f._ablauf.erfolg is False, f"Fehlerfall: {f.lbl_status.text()}")
pruef(f.btn_log.isChecked() and any("Probe" in z and "\u2715" in z for z in f.txt_log._zeilen), "Fehler steht nicht hervorgehoben im Protokoll")
# Effekte
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
a = src.index('self.box_effects = QtWidgets.QGroupBox("Bild und Effekte")'); b = src.index("self.spalte_rechts.addWidget(self.box_effects", a)
eff = src[a:b]
for name in ("cmb_blur", "btn_cam_path", "lbl_cam_status", "chk_stab", "chk_reverse", "chk_hotpix", "chk_astro", "chk_tel", "chk_denoise"):
    pruef(f"self.{name} = " in eff and getattr(f, name, None) is not None, f"{name} fehlt in 'Bild und Effekte'")
pruef(eff.index("self.chk_denoise") > eff.index("self.chk_tel"), "Denoise steht nicht zuletzt - ausgeblendet bliebe eine Luecke")
pruef("#ffaa00" not in src[src.index("class MainWindow"):].split("def _open_camera_path_dialog")[1][:3000], "feste Farbe am Kamerafahrt-Schild")
pruef(pm.TRANSLATIONS.get("Bildausschnitt:") == "Framing:" and " 16:9 Kamerafahrt / Crop \u2026" in pm.TRANSLATIONS, "Uebersetzung fehlt")
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
