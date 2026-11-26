# -*- coding: utf-8 -*-
"""Vorbereitung fuer Windows - laeuft auf jedem System.

1. Dateilisten ohne Doppelte (Windows unterscheidet *.nef und *.NEF nicht).
2. Engines in den ueblichen Installationsordnern finden.
3. Lange Befehlszeilen auf mehrere Durchgaenge verteilen (Grenze 32767).
4. Encoder, die es auf dem System nicht gibt (VAAPI unter Windows), gesperrt.
5. Kein Konsolenfenster je Engine- oder FFmpeg-Aufruf."""
import os, sys, re, subprocess, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

print("=== 1. Dateilisten ===")
pruef(pm.ohne_doppelte(["/a/b.NEF", "/a/b.NEF", "/a/a.NEF"]) == ["/a/a.NEF", "/a/b.NEF"],
      "dieselbe Datei aus zwei Suchmustern muss einmal bleiben")
d = tempfile.mkdtemp(dir=ARBEIT)
for n in ("IMG_1.NEF", "IMG_2.nef", "IMG_3.jpg", "IMG_4.JPG", "notiz.txt"):
    open(os.path.join(d, n), "wb").close()
raws = [os.path.basename(f) for f in pm.find_raw_files(d)]
jpgs = [os.path.basename(f) for f in pm.find_jpg_files(d)]
pruef(sorted(raws) == ["IMG_1.NEF", "IMG_2.nef"], f"RAW: {raws}")
pruef(sorted(jpgs) == ["IMG_3.jpg", "IMG_4.JPG"], f"JPG: {jpgs}")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef(not re.search(r'glob\.glob\([^)]*"\*\.(jpg|JPG)"', src),
      "es wird noch irgendwo *.jpg und *.JPG getrennt gesucht")

print("=== 2. Engines finden ===")
wurzel = tempfile.mkdtemp(dir=ARBEIT)
for rel in ("PF/RawTherapee/5.9/rawtherapee-cli.exe", "PF/RawTherapee/5.10/rawtherapee-cli.exe",
            "PF/ART/ART-cli.exe", "LA/Programs/darktable/bin/darktable-cli.exe"):
    p = os.path.join(wurzel, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").close()
env = {'ProgramFiles': os.path.join(wurzel, "PF"), 'LOCALAPPDATA': os.path.join(wurzel, "LA")}
# Ohne Suchpfad: ein auf diesem Rechner installiertes RawTherapee wuerde
# sonst gefunden, bevor die nachgebauten Installationsordner dran sind.
gefunden = {k: pe.engine_suchen(k, env, nt=True, suchpfad=False) for k in ('art', 'rt', 'dt')}
pruef(gefunden['rt'].endswith(os.path.join("5.10", "rawtherapee-cli.exe")),
      f"RawTherapee: die neueste Version (5.10 vor 5.9): {gefunden['rt']}")
pruef(gefunden['art'].endswith("ART-cli.exe"), f"ART: {gefunden['art']}")
pruef(gefunden['dt'].endswith(os.path.join("bin", "darktable-cli.exe")), f"darktable: {gefunden['dt']}")
leer = {k: pe.engine_suchen(k, {'ProgramFiles': os.path.join(wurzel, "nichts")}, nt=True, suchpfad=False)
        for k in ('art', 'rt', 'dt')}
pruef(all(v == "" for v in leer.values()), f"Phantom-Fund: {leer}")
pruef(pe.engine_suchen('rt', env, nt=False) in ("", __import__("shutil").which("rawtherapee-cli") or ""),
      "unter Linux keine Windows-Ordner durchsuchen")

print("=== 3. Lange Befehlszeilen ===")
kopf = ["C:\\Program Files\\ART\\ART-cli.exe", "-S", "-Y", "-o", "C:\\Ziel", "-j100", "-c"]
bilder = [f"C:\\Users\\Name\\Bilder\\Zeitraffer 2026\\Serie\\IMG_{i:05d}.NEF" for i in range(3000)]
teile = pm.bilder_aufteilen(bilder, 3)
wellen = pm.befehls_wellen(kopf, teile, 30000)
laengen = [len(subprocess.list2cmdline(c)) for w in wellen for c in w]
pruef(len(wellen) > 1, f"3000 lange Pfade muessen geteilt werden: {len(wellen)} Durchgang")
pruef(max(laengen) <= 30000, f"eine Befehlszeile ist zu lang: {max(laengen)}")
alle = [b for w in wellen for c in w for b in c[len(kopf):]]
pruef(sorted(alle) == sorted(bilder), "Bilder gehen verloren oder doppelt")
pruef(all(c[:len(kopf)] == kopf for w in wellen for c in w), "Kopf fehlt in einer Zeile")
pruef(all(len(w) <= 3 for w in wellen), "mehr Prozesse gleichzeitig als eingestellt")
eine = pm.befehls_wellen(kopf, teile, None)
pruef(len(eine) == 1 and len(eine[0]) == 3, "ohne Grenze muss es bei einem Durchgang bleiben")
pruef(pm.befehls_wellen(kopf, pm.bilder_aufteilen(bilder[:50], 3), 30000) == pm.befehls_wellen(kopf, pm.bilder_aufteilen(bilder[:50], 3), None),
      "kurze Listen duerfen nicht geteilt werden")
pruef((pm.KOMMANDO_MAX is None) == (os.name != 'nt'), f"Grenze passt nicht zum System: {pm.KOMMANDO_MAX}")
rw = src[src.index("    def _render_with_engine"):src.index("    def _measure_and_correct")]
pruef("befehls_wellen(" in rw and "KOMMANDO_MAX" in rw, "Pass 2 teilt die Befehlszeile nicht")

print("=== 4. Encoder je System ===")
vaapi = [c for c in pm.VIDEO_CODECS if c.get('hw') == 'vaapi']
pruef(vaapi and not any(pm.codec_verfuegbar(c, nt=True) for c in vaapi), "VAAPI unter Windows angeboten")
pruef(all(pm.codec_verfuegbar(c, nt=False) for c in pm.VIDEO_CODECS), "unter Linux fehlt ein Encoder")
pruef(all(pm.codec_verfuegbar(c, nt=True) for c in pm.VIDEO_CODECS if c.get('hw') != 'vaapi'),
      "unter Windows fehlt ein Encoder, den es dort gibt")

print("=== 5. Ohne Konsolenfenster ===")
pruef((pe.OHNE_FENSTER == {}) == (os.name != 'nt'), f"OHNE_FENSTER: {pe.OHNE_FENSTER}")
for name in ("purelapse_main.py", "purelapse_engines.py"):
    text = open(os.path.join(PROJEKT, name), encoding="utf-8").read()
    for m in re.finditer(r"subprocess\.(Popen|run|call|check_output)\(", text):
        # bis zur schliessenden Klammer des Aufrufs
        tiefe, i = 0, m.end() - 1
        while True:
            if text[i] == "(":
                tiefe += 1
            elif text[i] == ")":
                tiefe -= 1
                if tiefe == 0:
                    break
            i += 1
        aufruf = text[m.start():i + 1]
        zeile = text.count("\n", 0, m.start()) + 1
        pruef("OHNE_FENSTER" in aufruf, f"{name}:{zeile} startet ohne OHNE_FENSTER: {aufruf[:60]}")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
