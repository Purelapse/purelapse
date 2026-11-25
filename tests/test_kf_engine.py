# -*- coding: utf-8 -*-
"""Keyframes nach einem Engine-Wechsel: Bildleiste, Filter, Zaehler und
Dateien muessen dasselbe sagen. Fall aus der Praxis: oben "8 Keyframes",
der Filter zeigte 4 - die Sterne der Bildleiste stammten noch von Darktable."""
import os, sys, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

pe.set_engine('rt')
o = os.path.join(ARBEIT, "kf_engine"); d, _ = szene(o, n=24)
e = lauf(parameter(o, d, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI))
pruef(e.ok(), f"Pass 1: {e.fehler[:1]}")
# Zwei Keyframes nur im RawTherapee-Profil (ohne .xmp), einer mit Stern in der .xmp
for f in (d[5], d[12]):
    sc = f + ".pp3"; prof = pe.read_arp_dict(sc)
    prof.setdefault('General', {})['Rank'] = '5'; pe.write_arp_dict(sc, prof)
pe.bewertung_schreiben(d[18] + ".xmp", 5)
for f in d: 
    if f in (d[18],): continue
    if os.path.exists(f + ".xmp"): os.remove(f + ".xmp")
zeiten = {p: os.stat(p).st_mtime_ns for p in glob.glob(o + "/*.pp3") + glob.glob(o + "/*.xmp")}

def stand_der_anzeige(w):
    sterne = sum(1 for t in w.tiles if t['chk'].isChecked())
    w.btn_kf_filter.setChecked(True)
    gefiltert = sum(1 for t in w.tiles if not t['item'].isHidden())
    w.btn_kf_filter.setChecked(False)
    return sterne, gefiltert, w._kf_count

print("=== 1. Ordner mit Darktable geoeffnet ===")
w = pm.MainWindow(); w.txt_art_path.setText(RT_CLI); w.rb_raw.setChecked(True)
w.cmb_engine.setCurrentIndex(2); w._set_folder(o); w.cmb_engine.setCurrentIndex(2)
pe.set_engine('dt')
s, g, z = stand_der_anzeige(w)
pruef(s == g == z == 1, f"Darktable: Sterne {s}, Filter {g}, Zaehler {z} (erwartet 1)")

print("=== 2. Umschalten auf RawTherapee ===")
w.cmb_engine.setCurrentIndex(1)
s, g, z = stand_der_anzeige(w)
pruef(s == g == z == 3, f"RawTherapee: Sterne {s}, Filter {g}, Zaehler {z} (erwartet 3)")
pruef("3 bearbeitete Keyframes" in w.lbl_count.text(), f"Zaehler oben: {w.lbl_count.text()}")
pruef(any("Sterne in der Bildleiste sind angepasst" in z for z in w.txt_log._zeilen), "kein Hinweis im Protokoll")
pruef(all(t['chk'].isChecked() == (i in (5, 12, 18)) for i, t in enumerate(w.tiles)), "falsche Bilder markiert")
neu = {p: os.stat(p).st_mtime_ns for p in glob.glob(o + "/*.pp3") + glob.glob(o + "/*.xmp")}
pruef(neu == zeiten, "der Abgleich hat Dateien geschrieben")

print("=== 3. Zurueck auf Darktable, dann Stern von Hand ===")
w.cmb_engine.setCurrentIndex(2)
s, g, z = stand_der_anzeige(w)
pruef(s == g == z == 1, f"zurueck auf Darktable: Sterne {s}, Filter {g}, Zaehler {z}")
w.cmb_engine.setCurrentIndex(1)
w.tiles[5]['chk'].setChecked(False)     # von Hand entfernt: muss in die Datei
pruef(not pe.check_is_keyframe(d[5] + ".pp3"), "Stern von Hand entfernt, Profil sagt weiter Keyframe")
s, g, z = stand_der_anzeige(w)
pruef(s == g == z == 2, f"nach dem Entfernen: Sterne {s}, Filter {g}, Zaehler {z}")

print("=== 4. Neu einlesen: nichts vom vorigen Lader ===")
w.cmb_engine.setCurrentIndex(1)
n_vorher, kf_vorher = len(w.tiles), w._kf_count
alt = w.gallery_worker
nachzuegler = (alt.image_ready, alt.scan_done, alt.finished_loading)
w._refresh_preview()
n_neu = len(w.tiles)
# Was der alte Lader schon abgeschickt hatte, kommt jetzt noch an
from PyQt5 import QtGui
nachzuegler[0].emit(0, "alt.NEF", QtGui.QImage(), {'kf': True, 'luma': 0.2})
nachzuegler[1].emit(0, 99, [], [], 7)
pruef(len(w.tiles) == n_neu == n_vorher, f"Kacheln vom vorigen Lader angehaengt: {n_vorher} -> {n_neu} -> {len(w.tiles)}")
pruef(w._kf_count == kf_vorher and "2 bearbeitete Keyframes" in w.lbl_count.text(),
      f"Zaehler vom vorigen Lader ueberschrieben: {w._kf_count} / {w.lbl_count.text()}")
pruef(len(w.kf_marker) == kf_vorher, f"Keyframe-Linien doppelt: {len(w.kf_marker)} statt {kf_vorher}")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
