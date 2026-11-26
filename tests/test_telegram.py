# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Telegram-Benachrichtigung gegen einen nachgebauten Bot-Server."""
import os, sys, json, threading, stat
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import _basis
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
EINGANG = []
class Bot(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        daten = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode()).items()}
        _, token, methode = self.path.split("/", 2)
        if token != "botGUT:123":
            self.send_response(401); self.end_headers()
            self.wfile.write(json.dumps({'ok': False, 'description': 'Unauthorized'}).encode()); return
        if methode == "sendMessage":
            EINGANG.append(daten); antwort = {'ok': True, 'result': {}}
        else:
            antwort = {'ok': True, 'result': [{'message': {'chat': {'id': 4711, 'first_name': 'Testnutzer'}}}]}
        self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(antwort).encode())
    def log_message(self, *a): pass
srv = HTTPServer(("127.0.0.1", 0), Bot)
threading.Thread(target=srv.serve_forever, daemon=True).start()
pm.TELEGRAM_API = f"http://127.0.0.1:{srv.server_port}/bot{{token}}/{{methode}}"
pe.konfig_setzen('telegram', None)

print("=== Bausteine ===")
pruef(pm.telegram_senden("GUT:123", "4711", "hallo") [0] and EINGANG[-1] == {'chat_id': '4711', 'text': 'hallo', 'disable_web_page_preview': 'true'}, f"senden: {EINGANG[-1:]}")
ok, info = pm.telegram_senden("FALSCH:9", "4711", "x")
pruef(not ok and "Unauthorized" in info and "FALSCH" not in info, f"falscher Token: {info}")
pruef(pm.telegram_chat_finden("GUT:123") == ("4711", "Testnutzer"), "Chat-ID ermitteln")
pruef(not pm.telegram_senden("", "1", "x")[0] and not pm.telegram_senden("GUT:123", "", "x")[0], "fehlende Angaben")
alt = pm.TELEGRAM_API; pm.TELEGRAM_API = "http://127.0.0.1:1/bot{token}/{methode}"
ok, info = pm.telegram_senden("GEHEIM:1", "1", "x", timeout=3); pm.TELEGRAM_API = alt
pruef(not ok and "GEHEIM" not in info, f"Verbindungsfehler verraet den Token: {info}")
pm.telegram_speichern(True, " GUT:123 ", " 4711 ")
pruef(pm.telegram_laden() == {'an': True, 'token': 'GUT:123', 'chat': '4711'}, "speichern/laden")
# Unter Windows gibt es keine Unix-Rechte; dort schuetzt das Benutzerprofil
# (%APPDATA%) die Datei.
if os.name != 'nt':
    pruef(stat.S_IMODE(os.stat(pe.konfig_pfad()).st_mode) == 0o600, "Konfiguration ist fuer andere lesbar")

print("=== Im Fenster ===")
o = os.path.join(ARBEIT, "telegram"); d, _ = szene(o, n=60)
f = pm.MainWindow(); f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True); f._set_folder(o)
pruef(f.chk_telegram.isChecked() and f.txt_tg_chat.text() == "4711", "Einstellungen nicht geladen")
def warte():
    t = getattr(f, '_telegram_faden', None)
    if t: t.join(10)
n0 = len(EINGANG); f._go_step('smooth'); f._start(); warte()
pruef(len(EINGANG) == n0 + 1, f"nach Pass 1 keine Nachricht ({len(EINGANG) - n0})")
txt = EINGANG[-1]['text'] if EINGANG else ""
pruef("fertig" in txt and "telegram" in txt and "Pass 1, 60 Bilder" in txt and "Dauer" in txt, txt)
n0 = len(EINGANG); f._go_step('render'); f._start(); warte()
txt = EINGANG[-1]['text'] if len(EINGANG) > n0 else ""
pruef("Pass 2" in txt and "Restflackern" in txt and "Video rendern" in txt and ".mp4" in txt, txt)
print("   ---\n" + "\n".join("   " + z for z in txt.splitlines()) + "\n   ---")
# Fehler wird gemeldet, Abbruch durch den Benutzer nicht
def kaputt(self): raise RuntimeError("Probe-Fehler")
altlauf = pm.Worker._run_raw_pass2; pm.Worker._run_raw_pass2 = kaputt
n0 = len(EINGANG); f._start(); warte()
pruef(len(EINGANG) == n0 + 1 and "Fehler" in EINGANG[-1]['text'] and "Probe-Fehler" in EINGANG[-1]['text'], "Fehler nicht gemeldet")
def abbruch(self):
    f._vom_benutzer_abgebrochen = True
    raise RuntimeError("Abgebrochen")
pm.Worker._run_raw_pass2 = abbruch
alt_launch = f._launch
def launch_mit_abbruch(p, b):
    alt_launch(p, b)
n0 = len(EINGANG)
f._cancel_vorher = True
orig = f._launch
def gestartet(p, b):
    orig(p, b)
f._start(); warte()
pm.Worker._run_raw_pass2 = altlauf
pruef(len(EINGANG) == n0, "Abbruch durch den Benutzer wurde gemeldet")
# ausgeschaltet: keine Nachricht
f.chk_telegram.setChecked(False)
n0 = len(EINGANG); f._start(); warte()
pruef(len(EINGANG) == n0, "trotz ausgeschalteter Benachrichtigung gesendet")
# Schnellvorschau meldet nicht
f.chk_telegram.setChecked(True); n0 = len(EINGANG); f._start_schnell(); warte()
pruef(len(EINGANG) == n0, "Schnellvorschau wurde gemeldet")
srv.shutdown()
print(f"{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
