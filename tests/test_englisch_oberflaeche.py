# -*- coding: utf-8 -*-
"""Englische Oberflaeche: Statuszeile, Fertig-Meldungen, Telegram,
Tooltips und Listen ohne deutsche Reste."""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import _basis, QtWidgets
import purelapse_texte as tx
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

DEUTSCH = re.compile(r"[äöüÄÖÜß]|\b(Bilder|Bild|Ordner|fertig|Fertiges|liegen|wird|werden|erstellt|"
                     r"Schreibe|Erzeuge|Analysiere|Lese|Messe|Rendere|Rohfassung|Vergleichsvideo|"
                     r"Entwicklung|Nachkalibrierung|Suche|abgeschlossen|Weiter|freiwillig|"
                     r"Entflackerte|Keine|Kein|keine|nicht|von|und|oder|bitte|Bitte)\b")
def deutsch(s):
    # Pfade und Dateinamen zaehlen nicht
    return DEUTSCH.search(re.sub(r"/[\w./ -]+|IMG_\d+\S*|Deflickered_JPG", "", str(s)))

print("=== 1. Statuszeile ===")
start = time.time() - 10
for text, soll in (
        (pm.fortschritt_text("Analysiere RAWs", 3, 10, start, "IMG_0003.NEF"), "Measure RAWs  ·  3 of 10  ·  IMG_0003.NEF"),
        (pm.fortschritt_text("Entwicklung", 5, 9, start), "Development  ·  5 of 9"),
        (pm.fortschritt_text("Nachkalibrierung 2", 1, 9, start), "Recalibration 2  ·  1 of 9"),
        (pm.fortschritt_text("Rendere Video", 2, 9, start, lang='en'), "Render video  ·  2 of 9"),
        ("Schreibe Sidecar: IMG_0001.NEF", "Writing sidecar: IMG_0001.NEF"),
        ("Erzeuge einmalig ein Basisprofil...", "Creating a base profile (only once)..."),
        ("Vergleichsvideo wird erstellt...", "Creating comparison video..."),
        ("Suche defekte Pixel: 4/15", "Finding defective pixels: 4/15")):
    ist = pm.status_kurz(text, 'en')
    pruef(ist == soll, f"englisch: {text!r} -> {ist!r}, erwartet {soll!r}")
    pruef(pm.status_kurz(text, 'de') == pm.status_kurz(text), "deutsch haengt an der Voreinstellung")
pruef(pm.status_kurz(pm.fortschritt_text("Entwicklung", 5, 9, start), 'de') == "Entwicklung  ·  5 von 9",
      "deutsche Statuszeile veraendert")
pruef(pm.status_sprache("Unbekannter Schritt", 'en') == "Unbekannter Schritt", "Unbekanntes wird verfaelscht")
# Die Ablaufanzeige erkennt die Phase weiter am deutschen Anfang
pruef(pm.status_zerlegen(pm.fortschritt_text("Analysiere RAWs", 3, 10, start, lang='en'))[:3]
      == ("Analysiere RAWs", 3, 10), "englische Zeitangaben stoeren das Zerlegen")
schirm = pm.LadeSchirm(None)
schirm.zeige("/tmp/x", 'en')
schirm.stand(5, 56, pm.fortschritt_text("Reading images", 5, 56, start, lang='en'))
pruef(schirm.lbl_stand.text() == "Reading images  ·  5 of 56", f"Ladeschirm: {schirm.lbl_stand.text()!r}")

print("=== 2. Fertig-Meldungen, Telegram ===")
o = os.path.join(ARBEIT, "en_ui_jpg"); d, _ = szene(o, n=24, art="jpg")
e = lauf(parameter(o, d, lang='en'))
pruef(e.ok() and e.fertig[0].startswith("Video done:"), f"JPG fertig: {e.fertig[:1]} {e.fehler[:1]}")
e = lauf(parameter(o, d, lang='en', make_video=False))
pruef(e.ok() and e.fertig[0].startswith("Deflickered JPGs are in:"), f"JPG ohne Video: {e.fertig[:1]}")
pe.set_engine('rt')
o2 = os.path.join(ARBEIT, "en_ui_raw"); d2, _ = szene(o2, n=24)
e1 = lauf(parameter(o2, d2, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI, lang='en'))
pruef(e1.ok() and e1.fertig[0].startswith("Pass 1 complete") and not deutsch(e1.fertig[0]),
      f"Pass 1 fertig: {e1.fertig[:1]} {e1.fehler[:1]}")
e2 = lauf(parameter(o2, d2, raw_mode='pass2', art_cli_path=RT_CLI, lang='en'))
pruef(e2.ok() and e2.fertig[0].startswith("Finished video:"), f"Pass 2 fertig: {e2.fertig[:1]} {e2.fehler[:1]}")
deutsche_status = [s for s in e1.status + e2.status if deutsch(pm.status_kurz(s, 'en'))]
pruef(not deutsche_status, f"deutsche Statuszeilen: {[pm.status_kurz(s, 'en') for s in deutsche_status[:4]]}")
e_de = lauf(parameter(o2, d2, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI))
pruef(e_de.ok() and e_de.fertig[0].startswith("Pass 1 abgeschlossen"), "deutsche Fertig-Meldung veraendert")

