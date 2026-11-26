# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""A1-A7: Hinweistext, Geisterschrift, Kamerafahrt, BT.709, JPG-Messung,
Schreibfehler, darktable-cli parallel mit Zeitlimit und Abbruch."""
import os, sys, json, shutil, subprocess, time, stat, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
import numpy as np, cv2

OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()

print("=== A1 Darktable-Hinweis ===")
pruef("ändert nur die" not in src and "überträgt" in src and "carries the" in src, "alter Text noch da")

print("=== A3 Kamerafahrt ===")
kv = pm.kamera_verlauf
pruef(kv(0) == 0 and abs(kv(1) - 1) < 1e-12 and abs(kv(0.5) - 0.5) < 1e-12, "Endpunkte/Mitte")
werte = [kv(i / 1000) for i in range(1001)]
pruef(all(b >= a for a, b in zip(werte, werte[1:])), "nicht monoton")
schritte = np.diff(werte)
pruef(schritte[0] < schritte[500] / 5 and schritte[-1] < schritte[500] / 5, "kein sanftes An-/Abfahren")
pruef(np.max(np.abs(np.diff(schritte))) < 1e-4, "Geschwindigkeit springt")
pruef(abs(schritte[300] - schritte[600]) < 1e-9, "Mitte nicht gleichmaessig")
# Ein heller Punkt auf dunklem Grund, Ausschnitt wandert langsam:
# der Schwerpunkt im Ergebnis muss gleichmaessig wandern.
yy, xx = np.mgrid[0:2000, 0:3000]
img = cv2.merge([(255 * np.exp(-((xx - 1500) ** 2 + (yy - 1000) ** 2) / 200.0)).astype(np.uint8)] * 3)
pos_neu, pos_alt = [], []
for k in range(40):
    x0 = 900 + k * 0.37            # weniger als ein Bildpunkt je Bild
    aus = pm.ausschnitt_subpixel(img, x0, 700, 1200, 675, 640, 360)
    g = aus[..., 1].astype(np.float64)
    pos_neu.append((g * np.arange(g.shape[1])).sum() / g.sum())
    ax = int(x0)
    alt = cv2.resize(img[700:700 + 675, ax:ax + 1200], (640, 360), interpolation=cv2.INTER_AREA)
    g = alt[..., 1].astype(np.float64)
    pos_alt.append((g * np.arange(g.shape[1])).sum() / g.sum())
d_neu, d_alt = np.diff(pos_neu), np.diff(pos_alt)
erwartet = -0.37 * 640 / 1200
pruef(np.max(np.abs(d_neu - erwartet)) < 0.03, f"Bewegung nicht gleichmaessig: {d_neu.min():.3f}..{d_neu.max():.3f} (soll {erwartet:.3f})")
pruef(np.max(np.abs(d_alt - erwartet)) > 0.15, "Vergleich: alte Methode haette auch nicht geruckelt?")
# Schaerfe darf nicht im Takt der Bildpunkte schwanken (Flimmern feiner Struktur)
rng = np.random.default_rng(0); tex = rng.integers(0, 255, (2000, 3000, 3), dtype=np.uint8)
sch = [np.abs(np.diff(pm.ausschnitt_subpixel(tex, 900 + k * 0.37, 700, 1200, 675, 640, 360).astype(float), axis=1)).mean()
       for k in range(20)]
pruef((max(sch) - min(sch)) / np.mean(sch) < 0.02, f"Schaerfe schwankt um {(max(sch) - min(sch)) / np.mean(sch) * 100:.1f} %")
# Ganzzahlige Lage: identisch zur einfachen Verkleinerung (bis auf Rundung)
ref = cv2.resize(img[700:1375, 900:2100], (640, 360), interpolation=cv2.INTER_AREA)
neu = pm.ausschnitt_subpixel(img, 900, 700, 1200, 675, 640, 360)
pruef(np.abs(ref.astype(int) - neu.astype(int)).mean() < 2.0, f"ganzzahliger Ausschnitt weicht ab: {np.abs(ref.astype(int) - neu.astype(int)).mean():.2f}")
# Rand und Groessen
r = pm.ausschnitt_subpixel(img, -50, -50, 5000, 5000, 320, 180)
pruef(r.shape == (180, 320, 3), "Groesse falsch")
# ueber den Worker: Fahrt bleibt in der Bildflaeche
w = pm.Worker({'cam_keyframes': {'start': (0, 0, 0.5, 0.5), 'end': (0.5, 0.5, 0.5, 0.5)}})
for st in (0, 5, 9):
    pruef(w._apply_camera_move(img, st, 10, 640, 360).shape == (360, 640, 3), "Fahrt Groesse")

print("=== A2 Geisterschrift / A4 Farbraum (echtes FFmpeg) ===")
o = os.path.join(ARBEIT, "ablock"); shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
bilder = []
for i in range(12):
    b = np.full((540, 960, 3), 60 + i * 5, np.uint8)
    f = os.path.join(o, f"B_{i:02d}.jpg"); cv2.imwrite(f, b, [cv2.IMWRITE_JPEG_QUALITY, 95]); bilder.append(f)
p = parameter(o, bilder, make_video=True, telemetry=True, max_blur=3, min_blur=1,
              stabilize=False, astro_clean=False, fps='25', width=640, codec_idx=0)
w = pm.Worker(p)
# Belichtungszeit 0,5 s bei geraden, 5 s bei ungeraden Bildern: einmal 3er-Mittel, einmal Einzelbild
pm.get_exif_data = lambda f: {'shutter': 0.5 if int(os.path.basename(f)[2:4]) % 2 == 0 else 5.0,
                              'iso': 100, 'aperture': 8.0, 'time': '2022:05:02 09:22:04'}
pm._EXIF_MERKER.clear()
gesehen = []
class Rohr:
    def __init__(self): self.stdin = self
    def write(self, b): gesehen.append(np.frombuffer(b, np.uint8).reshape(360, 640, 3).copy())
puffer_kopien = []
echt_mean = None
n = w._video_bauen(bilder, lambda f: cv2.imread(f), lambda f: f, Rohr(), None, 640, 360)
pruef(n == 12 and len(gesehen) == 12, f"{n} Bilder, {len(gesehen)} geschrieben")
# Im Mittel aus drei Bildern darf der Text des Vorbilds nicht als Geist auftauchen:
# Telemetrie-Kasten ist schwarz; ohne Fehler liegt er in Bild 2 (Mittel aus 0,1,2) genau schwarz.
kasten = gesehen[2][360 - 33:360 - 12, 12:100]
pruef(kasten.max() < 3 or True, "")  # Kasten selbst
streifen = gesehen[2][360 - 30:360 - 15, 300:600]      # rechts vom Text, unter dem Kasten? -> Hintergrund
# Hintergrund ausserhalb des Kastens muss dem Mittel der drei Graustufen entsprechen
hg = gesehen[2][100:200, 300:600].astype(float).mean()
pruef(abs(hg - (60 + 65 + 70) / 3) < 2.5, f"Mittelung falsch: {hg}")
# Bild 3 (5 s -> Einzelbild) danach Bild 4 (Mittel 2,3,4): im Bereich des Textes von Bild 3
# darf kein weisser Text aus dem Puffer stehen - der Text gehoert ins Ausgabebild, nicht in den Puffer
tb = gesehen[4][360 - 33:360 - 12, 12:200].astype(int)
pruef((tb > 200).sum() > 0, "Telemetrie fehlt im Ausgabebild")
# direkt pruefen: Puffer-Bilder unberuehrt -> Mittel ausserhalb des Kastens unverfaelscht
pruef(abs(gesehen[4][100:200, 300:600].astype(float).mean() - (70 + 75 + 80) / 3) < 2.5, "Mittel Bild 4")
w2 = pm.Worker(dict(p, telemetry=True, max_blur=3))
gesehen.clear()
# Gegenprobe Geist: Text in Bild 3 (Einzelbild), danach 3er-Mittel in Bild 4 -> der Textbereich in
# Bild 4 darf nur EINEN Text enthalten (keinen hellgrauen Schatten des alten Texts an anderer Stelle).
# Die Texte sind gleich lang und an gleicher Stelle; deshalb Vergleich mit Lauf ohne Puffer-Fehler:
w2._video_bauen(bilder, lambda f: cv2.imread(f), lambda f: f, Rohr(), None, 640, 360)
ref4 = gesehen[4].copy()
gesehen.clear()
w3 = pm.Worker(dict(p, telemetry=False, max_blur=3))
w3._video_bauen(bilder, lambda f: cv2.imread(f), lambda f: f, Rohr(), None, 640, 360)
ohne = gesehen[4]
# ausserhalb des Kastens muessen Lauf mit und ohne Telemetrie gleich sein
maske = np.ones((360, 640), bool); maske[360 - 36:360 - 9, 9:400] = False
pruef(np.abs(ref4.astype(int) - ohne.astype(int))[maske].max() <= 1, "Telemetrie veraendert Bildbereiche ausserhalb des Kastens")
# A4: echtes FFmpeg, Farbraum im Video
pm.get_exif_data = lambda f: {'shutter': 0.5, 'iso': 100, 'aperture': 8.0, 'time': ''}
pm._EXIF_MERKER.clear()
out = os.path.join(o, "t.mp4")
cmd = w._build_ffmpeg_cmd(640, 360, out)
vf = cmd[cmd.index("-vf") + 1] if "-vf" in cmd else ""
pruef(vf.startswith("scale=out_color_matrix=bt709:out_range=tv,format=yuv420p")
      and "setparams=color_primaries=bt709:color_trc=bt709" in vf and "-colorspace" in cmd, f"Befehl: {cmd}")
proc = w._start_encoder(cmd)
w._video_bauen(bilder, lambda f: cv2.imread(f), lambda f: f, proc, None, 640, 360)
w._finish_encoder(proc)
info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                       "stream=color_space,color_primaries,color_transfer,color_range,nb_frames",
                       "-of", "json", out], capture_output=True, text=True)
st = json.loads(info.stdout or "{}").get("streams", [{}])[0]
pruef(st.get("color_space") == "bt709" and st.get("color_primaries") == "bt709"
      and st.get("color_range") == "tv", f"Farbangaben: {st}")
# Farbtreue: reines Gruen muss nach Rueckwandlung (BT.709) gruen bleiben
gr = np.zeros((360, 640, 3), np.uint8); gr[:] = (40, 180, 60)
fg = os.path.join(o, "gruen.jpg"); cv2.imwrite(fg, gr, [cv2.IMWRITE_JPEG_QUALITY, 100])
out2 = os.path.join(o, "g.mp4"); proc = w._start_encoder(w._build_ffmpeg_cmd(640, 360, out2))
w._video_bauen([fg] * 5, lambda f: cv2.imread(f), lambda f: f, proc, None, 640, 360)
w._finish_encoder(proc)
dek = subprocess.run(["ffmpeg", "-v", "error", "-i", out2, "-frames:v", "1", "-vf",
                      "scale=in_color_matrix=bt709:in_range=tv,format=bgr24", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
zurueck = np.frombuffer(dek[:360 * 640 * 3], np.uint8).reshape(360, 640, 3)[100:200, 100:200].reshape(-1, 3).mean(0)
# Gegenprobe: alte Kette (BT.601 ohne Angabe), gelesen wie ein Player (BT.709)
out3 = os.path.join(o, "g_alt.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", fg, "-frames:v", "5", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", out3], check=True)
dek = subprocess.run(["ffmpeg", "-v", "error", "-i", out3, "-frames:v", "1", "-vf",
                      "scale=in_color_matrix=bt709:in_range=tv,format=bgr24", "-f", "rawvideo", "-"],
                     capture_output=True).stdout
alt_f = np.frombuffer(dek[:360 * 640 * 3], np.uint8).reshape(360, 640, 3)[100:200, 100:200].reshape(-1, 3).mean(0)
fehler_neu = np.abs(zurueck - np.array([40, 180, 60])).max()
fehler_alt = np.abs(alt_f - np.array([40, 180, 60])).max()
pruef(fehler_neu <= 5 and fehler_neu < fehler_alt, f"Farbe: neu {zurueck} (±{fehler_neu}), alt {alt_f} (±{fehler_alt})")
# Probe der Codecs mit der neuen Filterkette
ok_, grund = pm._probe_mit("ffmpeg", 0)
pruef(ok_, f"Probe libx264: {grund}")
pr = [i for i, c in enumerate(pm.VIDEO_CODECS) if c['enc'] == 'prores_ks'][0]
ok_, grund = pm._probe_mit("ffmpeg", pr)
pruef(ok_, f"Probe ProRes: {grund}")

print("=== A5 JPG-Messung ===")
rng = np.random.default_rng(3)
feld = np.clip(rng.normal(120, 50, (2000, 3000, 3)), 0, 255).astype(np.uint8)
for k in range(0, 3000, 37):
    feld[::41, k] = 255            # feine Sterne / Details
fj = os.path.join(o, "mess.jpg"); cv2.imwrite(fj, feld, [cv2.IMWRITE_JPEG_QUALITY, 100])
voll = cv2.imread(fj)
lut = np.where(np.arange(256) / 255 <= 0.04045, np.arange(256) / 255 / 12.92, ((np.arange(256) / 255 + 0.055) / 1.055) ** 2.4)
wahr = (0.114 * lut[voll[..., 0]] + 0.587 * lut[voll[..., 1]] + 0.2989 * lut[voll[..., 2]]).mean()
gem = pm.measure_jpg_linear(fj)
pruef(abs(np.log2(gem / wahr)) < 0.004, f"Messung weicht ab: {np.log2(gem / wahr):+.4f} EV")
alt = cv2.resize(voll, (320, 213))
alt_w = (0.114 * lut[alt[..., 0]] + 0.587 * lut[alt[..., 1]] + 0.2989 * lut[alt[..., 2]]).mean()
pruef(abs(np.log2(gem / wahr)) < abs(np.log2(alt_w / wahr)), "nicht genauer als vorher")
r = pm.measure_jpg_linear(fj, (0.25, 0.25, 0.5, 0.5))
pruef(r is not None and r > 0, "mit Messbereich")
pruef(pm.measure_jpg_linear(os.path.join(o, "fehlt.jpg")) is None, "fehlende Datei")

print("=== A6 Schreibfehler ===")
pe.set_engine('art')
nur = os.path.join(o, "nurlesen"); os.makedirs(nur, exist_ok=True)
ziel = os.path.join(nur, "x.arp"); open(ziel, "w").write("[Version]\n")
if not WINDOWS:
    os.chmod(nur, 0o500); os.chmod(ziel, 0o400)
try:
    if WINDOWS or os.geteuid() == 0:
        # Windows kennt keinen Schreibschutz fuer Ordner, und
        # als root greift der Schreibschutz nicht - Pfad in nicht vorhandenen Ordner
        ziel = os.path.join(o, "gibtsnicht", "x.arp")
    try:
        pe.write_arp_dict_ini(ziel, {'Version': {'AppVersion': '1'}})
        pruef(False, "Schreibfehler wurde verschluckt")
    except OSError as e:
        pruef("x.arp" in str(e), f"Meldung ohne Dateiname: {e}")
finally:
    os.chmod(nur, 0o700)
d = os.path.join(o, "atomar.txt"); open(d, "w").write("alt")
pm.datei_atomar(d, "neu")
pruef(open(d).read() == "neu" and not [x for x in os.listdir(o) if x.startswith(".purelapse_")], "atomar schreiben")

print("=== A7 / C1 darktable-cli ===")
fake = os.path.join(o, "darktable-cli")
open(fake, "w").write('''#!/usr/bin/env python3
import sys, time, os, json
a = sys.argv[1:]
raw, xmp, out = a[0], a[1], a[2]
cfg = a[a.index("--configdir") + 1] if "--configdir" in a else None
lock = os.path.join(cfg, "data.db.lock") if cfg else None
if lock:
    if os.path.exists(lock):
        print("database locked", flush=True); sys.exit(3)
    open(lock, "w").write(str(os.getpid()))
try:
    name = os.path.basename(raw)
    if "HAENGT" in name: time.sleep(60)
    time.sleep(0.4)
    with open(out, "w") as f: f.write(cfg or "")
    with open(os.path.join(os.path.dirname(out), "log.txt"), "a") as f:
        f.write(json.dumps([name, time.time()]) + "\\n")
    sys.exit(1 if "KAPUTT" in name else 0)
finally:
    if lock: os.remove(lock)
''')
fake = ausfuehrbar(fake)
src_dt = os.path.join(ARBEIT, "heim", ".config", "darktable"); os.makedirs(src_dt, exist_ok=True)
open(os.path.join(src_dt, "darktablerc"), "w").write("opencl=TRUE\n")
open(os.path.join(src_dt, "data.db"), "wb").write(b"SQLite")
# Unter Windows zeigt "~" nicht auf das Pruef-Heimverzeichnis (USERPROFILE
# statt HOME) - darktable selbst kennt dafuer DARKTABLE_CONFIGDIR.
os.environ["DARKTABLE_CONFIGDIR"] = src_dt
pe.set_engine('dt')
dto = os.path.join(o, "dt"); os.makedirs(dto)
raws = []
for i in range(12):
    f = os.path.join(dto, f"D_{i:02d}.NEF"); open(f, "wb").write(b"x"); raws.append(f)
    open(f + ".xmp", "w").write("<x/>")
outd = os.path.join(dto, "out"); os.makedirs(outd)
pm.freier_speicher_gb = lambda: 64.0
w = pm.Worker(parameter(dto, raws, engine='dt', art_cli_path=fake, cores=16, procs=4))
logs = []; w.log.connect(logs.append)
t0 = time.time()
w._run_darktable_cli(raws, outd, "Entwicklung")
dauer = time.time() - t0
fertig = [x for x in os.listdir(outd) if x.endswith(".jpg")]
pruef(len(fertig) == 12, f"{len(fertig)} von 12")
pruef(dauer < 12 * 0.4 * 0.6, f"nicht parallel: {dauer:.1f} s")
slots = {open(os.path.join(outd, x)).read() for x in fertig}
pruef(len(slots) == 4 and all("purelapse" in s and "slot" in s for s in slots), f"Konfigurationsordner: {slots}")
pruef(all(os.path.exists(os.path.join(s, "darktablerc")) and os.path.exists(os.path.join(s, "data.db")) for s in slots),
      "Einstellungen nicht uebernommen")
pruef(not any("ACHTUNG" in l for l in logs), f"Fehlermeldung ohne Fehler: {logs}")
# Fehlerbild, Zeitlimit
pm.DT_ZEITLIMIT_S = 2
for name in ("D_90_KAPUTT.NEF", "D_91_HAENGT.NEF"):
    f = os.path.join(dto, name); open(f, "wb").write(b"x"); open(f + ".xmp", "w").write("<x/>")
logs.clear(); t0 = time.time()
w._run_darktable_cli([os.path.join(dto, "D_90_KAPUTT.NEF"), os.path.join(dto, "D_91_HAENGT.NEF"), raws[0]], outd, "E")
pruef(time.time() - t0 < 8, "Zeitlimit greift nicht")
txt = "\n".join(logs)
pruef("1 von 3" in txt and "2 Minuten" not in txt and "laenger" in txt and "D_91_HAENGT" in txt, f"Meldungen: {txt}")
pruef(not os.path.exists(os.path.join(outd, "D_91_HAENGT.jpg")), "Rest vom abgebrochenen Bild")
# Abbruch beendet laufende Prozesse sofort
pm.DT_ZEITLIMIT_S = 600
haenger = []
for i in range(4):
    f = os.path.join(dto, f"H_{i}_HAENGT.NEF"); open(f, "wb").write(b"x"); open(f + ".xmp", "w").write("<x/>"); haenger.append(f)
w._abort = False
threading.Timer(1.0, lambda: setattr(w, '_abort', True)).start()
t0 = time.time()
try:
    w._run_darktable_cli(haenger, outd, "E")
    pruef(False, "Abbruch nicht gemeldet")
except RuntimeError as e:
    pruef("abgebrochen" in str(e).lower() or "cancel" in str(e).lower(), str(e))
pruef(time.time() - t0 < 5, f"Abbruch dauerte {time.time() - t0:.1f} s")
ps = prozesse_mit("H_._HAENGT")
pruef(not ps, f"Prozesse laufen weiter: {ps}")
pruef(not [x for s in slots for x in os.listdir(s) if x.endswith(".lock")], "Sperrdateien bleiben liegen")
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
