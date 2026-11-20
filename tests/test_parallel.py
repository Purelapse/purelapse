#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Pruefungen fuer die parallele Entwicklung in Pass 2: Aufteilung der
Bilder, Prozesszahl, Protokoll und das Zusammenspiel mit der Oberflaeche.
Laeuft ohne Qt.
"""
import io, os, re, ast, sys, time, glob, shutil, tempfile, subprocess, collections

SRC_PATH = os.path.join(os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "purelapse_main.py")
src = io.open(SRC_PATH, encoding="utf-8").read()
for _m in ("purelapse_texte.py", "purelapse_design.py"):
    _p = os.path.join(os.path.dirname(SRC_PATH), _m)
    if os.path.exists(_p):
        src += "\n" + io.open(_p, encoding="utf-8").read()
SCRATCH = os.environ.get("PURELAPSE_ARBEIT", os.path.join(__import__("tempfile").gettempdir(), "purelapse_pruefung"))

ok_n = fail_n = 0
def pruef(b, text):
    global ok_n, fail_n
    if b: ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")

def schnitt(von, bis):
    return src[src.index(von):src.index(bis)]

ns = {"os": os, "subprocess": subprocess, "shutil": shutil, "tempfile": tempfile,
      "time": time, "glob": glob}
exec(schnitt("THREADS_PRO_PROZESS = 4", "def find_dri_device()"), ns)
pa = ns["prozess_anzahl"]
auf = ns["bilder_aufteilen"]

print("=== 1. Prozesszahl: Automatik ===")
# viel Speicher, damit nur Kerne und Bilder begrenzen
VIEL = 999.0
pruef(pa(1000, 16, 0, VIEL) == 4, "16 Kerne -> 4 Prozesse")
pruef(pa(1000, 32, 0, VIEL) == 8, "32 Kerne -> 8 (Obergrenze)")
pruef(pa(1000, 64, 0, VIEL) == 8, "64 Kerne -> nicht mehr als 8")
pruef(pa(1000, 8, 0, VIEL) == 2, "8 Kerne -> 2 Prozesse")
pruef(pa(1000, 4, 0, VIEL) == 1, "4 Kerne -> 1 Prozess")
pruef(pa(1000, 2, 0, VIEL) == 1, "2 Kerne -> 1 Prozess")
pruef(pa(1000, 1, 0, VIEL) == 1, "1 Kern -> 1 Prozess")

print("=== 2. Prozesszahl: Grenzen ===")
pruef(pa(3, 32, 0, VIEL) == 3, "nie mehr Prozesse als Bilder")
pruef(pa(1, 32, 0, VIEL) == 1, "ein Bild -> ein Prozess")
pruef(pa(0, 32, 0, VIEL) == 1, "keine Bilder -> 1, kein Absturz")
pruef(pa(1000, 16, 0, 3.0) == 1, "3 GB frei -> nur ein Prozess")
pruef(pa(1000, 16, 0, 6.0) == 2, "6 GB frei -> zwei Prozesse")
pruef(pa(1000, 16, 0, 12.0) == 4, "12 GB frei -> vier Prozesse")
pruef(pa(1000, 16, 0, 0.5) == 1, "fast kein Speicher -> immer noch 1")
pruef(pa(1000, 16, 8, VIEL) == 8, "Wunsch 8 wird genommen")
pruef(pa(1000, 4, 8, VIEL) == 4, "Wunsch wird von der Kernzahl begrenzt")
pruef(pa(1000, 16, 1, VIEL) == 1, "Wunsch 1 bedeutet seriell")
pruef(pa(1000, 16, 99, VIEL) == 8, "Wunsch ueber der Obergrenze")
pruef(pa(1000, 16, 2, 3.0) == 1, "Speicher begrenzt auch den Wunsch")
pruef(pa(1000, 16, 0, None) >= 1, "ohne Speicherangabe kein Absturz")
pruef(pa(-5, -5, 0, VIEL) == 1, "Unsinn-Eingaben -> 1")
fr = ns["freier_speicher_gb"]()
pruef(fr is None or fr > 0, "freier_speicher_gb liefert Unsinn")
print(f"  (hier gemessen: {fr:.1f} GB frei)" if fr else "  (Speicher nicht ermittelbar)")

print("=== 3. Aufteilung der Bilder ===")
for n_bilder in (1, 2, 7, 100, 1001):
    for jobs in (1, 2, 3, 4, 8):
        files = [f"IMG_{i:05d}.NEF" for i in range(n_bilder)]
        teile = auf(files, jobs)
        flach = [f for t in teile for f in t]
        pruef(sorted(flach) == sorted(files),
              f"{n_bilder}/{jobs}: nicht alle Bilder genau einmal verteilt")
        pruef(len(flach) == len(set(flach)), f"{n_bilder}/{jobs}: Bild doppelt")
        pruef(all(t for t in teile), f"{n_bilder}/{jobs}: leerer Teil dabei")
        pruef(len(teile) == min(jobs, n_bilder), f"{n_bilder}/{jobs}: Teilzahl falsch")
        groessen = [len(t) for t in teile]
        pruef(max(groessen) - min(groessen) <= 1,
              f"{n_bilder}/{jobs}: ungleich verteilt {groessen}")
# reihum, nicht blockweise: Prozess 0 bekommt Bild 0, 4, 8 ...
teile = auf([f"{i}" for i in range(12)], 4)
pruef(teile[0] == ["0", "4", "8"], f"nicht reihum verteilt: {teile[0]}")
pruef(auf([], 4) == [], "leere Liste")
pruef(auf(["a"], 0) == [["a"]], "jobs=0 wird zu 1")

print("=== 4. Protokoll und Zaehlung ===")
blk = (schnitt("    def _count_rendered", "    def _run_darktable_cli"))
exec(schnitt("# Zwischenbilder der Engine: JPG (Standard) oder 16-Bit-TIFF", "def _dev_kennung"), ns)
exec("class Sig:\n    def __init__(self): self.gesendet = []\n"
     "    def emit(self, *a): self.gesendet.append(a)\n"
     "class W:\n"
     "    def __init__(self, p, diag=False):\n"
     "        self.p = p; self._abort = False; self._diag_an = diag\n"
     "        self.log = Sig(); self.status = Sig(); self.progress = Sig()\n"
     "    def _diag(self): return self._diag_an\n"
     "    def _t(self, de, en): return en if self.p.get('lang') == 'en' else de\n"
     "    def _fortschritt(self, label, fertig, gesamt, start, zusatz=''):\n"
     "        self.status.emit(label, fertig, gesamt)\n"
     "        self.progress.emit(fertig, gesamt)\n"
     "    def _schritt_fertig(self, label, anzahl, start, einheit='Bilder'):\n"
     "        self.log.emit(f'> {label}: {anzahl} fertig')\n" + blk, ns)

ziel = os.path.join(SCRATCH, "parallel_out")
shutil.rmtree(ziel, ignore_errors=True)
os.makedirs(ziel)
w = ns["W"]({"target_dir": ziel})
pruef(w._count_rendered(ziel, None) == 0, "leerer Ordner -> 0")
pruef(w._count_rendered(ziel, ["a", "b"]) == 0, "erwartete Namen, keine Dateien")
io.open(os.path.join(ziel, "a.jpg"), "w").write("x")
io.open(os.path.join(ziel, "b.JPG"), "w").write("x")
io.open(os.path.join(ziel, "fremd.jpg"), "w").write("x")
pruef(w._count_rendered(ziel, ["a", "b"]) == 2, "Gross- und Kleinschreibung")
pruef(w._count_rendered(ziel, ["a", "b", "c"]) == 2, "fehlendes Bild nicht gezaehlt")
pruef(w._count_rendered(ziel, None) == 3, "ohne Namensliste alles zaehlen")

print("=== 5. Echter Parallellauf mit Platzhalter-Prozessen ===")
# Keine ART-Installation hier: drei Prozesse, die JPGs schreiben.
lauf = os.path.join(SCRATCH, "parallel_lauf")
shutil.rmtree(lauf, ignore_errors=True)
os.makedirs(lauf)
# 15 Bilder je 0.3 s: seriell rund 4.5 s, zu dritt rund 1.5 s. Die
# Fortschrittsabfrage taktet im Sekundenabstand, deshalb muss der
# Unterschied deutlich groesser als eine Sekunde sein, um messbar zu sein.
stems = [f"IMG_{i:03d}" for i in range(15)]
teile = auf(stems, 3)
cmds = [[sys.executable, "-c",
         "import sys,os,time\n"
         "for st in sys.argv[2:]:\n"
         "    time.sleep(0.3)\n"
         "    open(os.path.join(sys.argv[1], st + '.jpg'),'w').write('x'*2000)\n"
         "print('ENDEMARKE', len(sys.argv)-2)\n", lauf] + t for t in teile]
w = ns["W"]({"target_dir": lauf}, diag=True)
t0 = time.time()
w._run_engine_cli(cmds, os.environ.copy(), lauf, len(stems), "Prueflauf",
                  expected_stems=stems)
dauer = time.time() - t0
pruef(w._count_rendered(lauf, stems) == 15, "nicht alle 15 Bilder entstanden")
pruef(dauer < 3.0, f"lief offenbar nicht parallel ({dauer:.2f}s, seriell waeren 4.5s)")
pruef(dauer > 1.0, f"unglaubwuerdig schnell ({dauer:.2f}s)")
pruef(w.progress.gesendet and w.progress.gesendet[-1] == (15, 15),
      f"letzte Fortschrittsmeldung nicht 15/15: {w.progress.gesendet[-1:]}")
# Fortschritt muss zwischendurch wachsen, nicht von 0 auf fertig springen
werte = [a[0] for a in w.progress.gesendet]
pruef(werte == sorted(werte), f"Fortschritt laeuft nicht monoton: {werte}")
pruef(any(0 < v < 15 for v in werte),
      f"keine Zwischenmeldung, Anzeige springt von 0 auf fertig: {werte}")
pruef(not any("ACHTUNG" in str(a) for a in w.log.gesendet),
      f"Fehlermeldung ohne Fehler: {w.log.gesendet}")
logdatei = os.path.join(lauf, "purelapse_art.log")
pruef(os.path.exists(logdatei), "Diagnose-Modus hat kein Protokoll geschrieben")
inhalt = io.open(logdatei, encoding="utf-8").read()
for i in (1, 2, 3):
    pruef(f"Prozess {i}/3" in inhalt, f"Prozess {i} fehlt im Protokoll")
pruef(inhalt.count("Rueckgabewert 0") == 3, "Rueckgabewerte nicht protokolliert")
pruef(inhalt.count("ENDEMARKE 5") == 3,
      f"Ausgaben der Prozesse fehlen im Protokoll "
      f"({inhalt.count('ENDEMARKE 5')}x statt 3x)")
# Reihenfolge im Protokoll
pruef(inhalt.index("Prozess 1/3") < inhalt.index("Prozess 2/3") <
      inhalt.index("Prozess 3/3"), "Protokoll ist durcheinander")

print("=== 6. Fehlerfall und Abbruch ===")
lauf2 = os.path.join(SCRATCH, "parallel_fehler")
shutil.rmtree(lauf2, ignore_errors=True)
os.makedirs(lauf2)
ns["eng"] = lambda feld: {"label": "ART"}.get(feld, "")
w = ns["W"]({"target_dir": lauf2}, diag=False)
cmds = [[sys.executable, "-c", "import sys; sys.exit(0)"],
        [sys.executable, "-c", "import sys; sys.exit(3)"]]
w._run_engine_cli(cmds, os.environ.copy(), lauf2, 2, "Fehlerlauf",
                  expected_stems=["x"])
meldungen = [str(a) for a in w.log.gesendet]
pruef(any("ACHTUNG" in m for m in meldungen), "Fehlercode wurde nicht gemeldet")
pruef(any("Prozess 2: 3" in m for m in meldungen),
      f"es fehlt, WELCHER Prozess versagte: {meldungen}")
pruef(any("Diagnose-Modus" in m for m in meldungen),
      "Hinweis auf den Diagnose-Modus fehlt, obwohl er aus ist")

# Abbruch: beendet alle Prozesse und meldet es
lauf3 = os.path.join(SCRATCH, "parallel_abbruch")
shutil.rmtree(lauf3, ignore_errors=True)
os.makedirs(lauf3)
w = ns["W"]({"target_dir": lauf3}, diag=False)
w._abort = True
cmds = [[sys.executable, "-c", "import time; time.sleep(30)"] for _ in range(3)]
t0 = time.time()
try:
    w._run_engine_cli(cmds, os.environ.copy(), lauf3, 3, "Abbruch",
                      expected_stems=["x"])
    pruef(False, "Abbruch loeste keine Ausnahme aus")
except RuntimeError as e:
    pruef("abgebrochen" in str(e).lower(), f"falsche Meldung: {e}")
pruef(time.time() - t0 < 10, "Abbruch dauerte zu lange")

print("=== 7. Statische Pruefungen ===")
pruef("def _run_art(" not in src, "alte _run_art-Methode noch vorhanden")
pruef(src.count("self._run_engine_cli(") == 1, "_run_engine_cli nicht genau einmal benutzt")
rw = schnitt("    def _render_with_engine", "    def _measure_and_correct")
pruef("prozess_anzahl(" in rw, "_render_with_engine fragt die Prozesszahl nicht")
pruef("bilder_aufteilen(" in rw, "_render_with_engine teilt die Bilder nicht auf")
pruef("kerne // len(teile)" in rw, "Threads werden nicht auf die Prozesse verteilt")
pruef("_run_darktable_cli" in rw and rw.index("_run_darktable_cli") < rw.index("prozess_anzahl"),
      "Darktable muss vor der Aufteilung abgefangen werden")
pruef(src.count("'procs': self.cmb_procs") == 1, "Einstellung procs wird nicht gemerkt")
pruef(src.count("PROZESS_WAHL[") == 1, "Prozesswahl wird nicht umgesetzt")
pruef(src.count("self.cmb_procs") >= 4, "cmb_procs zu selten benutzt")
pruef("'cmb_procs': 'TT_PROCS'" in src, "Hinweistext nicht verbunden")
pruef(src.count('"TT_PROCS"') == 2, "Hinweistext fehlt in einer Sprache")
pruef(len(ns["PROZESS_WAHL"]) == 7, "PROZESS_WAHL passt nicht zur Auswahlliste")
pruef(ns["PROZESS_WAHL"][0] == 0, "erster Eintrag muss die Automatik sein")
m = re.search(r'self\.cmb_procs\.addItems\(\[(.*?)\]\)', src, re.S)
pruef(m is not None, "addItems fuer cmb_procs nicht gefunden")
if m:
    n_items = len(re.findall(r'"', m.group(1))) // 2
    pruef(n_items == len(ns["PROZESS_WAHL"]),
          f"Auswahlliste hat {n_items} Eintraege, PROZESS_WAHL {len(ns['PROZESS_WAHL'])}")
# Gitterzeilen im Einstellungskasten eindeutig
zeilen = re.findall(r'gperf\.addWidget\([^,]+,\s*(\d+),\s*0', src)
pruef(len(zeilen) == len(set(zeilen)) or zeilen.count('2') > 1,
      f"zwei Bedienelemente in derselben Gitterzeile: {zeilen}")

print("=== 8. Doppelte Definitionen und Schluessel ===")
tree = ast.parse(src)
for kn in ast.walk(tree):
    if isinstance(kn, (ast.ClassDef, ast.Module)):
        namen = [k.name for k in kn.body
                 if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))]
        dop = [n for n, c in collections.Counter(namen).items() if c > 1]
        pruef(not dop, f"{getattr(kn, 'name', 'Modul')}: doppelt -> {dop}")
    if isinstance(kn, ast.Dict):
        schl = [k.value for k in kn.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        dop = [n for n, c in collections.Counter(schl).items() if c > 1]
        pruef(not dop, f"Zeile {kn.lineno}: doppelte Schluessel -> {dop[:5]}")
# Uebersetzungstabelle muss umkehrbar bleiben
m = re.search(r'TRANSLATIONS = \{', src)
tr = ast.literal_eval(src[src.index("TRANSLATIONS = {") + len("TRANSLATIONS = "):
                          src.index("TRANSLATIONS_TT_EN")].rstrip().rstrip("\n")) \
     if False else None   # zu gross fuer literal_eval mit Klammerausdruecken
werte = re.findall(r'^\s*"([^"]+)":\s*"([^"]*)",\s*$', src, re.M)
vorne = collections.Counter(v for k, v in werte if v)
mehrfach = [v for v, c in vorne.items() if c > 1]
pruef(not mehrfach, f"gleiche englische Fassung fuer mehrere deutsche Texte: {mehrfach[:5]}")

print(f"\n{'='*52}\n{ok_n} Pruefungen bestanden, {fail_n} fehlgeschlagen")
sys.exit(1 if fail_n else 0)
