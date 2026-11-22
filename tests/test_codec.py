#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Pruefungen fuer die Codec-Tabelle, den Encoder-Selbsttest und den
Ausgabepfad. Laeuft ohne Qt: die betroffenen Codestuecke werden aus
purelapse_main.py herausgeschnitten und einzeln ausgefuehrt.
"""
import io, os, re, ast, sys, shutil, tempfile, subprocess, collections
import numpy as np

SRC_PATH = os.path.join(os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "purelapse_main.py")
src = io.open(SRC_PATH, encoding="utf-8").read()
for _m in ("purelapse_texte.py", "purelapse_design.py"):
    _p = os.path.join(os.path.dirname(SRC_PATH), _m)
    if os.path.exists(_p):
        src += "\n" + io.open(_p, encoding="utf-8").read()
SCRATCH = os.environ.get("PURELAPSE_ARBEIT", os.path.join(__import__("tempfile").gettempdir(), "purelapse_pruefung"))

ok_n = fail_n = 0
def pruef(bedingung, text):
    global ok_n, fail_n
    if bedingung:
        ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")

def schnitt(von, bis):
    return src[src.index(von):src.index(bis)]

# ---------------------------------------------------------------- Umgebung
ns = {"os": os, "subprocess": subprocess, "shutil": shutil, "tempfile": tempfile,
      "FFMPEG_BIN": shutil.which("ffmpeg") or "ffmpeg"}
ns["sys"] = sys
exec(schnitt("def ffmpeg_kandidaten():", "FFMPEG_BIN = _find_ffmpeg()"), ns)
exec(schnitt("def find_dri_device()", "def load_preview_image("), ns)
VC = ns["VIDEO_CODECS"]

print("=== 1. Tabelle ===")
pruef(len(VC) == 11, "elf Codecs erwartet")
pruef([c["enc"] for c in VC[:5]] ==
      ["libx264", "h264_nvenc", "libx265", "hevc_nvenc", "prores_ks"],
      "Reihenfolge der Indizes 0-4 darf sich nie aendern (gespeicherte Profile)")
for i, c in enumerate(VC):
    for feld in ("label", "enc", "args", "pix", "pre", "vf", "ext", "mult", "hw", "fb"):
        pruef(feld in c, f"Codec {i}: Feld {feld} fehlt")
    pruef(c["ext"] in (".mp4", ".mov"), f"Codec {i}: unbekannter Container")
    pruef(VC[c["fb"]]["hw"] is None, f"Codec {i}: Rueckfall ist kein CPU-Codec")
    pruef(c["mult"] > 0, f"Codec {i}: Groessenfaktor nicht positiv")
pruef(len({c["label"] for c in VC}) == len(VC), "Beschriftungen nicht eindeutig")
pruef(VC[4]["ext"] == ".mov", "ProRes muss in .mov landen, MP4 kann es nicht")
pruef(all(c["ext"] == ".mp4" for i, c in enumerate(VC) if i != 4),
      "ausser ProRes gehoert alles in .mp4")
pruef(ns["codec_def"](99)["enc"] == "libx264", "unbekannter Index -> libx264")
pruef(ns["codec_def"](None)["enc"] == "libx264", "None -> libx264")
pruef(ns["codec_def"](-1)["enc"] == "libx264", "negativer Index -> libx264")
pruef("@DRI@" not in ns["codec_pre_args"](VC[7]), "Platzhalter nicht ersetzt")
pruef(ns["codec_pre_args"](VC[7])[1].startswith("/dev/dri/"), "kein Render-Knoten")
pruef(ns["codec_pre_args"](VC[0]) == [], "CPU-Codec braucht keine pre-Argumente")

print("=== 1b. FFmpeg-Auswahl ===")
kand = ns["ffmpeg_kandidaten"]()
pruef(kand and (shutil.which("ffmpeg") is None or kand[0] == shutil.which("ffmpeg")), f"System-FFmpeg nicht zuerst: {kand}")
# ein untaugliches FFmpeg vorn: der Test faellt auf ein taugliches zurueck
ns["FFMPEG_BIN"] = "/gibt/es/nicht/ffmpeg"
ok_, grund_ = ns["probe_encoder"](0)
pruef(ok_ and ns["FFMPEG_BIN"] == kand[0], f"kein Rueckfall auf ein taugliches FFmpeg: {ok_} {ns['FFMPEG_BIN']}")
print("=== 2. Selbsttest probe_encoder ===")
for i, c in enumerate(VC):
    erg, grund = ns["probe_encoder"](i)
    pruef(isinstance(erg, bool) and isinstance(grund, str),
          f"Codec {i}: Rueckgabe hat die falsche Form")
    pruef(erg or grund.strip() != "", f"Codec {i}: Fehlschlag ohne Begruendung")
    if c["hw"] is None:
        pruef(erg, f"{c['label']} muss hier laufen")
    print(f"  [{i}] {c['label']:<34} {'OK' if erg else 'nein: ' + grund.splitlines()[0][:52]}")
erg, grund = ns["probe_encoder"](4711)
pruef(erg, "Unsinn-Index muss auf libx264 pruefen und bestehen")

print("=== 3. FFmpeg-Befehl ===")
blk = schnitt("    def _build_ffmpeg_cmd", "    def _get_output_video_path")
exec("class W:\n    def __init__(self, p): self.p = p\n" + blk, ns)
for i, c in enumerate(VC):
    cmd = ns["W"]({"fps": "25", "qual_idx": 1, "codec_idx": i})._build_ffmpeg_cmd(
        1920, 1080, "/tmp/x" + c["ext"])
    pruef(cmd.count("-c:v") == 1, f"Codec {i}: -c:v nicht genau einmal")
    pruef(cmd[cmd.index("-c:v") + 1] == c["enc"], f"Codec {i}: falscher Encoder")
    pruef(cmd.index("-i") < cmd.index("-c:v"), f"Codec {i}: -i muss vor -c:v stehen")
    for a in c["pre"]:
        if a != "@DRI@":
            pruef(a in cmd and cmd.index(a) < cmd.index("-i"),
                  f"Codec {i}: {a} muss vor -i stehen")
    if c["vf"]:
        pruef(cmd.index("-vf") > cmd.index("-i"), f"Codec {i}: -vf gehoert nach -i")
        pruef(cmd.index("-vf") < cmd.index("-c:v"), f"Codec {i}: -vf gehoert vor -c:v")
    # bgr24 beschreibt die Eingabe, c['pix'] die Ausgabe
    pf = [k for k, a in enumerate(cmd) if a == "-pix_fmt"]
    pruef(cmd[pf[0] + 1] == "bgr24", f"Codec {i}: Eingabeformat nicht bgr24")
    pruef(len(pf) == (2 if c["pix"] else 1), f"Codec {i}: Anzahl -pix_fmt falsch")
    if c["pix"]:
        pruef(cmd[pf[1] + 1] == c["pix"], f"Codec {i}: Ausgabeformat falsch")
# Qualitaetsstufen durchlaufen
for q, crf in enumerate(["16", "20", "23", "28"]):
    cmd = ns["W"]({"fps": "30", "qual_idx": q, "codec_idx": 0})._build_ffmpeg_cmd(
        1920, 1080, "/tmp/x.mp4")
    pruef(crf in cmd, f"Qualitaetsstufe {q}: CRF {crf} fehlt im Befehl")

print("=== 4. Echter Durchlauf mit Bilddaten ===")
rng = np.random.default_rng(7)
bilder = [rng.integers(0, 255, (360, 640, 3), dtype=np.uint8).tobytes() for _ in range(8)]
for i in [k for k, c in enumerate(VC) if c["hw"] is None]:
    out = os.path.join(SCRATCH, f"prueflauf_{i}{VC[i]['ext']}")
    cmd = ns["W"]({"fps": "25", "qual_idx": 2, "codec_idx": i})._build_ffmpeg_cmd(640, 360, out)
    errf = tempfile.TemporaryFile()
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=errf)
    gebrochen = False
    try:
        for b in bilder:
            pr.stdin.write(b)
        pr.stdin.close()
    except BrokenPipeError:
        gebrochen = True
    pr.wait()
    errf.seek(0)
    meldung = errf.read().decode(errors="ignore")
    pruef(not gebrochen, f"{VC[i]['label']}: Pipe brach ab -> {meldung[:120]}")
    pruef(pr.returncode == 0, f"{VC[i]['label']}: Fehlercode {pr.returncode}")
    pruef(os.path.exists(out) and os.path.getsize(out) > 1000,
          f"{VC[i]['label']}: keine brauchbare Datei")
    q = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-count_frames", "-show_entries",
                        "stream=nb_read_frames,codec_name", "-of", "csv=p=0", out],
                       capture_output=True, text=True).stdout.strip()
    pruef(q.endswith("8"), f"{VC[i]['label']}: nicht 8 Bilder im Video ({q})")
    print(f"  [{i}] {VC[i]['label']:<24} {os.path.getsize(out):>9} Bytes  {q}")

print("=== 5. Ausgabepfad ===")
blk = schnitt("    def _get_output_video_path", "    def _remove_satellites")
exec("PL_ORDNER = 'Purelapse'\n" + schnitt("def pl_ordner(", "def pl_datei("), ns)
exec("class S:\n    def emit(self, *a): pass\n"
     "class W2:\n    output_ready = S()\n"
     "    def __init__(self, p): self.p = p\n" + blk, ns)
basis = os.path.join(SCRATCH, "pfadtest")
shutil.rmtree(basis, ignore_errors=True)
os.makedirs(os.path.join(basis, "Nacht01"))
grund = dict(target_dir=os.path.join(basis, "Nacht01"), out_dir_mode=0,
             custom_out_dir="", res_name="2160p", fps="25", versioning=False)
for i, c in enumerate(VC):
    p = dict(grund, codec_idx=i)
    pfad = ns["W2"](p)._get_output_video_path()
    pruef(pfad.endswith(c["ext"]), f"Codec {i}: Pfad endet nicht auf {c['ext']}")
    pruef("Nacht01_Purelapse_2160p_25fps" in pfad, f"Codec {i}: Name falsch gebildet")
    pruef(os.path.dirname(pfad) == os.path.join(basis, "Nacht01", "Purelapse")
          and os.path.isdir(os.path.dirname(pfad)), f"Codec {i}: Video nicht im Purelapse-Ordner: {pfad}")
# Versionierung behaelt die Endung
p = dict(grund, codec_idx=4, versioning=True)
pfad1 = ns["W2"](p)._get_output_video_path()
pruef(pfad1.endswith("_v1.mov"), f"Versionierung verliert die Endung: {pfad1}")
io.open(pfad1, "w").write("x")
pfad2 = ns["W2"](p)._get_output_video_path()
pruef(pfad2.endswith("_v2.mov"), f"zweite Version falsch: {pfad2}")
p = dict(grund, codec_idx=0, versioning=False, name_suffix="_Original")
pruef(ns["W2"](p)._get_output_video_path().endswith("_Original.mp4"), "Suffix verloren")

print("=== 6. Statische Pruefungen der Datei ===")
pruef("stderr=subprocess.PIPE" not in schnitt("    def _run_plain", "    def _run_compare"),
      "Rohfassung schreibt stderr noch in eine Pipe")
pruef(src.count("ffmpeg_proc.stderr") == 0,
      "es wird noch direkt aus der FFmpeg-Pipe gelesen")
pruef(src.count("ffmpeg_proc = self._start_encoder(") == 3,
      "nicht alle drei Encoder-Starts gehen ueber _start_encoder")
pruef(src.count("self._finish_encoder(ffmpeg_proc)") == 3,
      "nicht alle drei Encoder-Abschluesse pruefen den Fehlercode")
pruef(src.count("ffmpeg_proc.wait()") == 0, "roher wait() ohne Fehlerpruefung uebrig")
# Vorabtest steht vor jeder Arbeit in _launch
launch = schnitt("    def _launch(self, params, banner):", "    def _start_plain")
pruef(launch.index("_preflight_codec") < launch.index("self._log_leeren()"),
      "_preflight_codec muss vor allem anderen in _launch stehen")
pruef(launch.index("_preflight_codec") < launch.index("Worker(params)"),
      "_preflight_codec muss vor dem Start des Workers stehen")
pruef("self.cmb_engine.setEnabled(False)" in launch,
      "Engine-Auswahl wird waehrend eines Laufs nicht gesperrt")
pruef("self.cmb_engine.setEnabled(True)" in
      schnitt("    def _enable_buttons", "    def _queue_refresh"),
      "Engine-Auswahl wird nach dem Lauf nicht wieder freigegeben")
pruef('VERSION = "2.44.0-beta"' in src, "Versionsnummer nicht erhoeht")
pruef(src.count("codec_idx == 0") == 0 and src.count("crf_vals[qual_idx]") == 0,
      "alte if/elif-Codecauswahl noch vorhanden")

print("=== 7. Doppelte Definitionen und Schluessel ===")
tree = ast.parse(src)
for knoten in ast.walk(tree):
    if isinstance(knoten, (ast.ClassDef, ast.Module)):
        namen = [k.name for k in knoten.body if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))]
        doppelt = [n for n, c in collections.Counter(namen).items() if c > 1]
        wo = getattr(knoten, "name", "Modul")
        pruef(not doppelt, f"{wo}: doppelt definiert -> {doppelt}")
    if isinstance(knoten, ast.Dict):
        schl = [k.value for k in knoten.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        doppelt = [n for n, c in collections.Counter(schl).items() if c > 1]
        pruef(not doppelt, f"Zeile {knoten.lineno}: doppelte Schluessel -> {doppelt[:5]}")

print("=== 8. Beschriftungen und Uebersetzung ===")
labels = [c["label"] for c in VC]
pruef(src.count("self.cmb_codec.addItems([c['label'] for c in VIDEO_CODECS])") == 1,
      "Auswahlliste wird nicht aus der Tabelle gefuellt")
# Jede Beschriftung, die uebersetzt wird, muss in TRANSLATIONS stehen
uebersetzt = re.findall(r'^\s*"([^"]+)":\s*"[^"]*",\s*$', src, re.M)
for lab in labels:
    if lab in uebersetzt:
        print(f"  uebersetzt: {lab}")
pruef(src.count('self.cmb_codec.currentIndexChanged.connect(self._on_codec_changed)') == 1,
      "_on_codec_changed ist nicht verbunden")
pruef("def _on_codec_changed" in src, "_on_codec_changed fehlt")
pruef("def _preflight_codec" in src, "_preflight_codec fehlt")
pruef("def _codec_available" in src, "_codec_available fehlt")

print(f"\n{'='*52}\n{ok_n} Pruefungen bestanden, {fail_n} fehlgeschlagen")
sys.exit(1 if fail_n else 0)
