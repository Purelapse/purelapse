# -*- coding: utf-8 -*-
"""
Pruefstand: laedt das ganze Programm und faehrt echte Ablaeufe.

Echt sind: purelapse_main, purelapse_engines, NumPy, SciPy, OpenCV, FFmpeg.
Nachgebaut sind: Qt (ohne Bildschirm), rawpy, exifread, pyqtgraph und die
Engine (fake_engine.py unter den Namen rawtherapee-cli und ART-cli).
"""
import os, sys, io, json, shutil, glob, math, time, datetime
import numpy as np
import cv2

HIER = os.path.dirname(os.path.abspath(__file__))
PROJEKT = os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ARBEIT = os.environ.get("PURELAPSE_ARBEIT", os.path.join(__import__("tempfile").gettempdir(), "purelapse_pruefung"))

# Eigenes Heimverzeichnis, damit keine Einstellungsdateien verstreut werden
HEIM = os.path.join(ARBEIT, "heim")
os.makedirs(HEIM, exist_ok=True)
# Pakete, die mit "pip install --user" unter ~/.local liegen (z. B. OpenCV),
# muessen auch die nachgebauten Engines noch finden, obwohl HOME umgebogen wird.
import site
os.environ.setdefault("PYTHONUSERBASE", site.getuserbase())
os.environ["HOME"] = HEIM
# Basisprofile frueherer Laeufe weg: sie stammen von der nachgebauten
# Engine, wie sie DAMALS war. Kennt die heutige ein Werkzeug mehr, fehlte
# es sonst im Profil, und die Pruefung liefe gegen einen alten Stand.
import glob as _glob, json as _json
for _alt in _glob.glob(os.path.join(HEIM, ".local", "share", "purelapse", "basis_*")):
    try:
        os.remove(_alt)
    except OSError:
        pass
_konf = os.path.join(HEIM, ".config", "purelapse", "purelapse.json")
try:
    with open(_konf, encoding="utf-8") as _f:
        _k = _json.load(_f)
    for _e in (_k.get("engines") or {}).values():
        if isinstance(_e, dict):
            _e.pop("profil", None)
    with open(_konf, "w", encoding="utf-8") as _f:
        _json.dump(_k, _f)
except (OSError, ValueError):
    pass
# Eigener Ordner fuer Zwischendateien: ein gleichzeitig offenes Purelapse
# legt seine Vorschau-Ordner sonst ins selbe /tmp und stoert die Zaehlung.
import tempfile
TEMP = os.path.join(ARBEIT, "tmp")
os.makedirs(TEMP, exist_ok=True)
os.environ["TMPDIR"] = TEMP
tempfile.tempdir = TEMP
sys.path.insert(0, os.path.join(HIER, "stubs"))
sys.path.insert(0, PROJEKT)
sys.argv = ["purelapse"]

import purelapse_main as pm          # noqa: E402
import purelapse_engines as pe       # noqa: E402
import exifread                      # noqa: E402  (Stellvertreter)
from PyQt5 import _basis             # noqa: E402

RT_CLI = os.path.join(HIER, "rawtherapee-cli")
ART_CLI = os.path.join(HIER, "ART-cli")


# ---------------------------------------------------------------- Szene
def szene(ordner, n=60, art="raw", flackern=0.06, stufen=True, sonne=False,
          luecke=None, seed=1, sonne_r=16, hell=1.0):
    """
    Baut eine Sonnenuntergangs-Sequenz.

    Das Licht nimmt gleichmaessig ab; die Kamera gleicht in Drittelstufen
    nach (Saegezahn) und die Blende streut von Bild zu Bild (Flackern).
    Rueckgabe: (Dateiliste, wahre Helligkeit je Bild in EV)
    """
    shutil.rmtree(ordner, ignore_errors=True)
    os.makedirs(ordner)
    rng = np.random.default_rng(seed)
    h, w = 200, 300
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    himmel = 0.55 - 0.35 * (yy / h)
    bild0 = np.stack([himmel * 1.15, himmel * 0.95, himmel * 0.80], axis=2)
    bild0[int(h * 0.72):, :, :] *= 0.18                      # Vordergrund
    bild0 += rng.normal(0, 0.004, bild0.shape)
    sonnen_maske = ((yy - h * 0.55) ** 2 + (xx - w * 0.5) ** 2) < sonne_r ** 2
    dateien, wahr = [], []
    kamera = 0.0
    t0 = datetime.datetime(2022, 5, 1, 19, 38, 5)
    sek = 0.0
    for i in range(n):
        licht = -2.2 * i / max(1, n - 1)                     # EV, faellt ab
        if stufen and (licht + kamera) < -0.34:
            kamera += 1.0 / 3.0                              # Kamera regelt nach
        zappel = float(rng.normal(0, flackern))
        ev = licht + kamera + zappel
        lin = np.clip(bild0 * 0.30 * hell * 2.0 ** ev, 0, 1.0)
        if sonne:
            # Der Sonnenball ist immer ausgebrannt, gleich wie die Kamera
            # belichtet: Rot am Anschlag, Gruen haengt zurueck -> rosa.
            lin[sonnen_maske] = (1.0, 0.70, 0.97)
        name = f"IMG_{i:04d}"
        if art == "raw":
            pfad = os.path.join(ordner, name + ".NEF")
            with open(pfad, "wb") as f:
                np.save(f, (lin * 65535 + 0.5).astype(np.uint16))
        else:
            pfad = os.path.join(ordner, name + ".jpg")
            s = np.where(lin <= 0.0031308, 12.92 * lin,
                         1.055 * np.power(lin, 1 / 2.4) - 0.055)
            cv2.imwrite(pfad, cv2.cvtColor((np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8),
                                           cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_JPEG_QUALITY, 97])
        sek += 5.0 if luecke != i else 15.0                  # Luecke: 2 Bilder fehlen
        exifread.DATEN[os.path.basename(pfad)] = {
            'zeit': (t0 + datetime.timedelta(seconds=sek)).strftime("%Y:%m:%d %H:%M:%S"),
            'belichtung': 1.0 / 250 * 2.0 ** kamera, 'iso': 100, 'blende': 8.0}
        dateien.append(pfad)
        wahr.append(licht)
    return dateien, np.array(wahr)


