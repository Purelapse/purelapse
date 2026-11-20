# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""D: eine Konfigurationsdatei, Uebernahme der alten Dateien, atomares Schreiben."""
import os, sys, json, stat, shutil, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
h = os.path.expanduser("~")
k = pe.konfig_pfad()
print("=== Uebernahme der alten Einzeldateien ===")
if os.path.exists(k): os.remove(k)
pe._KONFIG_ZWISCHEN['daten'] = None
alt = {".purelapse_last_path": "/bilder/zeitraffer\n", ".purelapse_lang": "en", ".purelapse_theme": "light",
       ".purelapse_settings.json": json.dumps({"fps": 3, "diag": True}),
       ".purelapse_queue.json": json.dumps([{"name": "a"}]),
       ".purelapse_bereiche.json": json.dumps({"/x": ["A.NEF", ""]}),
       ".purelapse_telegram.json": json.dumps({"an": True, "token": "T:1", "chat": "9"}),
       ".purelapse_rt_path": "/usr/bin/rawtherapee-cli", ".purelapse_rt_template": os.path.join(h, ".purelapse_rt_base.pp3"),
       ".purelapse_dt_path": "/usr/bin/darktable-cli"}
for n, inhalt in alt.items():
    open(os.path.join(h, n), "w", encoding="utf-8").write(inhalt)
open(os.path.join(h, ".purelapse_rt_base.pp3"), "w").write("[Version]\nAppVersion=5.9\n")
pe.set_engine('rt')
pruef(pm.get_lang() == "en" and pm.get_theme() == "light" and pm.get_last_path() == "/bilder/zeitraffer", "Grundwerte")
pruef(pm.load_queue() == [{"name": "a"}] and pm.lade_bereiche() == {"/x": ["A.NEF", ""]}, "Warteschlange/Bereiche")
pruef(pm.telegram_laden() == {'an': True, 'token': 'T:1', 'chat': '9'}, "Telegram")
pruef(pe.get_art_path() == "/usr/bin/rawtherapee-cli", "Engine-Pfad")
neu_basis = os.path.join(pe.daten_ordner(), "basis_rt.pp3")
pruef(pe.get_arp_template_path() == neu_basis and os.path.isfile(neu_basis), f"Basisprofil: {pe.get_arp_template_path()}")
pe.set_engine('dt'); pruef(pe.get_art_path() == "/usr/bin/darktable-cli", "Darktable-Pfad"); pe.set_engine('rt')
reste = [n for n in os.listdir(h) if n.startswith(".purelapse")]
pruef(reste == [], f"alte Dateien liegen noch: {reste}")
pruef(stat.S_IMODE(os.stat(k).st_mode) == 0o600, "Rechte")
pruef(os.path.dirname(k).endswith(os.path.join(".config", "purelapse")), k)
print("=== Lesen/Schreiben ===")
pm.save_theme("dark"); pm.save_lang("de"); pm.save_last_path("/neu")
d = json.load(open(k, encoding="utf-8"))
pruef(d["design"] == "dark" and d["sprache"] == "de" and d["letzter_ordner"] == "/neu" and d["einstellungen"]["fps"] == 3, f"{d}")
pe.save_art_path("/opt/rt"); pruef(json.load(open(k))["engines"]["rt"]["programm"] == "/opt/rt", "Engine-Pfad schreiben")
pruef(not [x for x in os.listdir(os.path.dirname(k)) if x != "purelapse.json"], "weitere Dateien im Konfigurationsordner")
# kaputte Datei: Programm startet mit Grundwerten
open(k, "w").write("{kaputt")
pe._KONFIG_ZWISCHEN['daten'] = None
pruef(pm.get_theme() == "dark" and pm.load_queue() == [], "kaputte Konfiguration")
pm.save_theme("light"); pruef(pm.get_theme() == "light", "nach kaputter Datei wieder schreibbar")
# Umlaute / Zeichen ausserhalb Latin-1 (Windows)
pm.save_last_path("/Bilder/Łódź Zeitraffer/ÄÖÜ")
pruef(pm.get_last_path() == "/Bilder/Łódź Zeitraffer/ÄÖÜ", "Sonderzeichen im Pfad")
# Fenster speichert Einstellungen in derselben Datei
w = pm.MainWindow(); w._save_settings()
pruef(isinstance(json.load(open(k, encoding="utf-8")).get("einstellungen"), dict), "Fenster-Einstellungen")
pruef([n for n in os.listdir(h) if n.startswith(".purelapse")] == [], "Fenster legt wieder Einzeldateien an")
# aufraeumen: die Pruefstand-Konfiguration ist allen Tests gemeinsam
os.remove(k); pe._KONFIG_ZWISCHEN['daten'] = None
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
