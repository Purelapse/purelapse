# -*- coding: utf-8 -*-
"""Alles, was Purelapse erzeugt, liegt im Unterordner "Purelapse" des
Bilderordners; die Begleitdateien der Engines bleiben neben den Bildern.
Aeltere Ordner werden beim Oeffnen umgeraeumt."""
import os, sys, glob, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import _basis
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

def lose(ordner):
    """Was ausser Bildern und Begleitdateien lose im Bilderordner liegt."""
    rest = []
    for n in os.listdir(ordner):
        if n == "Purelapse" or pm.is_raw_file(n) or n.lower().endswith((".jpg", ".jpeg")):
            continue
        if n.lower().endswith((".pp3", ".arp", ".xmp")):
            continue
        rest.append(n)
    return sorted(rest)

print("=== 1. RAW: Pass 1 und Pass 2 mit Diagnose ===")
pe.set_engine('rt')
o = os.path.join(ARBEIT, "ordner_raw"); d, _ = szene(o, n=24)
os.makedirs(pl(o), exist_ok=True)
open(pl(o, pm.CALIB_DB), "w").write(json.dumps({os.path.basename(f): 0.5 for f in d}))
e1 = lauf(parameter(o, d, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI, diag=True))
pruef(not os.path.exists(pl(o, pm.CALIB_DB)), "Pass 1 laesst die alte Nachkalibrierung stehen")
pruef(any("Nachkalibrierung verworfen" in z for z in e1.log), "Verwerfen nicht im Protokoll")
e2 = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=RT_CLI, diag=True))
pruef(e1.ok() and e2.ok(), f"Lauf: {e1.fehler[:1]} {e2.fehler[:1]}")
pruef(lose(o) == [], f"lose im Bilderordner: {lose(o)}")
pruef(len(glob.glob(o + "/*.pp3")) == 24, "Begleitdateien liegen nicht neben den RAWs")
for name in (pm.DEFLICKER_DB, pm.RESULT_DB, "purelapse_pass1.csv", "purelapse_pass2.csv", "purelapse_art.log"):
    pruef(os.path.exists(pl(o, name)), f"{name} fehlt im Purelapse-Ordner")
pruef(len(glob.glob(pl(o, "Deflickered_JPG", "*.jpg"))) == 24, "entwickelte Bilder nicht in Purelapse/Deflickered_JPG")
v = glob.glob(pl(o, "*_Purelapse_*.mp4"))
pruef(len(v) == 1, f"Video nicht im Purelapse-Ordner: {os.listdir(pl(o))}")
pruef(e2.ausgabe and os.path.abspath(e2.ausgabe[-1]) == os.path.abspath(pl(o)),
      f"'Ordner oeffnen' zeigt nicht auf den Purelapse-Ordner: {e2.ausgabe[-1:]}")
# Pass 2 nochmals: ueberspringt die schon entwickelten Bilder, findet die Messwerte
e3 = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=RT_CLI, versioning=True))
pruef(e3.ok() and len(glob.glob(pl(o, "*_Purelapse_*.mp4"))) == 2, f"zweiter Pass 2: {e3.fehler[:1]}")

print("=== 2. Ohne Diagnose keine Protokolle ===")
o2 = os.path.join(ARBEIT, "ordner_jpg"); d2, _ = szene(o2, n=24, art="jpg")
e = lauf(parameter(o2, d2))
pruef(e.ok() and lose(o2) == [], f"JPG: lose {lose(o2)} {e.fehler[:1]}")
pruef(not glob.glob(pl(o2, "*.csv")) and not glob.glob(pl(o2, "*.log")), "Protokolle ohne Diagnose-Modus")
pruef(len(glob.glob(pl(o2, "*_Purelapse_*.mp4"))) == 1, "JPG-Video nicht im Purelapse-Ordner")

print("=== 3. Andere Speicherorte bleiben moeglich ===")
o3 = os.path.join(ARBEIT, "ordner_eigen"); d3, _ = szene(o3, n=24, art="jpg")
ziel = os.path.join(ARBEIT, "ordner_eigen_ziel"); shutil.rmtree(ziel, ignore_errors=True); os.makedirs(ziel)
e = lauf(parameter(o3, d3, out_dir_mode=3, custom_out_dir=ziel))
pruef(e.ok() and len(glob.glob(ziel + "/*.mp4")) == 1, "eigener Ordner wird nicht benutzt")

print("=== 4. Aeltere Ordner umraeumen ===")
o4 = os.path.join(ARBEIT, "ordner_alt"); d4, _ = szene(o4, n=24)
for name, inhalt in ((pm.DEFLICKER_DB, "{}"), (pm.CALIB_DB, "{}"), (pm.RESULT_DB, "{}"),
                     ("purelapse_pass1.csv", "a"), ("purelapse_art.log", "x"),
                     ("ordner_alt_Purelapse_4K_25fps_v1.mp4", "v"),
                     ("ordner_alt_Purelapse_4K_25fps_Original_v1.mov", "v"),
                     ("urlaub.mp4", "fremd"), ("notizen.txt", "fremd")):
    open(os.path.join(o4, name), "w").write(inhalt)
