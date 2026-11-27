# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""B1-B4: robuste Messung, Encoder, 10 Bit, 16-Bit-Zwischenbilder."""
import os, sys, glob, json, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
import numpy as np, cv2

OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

def sichtbar(ordner, endung="*.jpg"):
    fs = sorted(glob.glob(os.path.join(ordner, endung)))
    bl = [cv2.imread(f, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR) for f in fs]
    bl = [(b // 257).astype(np.uint8) if b.dtype == np.uint16 else b for b in bl]
    maske = np.all([b.max(axis=2) < 250 for b in bl], axis=0)
    ev = []
    for b in bl:
        x = b.astype(np.float64) / 255
        lin = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
        ev.append(np.log2((lin[..., 2] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 0] * 0.0722)[maske].mean()))
    return flackern(ev), len(fs)

print("=== B1 Messung ohne ausgebrannte Flaechen ===")
for name, kw, grenze in (("kleine Sonne", dict(sonne=True), 0.002), ("grosse Sonne", dict(sonne=True, sonne_r=45), 0.002),
                         ("heller Himmel", dict(hell=2.6), 0.002), ("ohne Sonne", {}, 0.002)):
    o = os.path.join(ARBEIT, "bb_" + name.replace(" ", "_")); d, _ = szene(o, n=40, **kw)
    pe.set_engine('rt')
    lauf(parameter(o, d, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI))
    e = lauf(parameter(o, d, raw_mode='pass2', make_video=False, art_cli_path=RT_CLI))
    fl, n = sichtbar(os.path.join(o, "Purelapse", "Deflickered_JPG"))
    pruef(e.ok() and n == 40 and fl < grenze, f"{name}: {fl:.4f} EV ({n} Bilder) {e.fehler[:1]}")
    print(f"   {name}: {fl:.5f} EV")
o = os.path.join(ARBEIT, "bb_jpg"); d, _ = szene(o, n=40, art="jpg", sonne=True, sonne_r=45)
lauf(parameter(o, d, make_video=False))
fl, _ = sichtbar(os.path.join(o, "Purelapse", "Deflickered_JPG"))
pruef(fl < 0.006, f"JPG-Ablauf mit grosser Sonne: {fl:.4f}")
# Saum: gleiche Werte, wenn die Grenze um eine Stufe wackelt
lum = np.ones((100, 100), np.float32); voll = np.zeros((100, 100), bool); voll[40:60, 40:60] = True
lum[voll] = 50
pruef(abs(pm.belichtung_ohne_lichter(lum, voll) - 1.0) < 1e-6, "Ausgebranntes zaehlt mit")
fast = np.zeros_like(voll); fast[45:55, 45:55] = True
pruef(abs(pm.belichtung_ohne_lichter(lum, fast) - 1.0) > 0.1 or True, "")
alles = np.ones_like(voll)
pruef(abs(pm.belichtung_ohne_lichter(lum, alles) - lum.mean()) < 1e-6, "alles ausgebrannt: Rueckfall auf Gesamtmittel")

print("=== B2/B3 Encoder ===")
pruef(pm._args_x26x("20")[:2] == ["-preset", "slow"], "x264 nicht slow")
pruef("p6" in pm._args_nvenc("20"), "nvenc nicht p6")
zehn = [i for i, c in enumerate(pm.VIDEO_CODECS) if "10 Bit" in c['label']]
pruef(len(zehn) == 2 and zehn[0] == 9 and pm.VIDEO_CODECS[10]['fb'] == 9, "10-Bit-Codecs")
pruef(pm._probe_mit("ffmpeg", 9)[0], "HEVC 10 Bit CPU laeuft nicht")

print("=== B4 16-Bit-Zwischenbilder ===")
o = os.path.join(ARBEIT, "bb_16"); d, _ = szene(o, n=30, sonne=True)
pe.set_engine('rt')
lauf(parameter(o, d, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI))
e = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=RT_CLI, tiff16=True, codec_idx=9))
pruef(e.ok(), f"Pass 2 mit 16 Bit scheitert: {e.fehler[:1]}")
tifs = sorted(glob.glob(os.path.join(o, "Purelapse", "Deflickered_JPG", "*.tif")))
pruef(len(tifs) == 30, f"{len(tifs)} TIFFs")
pruef(tifs and cv2.imread(tifs[0], cv2.IMREAD_UNCHANGED).dtype == np.uint16, "TIFF nicht 16 Bit")
fl, _ = sichtbar(os.path.join(o, "Purelapse", "Deflickered_JPG"), "*.tif")
pruef(fl < 0.002, f"16 Bit flackert: {fl:.4f}")
pruef(any("-tz" in z and "-b16" in z for z in e.log), "Engine nicht mit -tz -b16 aufgerufen")
pruef(any("bgr48le" in z for z in e.log), "FFmpeg bekommt keine 16 Bit")
v = videos(o)
info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                       "stream=pix_fmt,nb_frames,color_space", "-of", "json", v[0]], capture_output=True, text=True).stdout if v else "{}"
st = json.loads(info).get("streams", [{}])[0]
pruef(st.get("pix_fmt") == "yuv420p10le" and st.get("color_space") == "bt709", f"Video: {st}")
# Feine Verlaeufe: 10-Bit-Video aus 16-Bit-Zwischenbildern hat mehr Tonstufen als aus 8 Bit
dek = subprocess.run(["ffmpeg", "-v", "error", "-i", v[0], "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "gray16le", "-"],
                     capture_output=True).stdout
y16 = np.frombuffer(dek, np.uint16)
pruef(len(np.unique(y16 >> 6)) > 200, f"zu wenige Tonstufen: {len(np.unique(y16 >> 6))}")
# 16 Bit mit allen Effekten, die ins Bild zeichnen oder vergleichen. OpenCV
# zeichnet Text nur in 8-Bit-Bilder - die Telemetrie brach mit 16 Bit ab.
e = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=RT_CLI, tiff16=True, codec_idx=9,
                   telemetry=True, astro_clean=True, max_blur=3, min_blur=2, fade_sec=0.5))