ablauf = pm.Ablauf(['analyse', 'schreiben'])
text = pm.telegram_bericht(True, o2, "Pass 1, 24 frames", ablauf, e1.fertig[0], None, 'en')
pruef(not deutsch(text), f"Telegram-Bericht mit deutschem Text:\n{text}")
pruef(pm.telegram_senden("", "1", "x", lang='en')[1] == "No bot token entered.", "Telegram: fehlender Token")
pruef(pm.telegram_senden("T", "", "x", lang='en')[1] == "No chat ID entered.", "Telegram: fehlende Chat-ID")
pruef(pm.telegram_senden("", "1", "x")[1] == "Kein Bot-Token eingetragen.", "Telegram deutsch veraendert")

print("=== 3. Tooltips, Listen, Platzhalter ===")
for tab in (tx.TRANSLATIONS, tx.TRANSLATIONS_TT_EN):
    roh = [k for k, v in tab.items() if isinstance(v, str) and "\\n" in v]
    pruef(not roh, f"Tooltips mit sichtbarem \\n: {roh}")
tt_de = {k for k in tx.TRANSLATIONS if k.startswith("TT_")}
pruef(tt_de == set(tx.TRANSLATIONS_TT_EN), f"Tooltip-Schluessel ungleich: {tt_de ^ set(tx.TRANSLATIONS_TT_EN)}")
pm.save_lang('en')
f = pm.MainWindow()
pruef(f.lang == 'en', "Sprache nicht englisch")
for name in ('btn_erstes', 'btn_letztes', 'btn_start_hier', 'btn_ende_hier', 'txt_arp_template',
             'chk_diag', 'chk_tiff16', 'btn_schnell', 'chk_hotpix', 'btn_q_add'):
    tip = getattr(f, name).toolTip()
    pruef(tip and not deutsch(tip), f"{name}: Tooltip {tip[:70]!r}")
blur = [f.cmb_blur.itemText(i) for i in range(f.cmb_blur.count())]
pruef(blur[0] == "Off (1 frame)" and blur[1] == "3 frames" and not any(deutsch(b) for b in blur), f"Motion Blur: {blur[:3]}")
pruef(not deutsch(f.txt_tg_chat.placeholderText()) and not deutsch(f.txt_tg_token.placeholderText()),
      f"Telegram-Platzhalter: {f.txt_tg_chat.placeholderText()!r}")
f._apply_language('de')
pruef(f.cmb_blur.itemText(0) == "Aus (1 Bild)" and f.btn_erstes.toolTip() == "Zum ersten Bild",
      "zurueck auf Deutsch klappt nicht")
f._apply_language('en')
f._set_folder(o)
pruef(f.lbl_count.text().startswith("Folder selected") or not deutsch(f.lbl_count.text()),
      f"Zaehler nach dem Einlesen: {f.lbl_count.text()!r}")
pm.save_lang('de')

print("=== 4. Weitere Meldungen ===")
pruef(pm.probe_grund_text("FFmpeg wurde nicht gefunden.", 'en') == "FFmpeg was not found.", "Codec-Test: nicht gefunden")
pruef(pm.probe_grund_text("FFmpeg endete mit Fehlercode 3.", 'en') == "FFmpeg exited with error code 3.", "Codec-Test: Fehlercode")
pruef(pm.probe_grund_text("Unknown encoder 'x'", 'en') == "Unknown encoder 'x'", "FFmpeg-Text verfaelscht")
pruef(pm.probe_grund_text("FFmpeg wurde nicht gefunden.") == "FFmpeg wurde nicht gefunden.", "Codec-Test deutsch")
import numpy as np
bild = np.full((60, 90, 3), 0.18)
_, grund_en = pm.auto_optimieren(bild, iso=3200, lang='en')
_, grund_de = pm.auto_optimieren(bild, iso=3200)
pruef(grund_en and not any(deutsch(g) for g in grund_en), f"Schnelleinstellungen: {grund_en[:3]}")
pruef(len(grund_en) == len(grund_de) and any("Weissabgleich" in g for g in grund_de), "deutsche Begruendung veraendert")
ref = {'Version': {'AppVersion': '5.9'}, 'Exposure': {'Contrast': '0'}}
befund = pe.validate_arp({'Exposure': {'Contrast': 'x'}}, ref, "IMG_1.NEF", lang='en')
pruef(befund and not any(deutsch(b) for b in befund), f"Profilpruefung: {befund}")
pruef(any("fehlt" in b for b in pe.validate_arp({'Exposure': {}}, ref, "IMG_1.NEF")), "Profilpruefung deutsch")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