# ---------------------------------------------------------------- Messen
def helligkeit_ev(bild_bgr):
    """Mittlere Helligkeit in linearem Licht, als EV."""
    b = bild_bgr.astype(np.float64) / 255.0
    lin = np.where(b <= 0.04045, b / 12.92, ((b + 0.055) / 1.055) ** 2.4)
    y = lin[..., 2] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 0] * 0.0722
    return math.log2(max(1e-6, float(y.mean())))


def flackern(ev):
    """Streuung um den laufenden Median - das, was man als Flackern sieht."""
    ev = np.asarray(ev, dtype=np.float64)
    n = len(ev)
    rest = [ev[i] - np.median(ev[max(0, i - 3):min(n, i + 4)]) for i in range(n)]
    return float(np.std(rest))


def ordner_flackern(ordner):
    dateien = sorted(glob.glob(os.path.join(ordner, "*.jpg")))
    return flackern([helligkeit_ev(cv2.imread(f)) for f in dateien]), len(dateien)


def tonwert_flackern(ordner):
    """
    Flackern getrennt nach Himmel (oben) und Vordergrund (unten).

    Eine von Bild zu Bild andere Tonkurve verschiebt Lichter und Schatten
    gegeneinander. Die mittlere Helligkeit kann dabei ruhig bleiben - das
    Flackern sieht man trotzdem.
    Rueckgabe: (Himmel, Vordergrund)
    """
    dateien = sorted(glob.glob(os.path.join(ordner, "*.jpg")))
    oben, unten = [], []
    for f in dateien:
        b = cv2.imread(f)
        h = b.shape[0]
        oben.append(helligkeit_ev(b[:int(h * 0.6)]))
        unten.append(helligkeit_ev(b[int(h * 0.8):]))
    return flackern(oben), flackern(unten)


def video_flackern(pfad):
    cap = cv2.VideoCapture(pfad)
    ev = []
    while True:
        ok, bild = cap.read()
        if not ok:
            break
        ev.append(helligkeit_ev(bild))
    cap.release()
    return (flackern(ev) if len(ev) > 5 else float('nan')), len(ev)


# ---------------------------------------------------------------- Lauf
class Ergebnis:
    def __init__(self):
        self.log, self.status, self.fertig, self.fehler = [], [], [], []
        self.ausgabe, self.clip = [], []

    @property
    def text(self):
        return "\n".join(self.log)

    def ok(self):
        return bool(self.fertig) and not self.fehler


def lauf(params, vor_start=None):
    """Startet den Worker so, wie das Hauptfenster es taete, und sammelt."""
    e = Ergebnis()
    w = pm.Worker(params)
    w.log.connect(e.log.append)
    w.status.connect(e.status.append)
    w.finished_ok.connect(e.fertig.append)
    w.failed.connect(e.fehler.append)
    w.output_ready.connect(e.ausgabe.append)
    w.clip_report.connect(lambda a, g, s: e.clip.append((a, g, s)))
    if vor_start:
        vor_start(w)
    e.worker = w
    w.run()
    return e


def parameter(ordner, dateien, **mehr):
    """Dieselben Schluessel, die _collect_params zusammenstellt."""
    p = {
        'target_dir': ordner, 'files': dateien,
        'format': 'raw' if dateien[0].lower().endswith('.nef') else 'jpg',
        'scene_int': 1, 'smooth_val': 50, 'ev_val': 0.0, 'roi_rel': None,
        'fps': '25', 'width': 640, 'res_name': '360p', 'res_idx': 0,
        'max_blur': 1, 'min_blur': 1, 'cam_keyframes': None,
        'reverse_play': False, 'stabilize': False, 'denoise': False,
        'astro_clean': False, 'hotpixel': False, 'fade_sec': 0.0,
        'telemetry': False, 'make_video': True, 'engine': 'rt',
        'cores': 4, 'procs': 0, 'codec_idx': 0, 'qual_idx': 1,
        'calib_rounds': 2, 'diag': False, 'out_dir_mode': 0,
        'custom_out_dir': '', 'versioning': False,
    }
    p.update(mehr)
    return p


def videos(ordner):
    """Fertige Videos: im Purelapse-Ordner des Bilderordners (aeltere Laeufe: lose)."""
    return sorted(glob.glob(os.path.join(ordner, "Purelapse", "*.mp4"))
                  + glob.glob(os.path.join(ordner, "Purelapse", "*.mov"))
                  + glob.glob(os.path.join(ordner, "*.mp4"))
                  + glob.glob(os.path.join(ordner, "*.mov")))


def pl(ordner, *teile):
    """Pfad im Purelapse-Ordner eines Bilderordners."""
    return os.path.join(ordner, "Purelapse", *teile)