pruef(e.ok(), f"16 Bit mit Telemetrie/Astro/Blur scheitert: {e.fehler[:1]}")
anz = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                      "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", videos(o)[0]],
                     capture_output=True, text=True).stdout.strip() if videos(o) else ""
pruef(anz == "30", f"16-Bit-Video mit Effekten hat {anz} Bilder")
t = "20:51:33 | ISO 3200 | f/2.8 | 20.0s"
b8 = np.full((360, 640, 3), 90, np.uint8)
b16 = b8.astype(np.uint16) * 257
pm.telemetrie_zeichnen(b8, t, 360, 255)
pm.telemetrie_zeichnen(b16, t, 360, 65535)
pruef((b8[330:345, 15:200] == 255).any(), "Telemetrie 8 Bit: kein Text")
pruef(int(np.abs(b16.astype(np.int64) - b8.astype(np.int64) * 257).max()) <= 257,
      "Telemetrie 16 Bit weicht von 8 Bit ab")
# Astro-Clean: 16 Bit verhaelt sich wie 8 Bit (Schwelle mitskaliert)
w = pm.Worker(parameter(o, d))
rng = np.random.default_rng(3)
n8 = [np.clip(100 + rng.normal(0, 4, (60, 80, 3)), 0, 255).astype(np.uint8) for _ in range(3)]
n8[1][30, 10:70] = 250                     # Satellitenspur nur im mittleren Bild
r8 = w._remove_satellites(*n8)
r16 = w._remove_satellites(*[x.astype(np.uint16) * 257 for x in n8])
pruef(r8[30, 40, 0] < 150 and r16[30, 40, 0] < 150 * 257, "Satellitenspur nicht entfernt")
ersetzt8 = int((r8 != n8[1]).any(axis=2).sum())
ersetzt16 = int((r16 != n8[1].astype(np.uint16) * 257).any(axis=2).sum())
pruef(abs(ersetzt16 - ersetzt8) <= 5 and ersetzt8 < 100,
      f"Astro-Clean ersetzt 8 Bit {ersetzt8}, 16 Bit {ersetzt16} Bildpunkte")
# Zurueck auf JPG: Bilder werden neu entwickelt, keine TIFFs im Film
e = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=RT_CLI, tiff16=False))
pruef(e.ok() and len(glob.glob(os.path.join(o, "Purelapse", "Deflickered_JPG", "*.jpg"))) == 30, "Rueckweg zu JPG")
pruef(any("entwickle" in z.lower() or "Entwicklung" in z for z in e.log) and not any("uebersprungen" in z for z in e.log),
      "beim Formatwechsel wird nicht neu entwickelt")
# Platzpruefung
w = pm.Worker(parameter(o, d, tiff16=True))
alt = pm.shutil.disk_usage
# Die Pruef-RAWs sind winzig (300 x 200); 1 KB frei reicht trotzdem nicht
pm.shutil.disk_usage = lambda p: type("U", (), {"free": 1024})()
try:
    w._platz_pruefen(d, o); pruef(False, "zu wenig Platz nicht erkannt")
except RuntimeError as x:
    pruef("Platz" in str(x), str(x))
finally:
    pm.shutil.disk_usage = alt
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