os.makedirs(os.path.join(o4, "Deflickered_JPG")); open(os.path.join(o4, "Deflickered_JPG", "IMG_0001.jpg"), "w").write("j")
open(os.path.join(o4, "IMG_0001.NEF.pp3"), "w").write("[Version]\n")
verschoben, geblieben = pm.alte_ablage_umraeumen(o4)
pruef(len(verschoben) == 8 and not geblieben, f"umgeraeumt: {verschoben} / {geblieben}")
pruef(sorted(lose(o4)) == ["notizen.txt", "urlaub.mp4"], f"fremde Dateien angefasst oder Reste: {lose(o4)}")
pruef(os.path.exists(o4 + "/IMG_0001.NEF.pp3"), "Begleitdatei verschoben")
pruef(os.path.exists(pl(o4, "Deflickered_JPG", "IMG_0001.jpg")), "Deflickered_JPG nicht mitgenommen")
pruef(open(pl(o4, pm.DEFLICKER_DB)).read() == "{}", "Inhalt beim Verschieben veraendert")
pruef(pm.alte_ablage_umraeumen(o4) == ([], []), "zweites Umraeumen tut noch etwas")
# Gleichnamige Datei im Purelapse-Ordner: nichts ueberschreiben
open(os.path.join(o4, pm.CALIB_DB), "w").write("alt")
open(pl(o4, pm.CALIB_DB), "w").write("neu")
verschoben, geblieben = pm.alte_ablage_umraeumen(o4)
pruef(geblieben == [pm.CALIB_DB] and open(pl(o4, pm.CALIB_DB)).read() == "neu",
      "vorhandene Datei im Purelapse-Ordner ueberschrieben")
os.remove(os.path.join(o4, pm.CALIB_DB))
pruef(pm.alte_ablage_umraeumen(os.path.join(ARBEIT, "gibt_es_nicht")) == ([], []), "fehlender Ordner")

print("=== 5. Im Fenster: Umraeumen beim Oeffnen, Startdialog, Schritte ===")
o5 = os.path.join(ARBEIT, "ordner_fenster"); d5, _ = szene(o5, n=56)
open(os.path.join(o5, pm.DEFLICKER_DB), "w").write(json.dumps({os.path.basename(f): 0.0 for f in d5}))
open(os.path.join(o5, "ordner_fenster_Purelapse_4K_25fps_v1.mp4"), "w").write("v")
stand_alt = pm.workflow_stand(o5)
pruef("Pass 1 erledigt" in stand_alt and "1 Video" in stand_alt, f"Startdialog vor dem Umraeumen: {stand_alt}")
f = pm.MainWindow()
f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True)
f._set_folder(o5)
pruef(os.path.exists(pl(o5, pm.DEFLICKER_DB)) and lose(o5) == [], f"beim Oeffnen nicht umgeraeumt: {lose(o5)}")
pruef(any("2 Dateien" in z and "Purelapse" in z for z in f.txt_log._zeilen), "Umraeumen nicht im Protokoll")
stand_neu = pm.workflow_stand(o5)
pruef("Pass 1 erledigt" in stand_neu and "1 Video" in stand_neu, f"Startdialog nach dem Umraeumen: {stand_neu}")
pruef(f._step_done('smooth'), "Schritt 'Helligkeit glaetten' gilt nicht als erledigt")
pruef(f.cmb_export_dir.itemText(0).startswith("1. Purelapse-Ordner"), f"Speicherort: {f.cmb_export_dir.itemText(0)}")

print("=== 5b. Ordner oeffnen folgt dem Ordnerwechsel ===")
f.cmb_export_dir.setCurrentIndex(0)
f._on_output_ready(pl(o5))
pruef(f._current_output_dir() == pl(o5), f"nach dem Lauf: {f._current_output_dir()}")
o5b = os.path.join(ARBEIT, "ordner_wechsel"); szene(o5b, n=56)
f._set_folder(o5b)
pruef(f._current_output_dir() == o5b, f"nach dem Wechsel noch der alte Ordner: {f._current_output_dir()}")
os.makedirs(pl(o5b), exist_ok=True)
pruef(f._current_output_dir() == pl(o5b), f"Purelapse-Ordner nicht bevorzugt: {f._current_output_dir()}")
f._set_folder(o5)
pruef(f._current_output_dir() == pl(o5), f"zurueck im ersten Ordner: {f._current_output_dir()}")

print("=== 6. Zuruecksetzen raeumt leere Ordner weg ===")
o6 = os.path.join(ARBEIT, "ordner_reset"); d6, _ = szene(o6, n=24)
os.makedirs(pl(o6, "Deflickered_JPG"))
open(pl(o6, "Deflickered_JPG", "IMG_0000.jpg"), "w").write("j")
open(pl(o6, pm.DEFLICKER_DB), "w").write("{}")
# Den Dialog selbst baut der Pruefstand nicht; Suche und Loeschen schon.
import types
class Haken:
    def __init__(self, an): self.an = an
    def isChecked(self): return self.an
dlg = types.SimpleNamespace(target_dir=o6, deleted=0, _de=True,
                            accept=lambda: None, reject=lambda: None)
dlg._groups = pm.ResetDialog._scan(dlg)
pruef(len(dlg._groups['output']) == 1 and len(dlg._groups['state']) == 1, f"Zuruecksetzen findet: {dlg._groups}")
dlg.boxes = {k: Haken(k in ('output', 'state')) for k in dlg._groups}
pm.ResetDialog._confirm(dlg)
pruef(dlg.deleted == 2 and not os.path.exists(pl(o6)), f"Zuruecksetzen: {dlg.deleted} geloescht, Ordner da: {os.path.exists(pl(o6))}")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
