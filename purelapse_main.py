#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
"""
PURELAPSE - GUI (Linux)
================================
Grafische Oberflaeche fuer den JPG-, ART/RawTherapee- und Darktable-RAW-
Zeitraffer-Workflow.
Features: ROI, Export, Astro-Clean, Visueller 16:9 Keyframe-Crop, Sonnenstand.
"""
import sys
# --- Einzeldatei-Build (PyInstaller): Der Starter setzt LD_LIBRARY_PATH auf die
# mitgelieferten Bibliotheken. Externe Programme (ffmpeg, darktable-cli,
# rawtherapee-cli, ART-cli) duerfen das NICHT erben, sonst laden sie falsche
# Bibliotheken. Fuer den eigenen Prozess ist die Variable ab hier egal.
if getattr(sys, "frozen", False):
    _ld_orig = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if _ld_orig:
        os.environ["LD_LIBRARY_PATH"] = _ld_orig
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)
from PyQt5 import QtCore, QtGui, QtWidgets
# --- FIX: App zwingend als Allererstes starten ---
if not QtWidgets.QApplication.instance():
    app_instance = QtWidgets.QApplication(sys.argv)
else:
    app_instance = QtWidgets.QApplication.instance()
# ------------------------------------------------
import glob
import math
import time
import subprocess
import shutil
import tempfile
import multiprocessing
import concurrent.futures
from collections import deque
import json
import hashlib
import threading
import contextlib
import re
import html
import datetime
import cv2
import numpy as np
import rawpy
from scipy.ndimage import gaussian_filter1d
import exifread
import pyqtgraph as pg
# pyqtgraph zeichnet ohne Antialiasing, dadurch bekommen schraege Linien
# sichtbare Treppenstufen. Fuer die paar tausend Punkte hier ist der
# Aufwand unerheblich.
pg.setConfigOptions(antialias=True)

# Engine-Logik (ART / RawTherapee / Darktable) kommt aus einem eigenen
# Modul - purelapse_engines.py muss im selben Ordner liegen wie diese Datei.
from purelapse_engines import *
from purelapse_texte import *
from purelapse_design import *
from purelapse_design import _rgb
import purelapse_design as design

# === VERSIONSNUMMER ===
# "-beta": oeffentliche Testversion. Fuer die erste stabile Ausgabe das
# Anhaengsel entfernen (siehe CHANGELOG.md).
VERSION = "2.44.1-beta"
# ======================

# Startbild und Endbild je Ordner: was davor und danach liegt, bleibt im
# ganzen Arbeitsgang aussen vor. Steht in der Konfiguration ('bereiche').


def lade_bereiche():
    d = konfig_lesen('bereiche', standard={})
    return d if isinstance(d, dict) else {}


def speichere_bereich(ordner, start, ende):
    d = lade_bereiche()
    if start or ende:
        d[ordner] = [start or "", ende or ""]
    else:
        d.pop(ordner, None)
    konfig_setzen('bereiche', d)


def bereich_anwenden(files, start_name, end_name):
    """
    Schneidet eine Dateiliste auf Startbild bis Endbild zu.
    Rueckgabe: (Liste, erster Index, letzter Index). Ein unbekannter Name
    oder ein verdrehter Bereich gilt als "keine Einschraenkung".
    """
    n = len(files)
    if n == 0:
        return [], 0, -1
    namen = [os.path.basename(f) for f in files]
    a = namen.index(start_name) if start_name in namen else 0
    b = namen.index(end_name) if end_name in namen else n - 1
    if a > b:
        a, b = 0, n - 1
    return list(files[a:b + 1]), a, b

# ==========================================================================
#  RAW-FORMATE
#
#  Von rawpy/libraw unterstuetzte RAW-Endungen, die Purelapse als "RAW"
#  behandelt. An EINER Stelle gepflegt statt an mehreren endswith()-Tupeln.
# ==========================================================================
RAW_EXTS = ('.nef', '.cr2', '.cr3', '.dng', '.arw', '.raf', '.orf', '.rw2', '.pef', '.srw')

def is_raw_file(path):
    return path.lower().endswith(RAW_EXTS)

def find_raw_files(target_dir):
    """Alle RAW-Dateien eines Ordners, unabhaengig vom Kamerahersteller."""
    out = []
    for ext in RAW_EXTS:
        out += glob.glob(os.path.join(target_dir, "*" + ext))
        out += glob.glob(os.path.join(target_dir, "*" + ext.upper()))
    return sorted(out)

def find_original_raw(target_dir, stem):
    """Sucht zu einem Dateinamen-Stamm (ohne Endung) die zugehoerige RAW-Datei."""
    for ext in RAW_EXTS:
        for e in (ext, ext.upper()):
            p = os.path.join(target_dir, stem + e)
            if os.path.exists(p):
                return p
    return os.path.join(target_dir, stem + ".NEF")  # Fallback wie zuvor

# Datei im Bilderordner, in der Pass 1 seine reinen Deflicker-Werte ablegt.
DEFLICKER_DB = "purelapse_deflicker.json"
CALIB_DB = "purelapse_calib.json"
DEV_INDEX = ".purelapse_developed.json"
RESULT_DB = "purelapse_result.json"
# Alles, was Purelapse in einem Bilderordner anlegt - Videos, entwickelte
# Bilder, Messwerte, Protokolle -, liegt im Unterordner "Purelapse". Nur die
# Begleitdateien der Engines (.arp/.pp3/.xmp) bleiben neben den Bildern,
# weil ART, RawTherapee und darktable sie genau dort erwarten.
PL_ORDNER = "Purelapse"
ZWISCHEN_ORDNER = "Deflickered_JPG"
PROTOKOLLE = ("purelapse_pass1.csv", "purelapse_pass2.csv", "purelapse_profiles.csv",
              "purelapse_arp_check.log", "purelapse_art.log")

if os.environ.get("APPIMAGE"):
    # AppImage: das Programm liegt in einem schreibgeschuetzten Abbild.
    # "Programmverzeichnis" meint dann den Ordner, in dem die .AppImage liegt.
    SCRIPT_DIR = os.path.dirname(os.path.abspath(os.environ["APPIMAGE"]))
elif getattr(sys, "frozen", False):
    # Einzeldatei-Build: __file__ liegt in einem Temp-Ordner, der beim Beenden
    # geloescht wird -> stattdessen den Ordner der Programmdatei nehmen.
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    try:
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        SCRIPT_DIR = os.getcwd()


def ffmpeg_kandidaten():
    """
    Alle FFmpeg-Programme, die in Frage kommen, in dieser Reihenfolge:
    das des Systems, dann das mitgelieferte aus imageio-ffmpeg.

    Das System-FFmpeg kommt zuerst, auch im AppImage: es ist zu den
    Grafiktreibern des Rechners passend gebaut. Das mitgelieferte ist
    meist neuer und verlangt fuer NVENC einen ebenso neuen
    NVIDIA-Treiber ("Driver does not support the required nvenc API
    version") - es dient als Rueckfall, wenn das System keines hat.
    """
    out = []
    system = shutil.which("ffmpeg")
    if system:
        out.append(system)
    try:
        import imageio_ffmpeg
        eigen = imageio_ffmpeg.get_ffmpeg_exe()
        if eigen and eigen not in out:
            out.append(eigen)
    except Exception:
        pass
    return out or ["ffmpeg"]


def _find_ffmpeg():
    return ffmpeg_kandidaten()[0]


FFMPEG_BIN = _find_ffmpeg()


# ==========================================================================
#  AUSGEFRESSENE LICHTER
#
#  Zwei Messungen mit unterschiedlicher Aussagekraft:
#
#  Beim Einlesen eines Ordners steht nur das in der RAW-Datei eingebettete
#  Vorschau-JPEG zur Verfuegung. Das ist die Kamera-Entwicklung mit ihrer
#  eigenen Tonwertkurve und klippt deutlich frueher als die Sensordaten -
#  ein Hinweis also, keine Diagnose. Entsprechend hoch ist die Schwelle.
#
#  In Pass 1 misst measure_nef() dagegen die Sensordaten in 16 Bit und
#  linearem Licht. Was dort anschlaegt, ist wirklich verloren und laesst
#  sich auch von der Belichtungskorrektur nicht zurueckholen.
# ==========================================================================
CLIP_SCHWELLE_VORSCHAU = 0.010   # Anteil geklippter Pixel im Vorschau-JPEG
CLIP_SCHWELLE_RAW = 0.005        # Anteil geklippter Pixel in den Sensordaten


def lichter_auswerten(werte, schwelle):
    """
    Wertet eine Liste von Klipp-Anteilen aus (ein Wert je Bild).

    Rueckgabe: (anzahl_betroffen, gesamt, [(index, anteil), ...] absteigend
    nach Anteil, hoechstens 25 Eintraege).
    """
    treffer = []
    gesamt = 0
    for i, v in enumerate(werte):
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        gesamt += 1
        if f > schwelle:
            treffer.append((i, f))
    treffer.sort(key=lambda t: -t[1])
    return len(treffer), gesamt, treffer[:25]


# ==========================================================================
#  ZEITANZEIGE
#
#  Die Restzeit allein sagt wenig: sie schwankt, weil die Bilder
#  unterschiedlich lange brauchen. Zusammen mit der bereits verstrichenen
#  Zeit und der geschaetzten Gesamtdauer kann man dagegen entscheiden, ob
#  man wartet oder weggeht. Alle Arbeitsschritte benutzen denselben Text,
#  damit die Statuszeile nicht je Schritt anders aussieht.
# ==========================================================================
# ==========================================================================
#  RECHENKERN DER LIVE-VORSCHAU
#
#  Die Vorschau zeigt die Wirkung der Schnelleinstellungen, ohne ART oder
#  RawTherapee zu starten. Sie ist eine NAEHERUNG und keine Simulation der
#  Engine: deren Tonwertkurve, Farbprofil und Demosaik bleiben aussen vor.
#  Beurteilt wird damit die Veraenderung gegenueber dem jetzigen Zustand -
#  genau das, wofuer man beim Schieben eines Reglers ein Bild braucht.
#
#  Richtung der Weissabgleich-Regler: In der Oberflaeche beider Engines
#  macht eine hoehere Farbtemperatur das Bild waermer. Beide rechnen
#  intern "gmul /= green" (ART src/engine/colortemp.cc, RawTherapee
#  rtengine/colortemp.cc), Temperatur und Gruenwert folgen also derselben
#  Vorzeichenregel. Aus "waermer" folgt damit: ein hoeherer Gruenwert
#  macht das Bild gruener.
# ==========================================================================
VORSCHAU_BREITE = 1100       # Ladebreite der Vorschau in Pixeln
HISTOGRAMM_HOEHE = 150       # Hoehe des Histogramms im Dialog
HISTOGRAMM_BREITE = 260      # Breite - schmal genug, um es auf einen Blick zu lesen
ECHT_KANTE = 2000            # Kantenlaenge der echten Vorschau (Reserve zum Zoomen)
ZOOM_MAX = 8.0


def planck_xy(kelvin):
    """
    Farbort eines schwarzen Strahlers im CIE-1931-Diagramm.

    Naeherung nach Kim et al., wie sie auch in Bildbearbeitungen ueblich
    ist; im Bereich 1667 bis 25000 K genau genug fuer eine Vorschau.
    """
    t = max(1667.0, min(25000.0, float(kelvin)))
    if t <= 4000.0:
        x = (-0.2661239e9 / t ** 3 - 0.2343589e6 / t ** 2
             + 0.8776956e3 / t + 0.179910)
    else:
        x = (-3.0258469e9 / t ** 3 + 2.1070379e6 / t ** 2
             + 0.2226347e3 / t + 0.240390)
    if t <= 2222.0:
        y = (-1.1063814 * x ** 3 - 1.34811020 * x ** 2
             + 2.18555832 * x - 0.20219683)
    elif t <= 4000.0:
        y = (-0.9549476 * x ** 3 - 1.37418593 * x ** 2
             + 2.09137015 * x - 0.16748867)
    else:
        y = (3.0817580 * x ** 3 - 5.87338670 * x ** 2
             + 3.75112997 * x - 0.37001483)
    return x, y


# XYZ -> lineares sRGB (D65)
_XYZ_ZU_RGB = np.array([[3.2404542, -1.5371385, -0.4985314],
                        [-0.9692660, 1.8760108, 0.0415560],
                        [0.0556434, -0.2040259, 1.0572252]])


def beleuchtung_rgb(kelvin):
    """Lineares sRGB eines schwarzen Strahlers, auf Gruen normiert."""
    x, y = planck_xy(kelvin)
    y = max(1e-6, y)
    xyz = np.array([x / y, 1.0, (1.0 - x - y) / y])
    rgb = _XYZ_ZU_RGB.dot(xyz)
    rgb = np.maximum(rgb, 1e-4)
    return rgb / rgb[1]


def wb_faktoren(kelvin, gruen=1.0):
    """
    Kanalfaktoren fuer eine eingestellte Farbtemperatur.

    Kehrwert der Beleuchtung: wer der Entwicklung sagt, das Licht sei
    blaeulich gewesen, bekommt ein waermeres Bild zurueck. Deshalb steigt
    der Rotfaktor mit der Temperatur.
    """
    f = 1.0 / beleuchtung_rgb(kelvin)
    f = f / f[1]
    try:
        g = float(gruen)
    except (TypeError, ValueError):
        g = 1.0
    f[1] *= max(0.05, g)
    return f / f[1] if f[1] > 0 else f


def srgb_kodieren(linear):
    """Lineares Licht in die sRGB-Kennlinie, zum Anzeigen."""
    c = np.clip(linear, 0.0, 1.0)
    return np.where(c <= 0.0031308, 12.92 * c,
                    1.055 * np.power(c, 1.0 / 2.4) - 0.055)


def vorschau_rechnen(basis_linear, basis_temp, basis_gruen, werte):
    """
    Wendet die Schnelleinstellungen auf ein lineares Vorschaubild an.

    basis_linear  float32-Bild (H, W, 3) in linearem Licht, 0..1
    basis_temp    Farbtemperatur, die im Profil steht
    basis_gruen   Gruenwert, der im Profil steht
    werte         {id: Zahl} wie aus dem Dialog

    Gerechnet wird die DIFFERENZ zum jetzigen Zustand: bei unveraenderten
    Reglern kommt das Ausgangsbild zurueck. Was die Engine daraus absolut
    macht, bleibt ihre Sache.

    Schaerfe und Entrauschen sind nicht dabei - bei 520 Pixeln Breite
    waere jede Aussage darueber irrefuehrend.
    """
    bild = np.asarray(basis_linear, dtype=np.float32)
    # Zuerst die Lichter: in der Engine sitzt die Rekonstruktion ganz am
    # Anfang der Kette, noch vor Weissabgleich und Tonwerten.
    hl = float(werte.get('_hl_staerke', 0.0))
    if hl > 0:
        bild = lichter_ausbleichen(bild, hl)
    temp = werte.get('wb_temp', basis_temp)
    gruen = werte.get('wb_green', basis_gruen)
    if temp != basis_temp or gruen != basis_gruen:
        faktor = (wb_faktoren(temp, gruen) / wb_faktoren(basis_temp, basis_gruen))
        bild = bild * faktor.astype(np.float32).reshape(1, 1, 3)

    hell = float(werte.get('brightness', 0.0))
    if hell:
        # +-100 entsprechen rund +-1,5 Blendenstufen - in der Groessen-
        # ordnung dessen, was die Engines bei Vollausschlag tun.
        bild = bild * np.float32(2.0 ** (hell / 66.0))

    anzeige = srgb_kodieren(bild).astype(np.float32)

    kontrast = float(werte.get('contrast', 0.0))
    if kontrast:
        k = np.float32(2.0 ** (kontrast / 100.0))
        anzeige = np.clip(0.5 + (anzeige - 0.5) * k, 0.0, 1.0)

    saettigung = float(werte.get('saturation', 0.0))
    if saettigung:
        sf = np.float32(1.0 + saettigung / 100.0)
        luma = (anzeige[..., 0] * 0.2126 + anzeige[..., 1] * 0.7152
                + anzeige[..., 2] * 0.0722)[..., None]
        anzeige = np.clip(luma + (anzeige - luma) * sf, 0.0, 1.0)

    return (np.clip(anzeige, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)


def vorschau_basis_pegel(pfad, breite=VORSCHAU_BREITE):
    """
    Laedt ein Bild als lineares Vorschaubild.

    Rueckgabe: (float32 (H, W, 3) in 0..1 oder None, Pegel)

    Der Pegel sagt, wie hoch die hellsten Stellen VOR dem Normieren
    lagen (1.0 = am Anschlag). Nur bei hohem Pegel kann ueberhaupt etwas
    ausgebrannt sein.

    Die Helligkeit wird einmal so normiert, dass die hellsten Stellen
    gerade anliegen. Der Faktor bleibt danach fest - sonst wuerde der
    Helligkeitsregler nichts bewirken, weil sich die Anzeige jedes Mal
    nachzieht.
    """
    try:
        if is_raw_file(pfad):
            with rawpy.imread(pfad) as raw:
                roh = raw.postprocess(use_camera_wb=True, half_size=True,
                                      no_auto_bright=True, gamma=(1, 1),
                                      output_bps=16)
            bild = roh.astype(np.float32) / 65535.0
        else:
            roh = cv2.imdecode(np.fromfile(pfad, dtype=np.uint8),
                               cv2.IMREAD_COLOR)
            if roh is None:
                return None, 0.0
            # srgb_to_linear() arbeitet mit einer Tabelle und erwartet
            # ganze Zahlen 0..255.
            bild = np.asarray(srgb_to_linear(
                cv2.cvtColor(roh, cv2.COLOR_BGR2RGB)), dtype=np.float32)
    except Exception:
        return None, 0.0
    h, w = bild.shape[:2]
    if w > breite:
        hoehe = max(1, int(round(h * breite / float(w))))
        bild = cv2.resize(bild, (breite, hoehe), interpolation=cv2.INTER_AREA)
    obergrenze = float(np.percentile(bild, 99.5))
    if obergrenze > 1e-6:
        bild = bild / obergrenze
    return np.clip(bild, 0.0, 1.0).astype(np.float32), obergrenze


def vorschau_basis(pfad, breite=VORSCHAU_BREITE):
    """Wie vorschau_basis_pegel(), nur das Bild."""
    return vorschau_basis_pegel(pfad, breite)[0]


# Ab wann ein helles Pixel als verfaerbt gilt: der Abstand zwischen
# staerkstem und schwaechstem Kanal, bezogen auf 0..1.
HL_FARBSTICH_SCHWELLE = 0.12
HL_HELL_SCHWELLE = 0.93          # ab hier zaehlt ein Pixel als "Licht"
# Die Naeherungsvorschau zieht jedes Bild auf volle Helligkeit. Lagen die
# hellsten Stellen in Wahrheit darunter, ist dort nichts ausgebrannt - und
# eine Farbe in den Lichtern ist dann einfach die Farbe des Motivs.
HL_PEGEL_SCHWELLE = 0.80
# Echte Vorschau: so lange muessen die Regler ruhen, bevor die Engine
# losgeschickt wird, und so viele fertige Bilder bleiben im Speicher.
ECHT_WARTEZEIT_MS = 600
ECHT_MERKER_MAX = 16


# Ein Kanal gilt als "am Anschlag", ab diesem Wert (0..1).
HL_ANSCHLAG = 0.96


def lichter_farbstich(bild, linear=True):
    """
    Sucht den rosa Sonnenball: Stellen, an denen Rot UND Blau am Anschlag
    stehen, Gruen aber deutlich zurueckbleibt.

    So entsteht er: im Kern der Sonne laeuft Gruen auf dem Sensor zuerst
    voll, die Faktoren des Weissabgleichs heben Rot und Blau danach weiter
    an - heraus kommt Magenta statt Weiss.

    Bisher zaehlte jede helle Stelle, deren Kanaele auseinanderliefen.
    Damit schlug die Warnung bei jedem Abendhimmel an: ein kraeftiges
    Orange (255, 200, 130) ist hell und bunt, aber eine echte Farbe und
    kein Fehler. An zwei Referenzbildern meldete die alte Pruefung 82 und
    99 % der hellen Stellen als "verfaerbt", obwohl dort kein einziger
    Bildpunkt ausgebrannt war.

    bild    (H, W, 3) in RGB, float 0..1 wenn linear=True, sonst uint8
    Rueckgabe: (anteil_heller_pixel_verfaerbt, anteil_am_ganzen_bild,
                'magenta' oder '')
    """
    if bild is None or getattr(bild, 'size', 0) == 0:
        return 0.0, 0.0, ""
    b = np.asarray(bild, dtype=np.float32)
    if not linear:
        b = b / 255.0
    hoch = b.max(axis=2)
    hell = hoch >= HL_HELL_SCHWELLE
    n_hell = int(np.count_nonzero(hell))
    if n_hell == 0:
        return 0.0, 0.0, ""
    r, g, bl = b[..., 0], b[..., 1], b[..., 2]
    verfaerbt = (hell & (r >= HL_ANSCHLAG) & (bl >= HL_ANSCHLAG - 0.08)
                 & ((np.minimum(r, bl) - g) >= HL_FARBSTICH_SCHWELLE))
    n_bunt = int(np.count_nonzero(verfaerbt))
    if n_bunt == 0:
        return 0.0, 0.0, ""
    gesamt = float(b.shape[0] * b.shape[1])
    return n_bunt / float(n_hell), n_bunt / gesamt, 'magenta'


def ausgebrannt_anteil(bild_bgr8):
    """
    Anteil ausgebrannter Bildpunkte in einem 8-Bit-Bild (Vorschau-JPEG).

    Ausgebrannt heisst: mindestens ZWEI Kanaele am Anschlag - Weiss, Gelb
    oder Rosa. Ein einzelner Kanal am Anschlag ist meist eine kraeftige
    Farbe, die nur ueber den Farbraum des JPEGs hinausgeht, etwa das
    Rot eines Abendhimmels; im RAW ist dort noch alles da.
    """
    if bild_bgr8 is None or getattr(bild_bgr8, 'size', 0) == 0:
        return 0.0
    zweit = np.sort(np.asarray(bild_bgr8), axis=2)[..., 1]
    return float((zweit >= 245).mean())


def lichter_ausbleichen(linear, staerke=1.0, einsatz=0.85):
    """
    Naeherung der Lichter-Rekonstruktion fuer die Vorschau.

    Zieht die Kanaele in den hellsten Stellen zum staerksten Kanal hin,
    bis dort Weiss steht. Das ist nicht das Verfahren der Engine - die
    rechnet den fehlenden Kanal aus der Umgebung - aber es zeigt
    zuverlaessig, ob der Farbstich verschwindet.
    """
    b = np.asarray(linear, dtype=np.float32)
    if staerke <= 0:
        return b
    hoch = b.max(axis=2, keepdims=True)
    gewicht = np.clip((hoch - einsatz) / max(1e-6, 1.0 - einsatz), 0.0, 1.0)
    gewicht = gewicht * float(min(1.0, max(0.0, staerke)))
    return b * (1.0 - gewicht) + hoch * gewicht


def histogramm_bild(rgb, breite, hoehe, hintergrund=(26, 29, 35),
                    gitterfarbe=(70, 74, 82)):
    """
    Zeichnet ein RGB-Histogramm als Bild.

    Die Hoehe ist auf den hoechsten Wert aller drei Kanaele bezogen, nicht
    je Kanal einzeln - sonst sieht ein schwach besetzter Kanal genauso
    hoch aus wie ein starker und das Bild luegt ueber die Farbverteilung.

    Der oberste und unterste Balken sind ausgenommen: reines Schwarz und
    reines Weiss haeufen sich bei jedem Bild und wuerden die Skala
    zusammendruecken. Stattdessen markieren zwei senkrechte Streifen an
    den Raendern, wenn dort beschnitten wird.
    """
    bild = np.full((hoehe, breite, 3), hintergrund, dtype=np.uint8)
    for anteil in (0.25, 0.5, 0.75):
        x = int(anteil * (breite - 1))
        bild[:, x] = gitterfarbe
    if rgb is None or rgb.size == 0:
        return bild
    farben = ((255, 80, 80), (80, 220, 110), (90, 150, 255))
    # Immer 256 Balken rechnen - einen je moeglichem Wert - und erst
    # danach auf die Zeichenbreite bringen. Direkt mit 300 Balken ueber
    # 256 Werte bliebe jeder sechste leer und das Bild saehe aus wie ein
    # Kamm, obwohl die Verteilung glatt ist.
    hists = [cv2.calcHist([rgb], [k], None, [256], [0, 256]).flatten()
             for k in range(3)]

    # Beschnitt zuerst: bei einem durchweg schwarzen oder weissen Bild
    # sind die inneren Balken leer, und genau dann ist die Warnung am
    # wichtigsten.
    gesamt = float(rgb.shape[0] * rgb.shape[1])
    if gesamt > 0:
        tief = sum(float(h[0]) for h in hists) / (3.0 * gesamt)
        hell = sum(float(h[-1]) for h in hists) / (3.0 * gesamt)
        if tief > 0.005:
            bild[:, :2] = (90, 140, 255)
        if hell > 0.005:
            bild[:, -2:] = (255, 90, 90)

    # Leicht glaetten, bevor die Hoehe bestimmt wird. Ein JPEG - und die
    # echte Vorschau der Engine ist eines - besetzt durch die Kompression
    # einzelne Tonwerte gehaeuft. Diese Zacken bestimmten bisher die Skala:
    # kam das Bild der Engine, sackten alle Kurven ab, obwohl sich die
    # Verteilung kaum geaendert hatte.
    if max(float(h[1:-1].max()) for h in hists) <= 0:
        return bild
    kern = np.exp(-0.5 * (np.arange(-4, 5) / 1.5) ** 2)
    kern /= kern.sum()
    geglaettet = []
    for h in hists:
        h = h.astype(np.float64)
        innen = np.convolve(np.pad(h[1:-1], 4, mode='edge'), kern, mode='valid')
        geglaettet.append(np.concatenate(([h[0]], innen, [h[-1]])))
    hists = geglaettet
    hoechster = max((float(h[1:-1].max()) for h in hists), default=0.0)
    if hoechster <= 0:
        return bild
    x_ziel = np.linspace(0, 255, breite)
    for h, farbe in zip(hists, farben):
        y = np.interp(x_ziel, np.arange(256), np.clip(h / hoechster, 0.0, 1.0))
        punkte = np.column_stack((np.arange(breite),
                                  (hoehe - 1 - y * (hoehe - 3)).astype(np.int32)))
        cv2.polylines(bild, [punkte], False, farbe, 1, cv2.LINE_AA)
    return bild


# ==========================================================================
#  AUTOMATISCH OPTIMIEREN
#
#  Schlaegt Reglerwerte vor, gemessen am Bild - nicht geraten. Zielbild
#  ist ein knackiges, heutiges Ergebnis: offene Tiefen, Zeichnung in den
#  Lichtern, kraeftige aber nicht grelle Farben, sichtbare Schaerfe ohne
#  Saeume.
#
#  Was dieses Ziel AUSSCHLIESST, ist genauso wichtig: ein kraeftiger
#  globaler Kontrast, der die Tiefen zudrueckt, und eine hochgezogene
#  Saettigung obendrauf - diese Kombination ist das, was alt aussieht.
#  Deshalb sind beide gedeckelt, und die Saettigung wird zurueckgenommen,
#  wenn schon viel Kontrast dazukommt.
#
#  Der Weissabgleich bleibt mit Absicht unberuehrt. Ob ein warmes Bild ein
#  Sonnenuntergang oder ein Fehlgriff der Automatik ist, laesst sich aus
#  einem einzelnen Bild nicht entscheiden - eine Korrektur wuerde genau
#  die Abendstimmung wegrechnen, derentwegen man ueberhaupt filmt.
# ==========================================================================
AUTO_HELLIGKEIT_ZIEL = 0.44     # angestrebter Mittelwert in der Anzeige
AUTO_HELLIGKEIT_MAX = 25        # Reglerausschlag, der hoechstens kommt
AUTO_KONTRAST_MAX = 28
AUTO_SPANNE_GENUG = 0.88        # ab hier ist das Histogramm weit genug
AUTO_SPANNE_ZIEL = 0.92         # darauf wird gestreckt, wenn Luft ist
AUTO_SAETTIGUNG_MAX = 25
AUTO_SCHAERFE_GLATT = 240       # ruhiges Motiv: weniger, sonst Saeume
AUTO_SCHAERFE_DETAIL = 380      # viel Struktur: vertraegt mehr


def _luma_anzeige(basis_linear):
    """Helligkeit in der Anzeige-Kennlinie, wie das Auge sie sieht."""
    a = srgb_kodieren(np.asarray(basis_linear, dtype=np.float32))
    return (a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722), a


def _entrauschen_aus_iso(iso):
    """
    Entrauschen nach ISO-Wert.

    Nicht am Bild gemessen, sondern an der Aufnahme: in einer 520 Pixel
    breiten Vorschau ist das Korn weggerechnet, eine Messung daran waere
    wertlos. Der ISO-Wert aus den EXIF-Daten sagt es verlaesslicher.
    """
    try:
        i = float(iso)
    except (TypeError, ValueError):
        return 0.0, 15.0
    if i <= 200:
        return 0.0, 15.0
    stufen = [(400, 5.0, 15.0), (800, 10.0, 18.0), (1600, 18.0, 22.0),
              (3200, 28.0, 28.0), (6400, 38.0, 35.0)]
    for grenze, lum, chrom in stufen:
        if i <= grenze:
            return lum, chrom
    return 45.0, 40.0


def auto_optimieren(basis_linear, iso=100, erlaubt=None, lang='de'):
    """
    Schlaegt Werte fuer die Schnelleinstellungen vor.

    basis_linear  lineares Vorschaubild (H, W, 3), 0..1
    iso           ISO-Wert der Aufnahme, fuer das Entrauschen
    erlaubt       Menge der Regler-Kennungen, die das Profil kennt;
                  None heisst alle
    lang          Sprache der Begruendungen ('de' oder 'en')

    Rueckgabe: ({id: Wert}, [Begruendung je Entscheidung])

    Jeder Wert kommt aus einer Messung, und jede Messung steht in der
    Begruendung mit ihrer Zahl. Wer das Ergebnis nicht mag, soll sehen
    koennen, worauf es beruht.
    """
    if basis_linear is None:
        return {}, []
    erlaubt = None if erlaubt is None else set(erlaubt)

    def darf(kid):
        return erlaubt is None or kid in erlaubt

    luma, anzeige = _luma_anzeige(basis_linear)
    werte, grund = {}, []
    en = (lang == 'en')

    def sag(de, en_text):
        grund.append(en_text if en else de)

    # ---- Helligkeit: Mittelwert auf einen brauchbaren Mittelton -------
    mittel = float(np.median(luma))
    if darf('brightness') and mittel > 1e-4:
        stufen = math.log2(max(1e-4, AUTO_HELLIGKEIT_ZIEL) / mittel)
        hell = max(-AUTO_HELLIGKEIT_MAX,
                   min(AUTO_HELLIGKEIT_MAX, stufen * 66.0))
        if abs(hell) >= 2.0:
            werte['brightness'] = round(hell)
            sag(f"Helligkeit {werte['brightness']:+.0f}: Mittelton "
                f"liegt bei {mittel:.2f}, angestrebt {AUTO_HELLIGKEIT_ZIEL:.2f}",
                f"Brightness {werte['brightness']:+.0f}: midtone is "
                f"{mittel:.2f}, target {AUTO_HELLIGKEIT_ZIEL:.2f}")
        else:
            sag(f"Helligkeit unveraendert: Mittelton {mittel:.2f} passt bereits",
                f"Brightness unchanged: midtone {mittel:.2f} already fits")

    # ---- Kontrast: nur so viel, wie Luft im Histogramm ist ------------
    p2, p98 = (float(x) for x in np.percentile(luma, (2.0, 98.0)))
    spanne = max(1e-3, p98 - p2)
    if darf('contrast'):
        if spanne >= AUTO_SPANNE_GENUG:
            sag(f"Kontrast unveraendert: Histogramm nutzt schon {spanne:.2f} der Skala",
                f"Contrast unchanged: histogram already uses {spanne:.2f} of the range")
        else:
            k = min(1.45, AUTO_SPANNE_ZIEL / spanne)
            kontrast = max(0.0, min(AUTO_KONTRAST_MAX, 100.0 * math.log2(k)))
            # Unter fuenf Punkten sieht man den Unterschied nicht; so ein
            # Vorschlag setzt nur ein Haekchen ohne Wirkung.
            if kontrast >= 5.0:
                werte['contrast'] = round(kontrast)
                sag(f"Kontrast {werte['contrast']:+.0f}: Histogramm "
                    f"nutzt nur {spanne:.2f} der Skala",
                    f"Contrast {werte['contrast']:+.0f}: histogram "
                    f"uses only {spanne:.2f} of the range")

    # ---- Saettigung: was fehlt, nicht was moeglich ist ----------------
    if darf('saturation'):
        bunt = float(np.mean(anzeige.max(axis=2) - anzeige.min(axis=2)))
        if bunt >= 0.28:
            sag(f"Saettigung unveraendert: Bild ist mit {bunt:.2f} schon farbkraeftig",
                f"Saturation unchanged: at {bunt:.2f} the image is already colourful")
        else:
            anteil = (0.28 - bunt) / 0.28
            sat = AUTO_SAETTIGUNG_MAX * min(1.0, max(0.0, anteil))
            # Kontrast hebt die Farbigkeit mit an. Beides voll aufzudrehen
            # ergibt den grellen Eindruck, den wir vermeiden wollen.
            sat *= max(0.4, 1.0 - werte.get('contrast', 0) / 50.0)
            if sat >= 2.0:
                werte['saturation'] = round(sat)
                gedaempft = werte.get('contrast', 0) > 10
                sag(f"Saettigung {werte['saturation']:+.0f}: "
                    f"Farbabstand liegt bei {bunt:.2f}"
                    + (" (wegen des Kontrasts gedaempft)" if gedaempft else ""),
                    f"Saturation {werte['saturation']:+.0f}: "
                    f"colour spread is {bunt:.2f}"
                    + (" (damped because of the contrast)" if gedaempft else ""))

    # ---- Schaerfe: wie viel Struktur traegt das Motiv? ----------------
    if darf('sharpen'):
        weich = cv2.GaussianBlur(luma, (0, 0), 1.6)
        struktur = float(np.std(luma - weich))
        anteil = min(1.0, max(0.0, (struktur - 0.012) / 0.030))
        scharf = (AUTO_SCHAERFE_GLATT
                  + (AUTO_SCHAERFE_DETAIL - AUTO_SCHAERFE_GLATT) * anteil)
        werte['sharpen'] = int(round(scharf))
        ruhig = anteil < 0.34
        sag(f"Schaerfe {werte['sharpen']}: Strukturmass {struktur:.3f}"
            + (" (ruhiges Motiv, zurueckhaltend)" if ruhig
               else " (viel Struktur, traegt mehr)"),
            f"Sharpening {werte['sharpen']}: structure measure {struktur:.3f}"
            + (" (calm subject, restrained)" if ruhig
               else " (lots of structure, takes more)"))

    # ---- Entrauschen: nach ISO, nicht nach der Vorschau ---------------
    lum_n, chrom_n = _entrauschen_aus_iso(iso)
    if darf('denoise_l'):
        werte['denoise_l'] = lum_n
        if lum_n <= 0:
            sag(f"Entrauschen aus: ISO {iso} braucht keines",
                f"Noise reduction off: ISO {iso} needs none")
        else:
            sag(f"Entrauschen {lum_n:.0f}: ISO {iso}",
                f"Noise reduction {lum_n:.0f}: ISO {iso}")
    if darf('denoise_c') and lum_n > 0:
        werte['denoise_c'] = chrom_n

    # ---- Verfaerbte Lichter ------------------------------------------
    anteil, am_bild, richtung = lichter_farbstich(basis_linear)
    if anteil > 0.15 and am_bild > 0.0002:
        werte['_hl'] = True
        sag(f"Lichter rekonstruieren: {100 * anteil:.0f} % der "
            "hellsten Stellen sind rosa verfaerbt",
            f"Reconstruct highlights: {100 * anteil:.0f} % of the "
            "brightest areas are tinted pink")
    elif anteil > 0:
        sag(f"Lichter in Ordnung: nur {100 * anteil:.0f} % der "
            "hellsten Stellen zeigen einen Farbstich",
            f"Highlights fine: only {100 * anteil:.0f} % of the "
            "brightest areas show a colour cast")

    sag("Weissabgleich unveraendert - aus einem Bild laesst sich "
        "nicht entscheiden, ob die Farbstimmung gewollt ist",
        "White balance unchanged - a single image cannot tell whether "
        "the colour mood is intended")
    return werte, grund


# Ab wie vielen Bildern die Punktsymbole der Messkurve verschwinden.
# Darueber liegen die Punkte dichter als ein Pixel und machen aus der
# Kurve ein breites Band.
SYMBOL_GRENZE = 150


def stift(farbe, breite=2, style=None):
    """
    Zeichenstift mit runden Enden und Verbindungen.

    Ohne das stossen die Liniensegmente mit eckigen Kanten aneinander,
    was bei einer dicken Linie an jedem Messpunkt als kleine Ecke
    sichtbar wird.
    """
    p = pg.mkPen(farbe, width=breite)
    p.setCapStyle(QtCore.Qt.RoundCap)
    p.setJoinStyle(QtCore.Qt.RoundJoin)
    if style is not None:
        p.setStyle(style)
    return p


def dauer_text(sekunden):
    """Sekunden als m:ss, ab einer Stunde als h:mm:ss."""
    try:
        sek = max(0, int(round(float(sekunden))))
    except (TypeError, ValueError):
        return "--:--"
    std, rest = divmod(sek, 3600)
    mins, sek = divmod(rest, 60)
    if std:
        return f"{std}:{mins:02d}:{sek:02d}"
    return f"{mins}:{sek:02d}"


def videolaenge_text(sekunden, lang='de'):
    """Laenge eines Videos fuer Menschen: "29,4 s", "1:05 min", "1:02:10 h"."""
    try:
        s = max(0.0, float(sekunden))
    except (TypeError, ValueError):
        return "--"
    if s < 60:
        zahl = f"{s:.1f}"
        return (zahl if lang == 'en' else zahl.replace(".", ",")) + " s"
    ganz = int(round(s))
    std, rest = divmod(ganz, 3600)
    mins, sek = divmod(rest, 60)
    if std:
        return f"{std}:{mins:02d}:{sek:02d} h"
    return f"{mins}:{sek:02d} min"


def fortschritt_text(label, fertig, gesamt, start_zeit, zusatz="", lang='de'):
    """
    Statuszeile aus Zaehlerstand, verstrichener Zeit, geschaetzter
    Gesamtdauer und Restzeit.

    Vor dem ersten fertigen Bild gibt es keine Grundlage fuer eine
    Schaetzung - dann wird nur die verstrichene Zeit genannt und nicht
    geraten.
    """
    verstrichen = max(0.0, time.time() - start_zeit)
    kopf = f"{label}: {fertig}/{gesamt}" if gesamt else str(label)
    if zusatz:
        kopf += f" | {zusatz}"
    englisch = (lang == 'en')
    if fertig > 0 and gesamt > 0:
        geschaetzt = verstrichen / fertig * gesamt
        rest = max(0.0, geschaetzt - verstrichen)
        if englisch:
            return (f"{kopf} | {dauer_text(verstrichen)} of approx. "
                    f"{dauer_text(geschaetzt)} | {dauer_text(rest)} left")
        return (f"{kopf} | {dauer_text(verstrichen)} von ca. "
                f"{dauer_text(geschaetzt)} | Rest {dauer_text(rest)}")
    if englisch:
        return f"{kopf} | {dauer_text(verstrichen)} | total duration not yet known"
    return f"{kopf} | {dauer_text(verstrichen)} | Gesamtdauer noch unbekannt"


# ==========================================================================
#  ABLAUF EINES LAUFS
#
#  Waehrend ein Video entsteht, will man drei Dinge auf einen Blick sehen:
#  was erledigt ist, was gerade laeuft, was noch kommt - jeweils mit Zeit.
#  Der Worker meldet seinen Stand als Statuszeile ("Entwicklung: 12/963 |
#  ..."). Daraus wird hier der Ablauf abgeleitet; am Worker selbst aendert
#  sich dafuer nichts.
# ==========================================================================
def status_zerlegen(text):
    """
    Zerlegt eine Statuszeile des Workers.

    Rueckgabe: (Bezeichnung, fertig, gesamt, Zusatz)
    "Entwicklung: 12/963 | 0:10 von ca. 9:00 | Rest 8:50"
        -> ("Entwicklung", 12, 963, "")
    "Schreibe Sidecar: IMG_0001.NEF" -> ("Schreibe Sidecar", 0, 0, "")
    """
    teile = [t.strip() for t in str(text or "").split(" | ")]
    kopf = teile[0]
    zusatz = " | ".join(teile[1:-2]) if len(teile) > 3 else ""
    m = re.match(r"^(.*?):\s*(\d+)\s*/\s*(\d+)$", kopf)
    if m:
        return m.group(1).strip(), int(m.group(2)), int(m.group(3)), zusatz
    return kopf.split(":")[0].rstrip(". ").strip(), 0, 0, zusatz


def status_kurz(text, lang='de'):
    """
    Die Statuszeile ohne die Zeitangaben - die stehen im Ablauf darunter.
    "Entwicklung: 12/963 | 0:10 von ca. 9:00 | Rest 8:50"
        -> "Entwicklung  ·  12 von 963"
    Alles, was nicht nach diesem Muster gebaut ist, bleibt wie es ist.
    """
    teile = [t.strip() for t in str(text or "").split(" | ")]
    if len(teile) < 3:
        return status_sprache(text, lang)
    label, fertig, gesamt, zusatz = status_zerlegen(text)
    kurz = status_sprache(label, lang)
    if gesamt:
        kurz += (f"  ·  {fertig} of {gesamt}" if lang == 'en'
                 else f"  ·  {fertig} von {gesamt}")
    if zusatz:
        kurz += f"  ·  {zusatz}"
    return kurz


# Statusmeldungen ohne Zaehler, die der Worker auf Deutsch schickt. Der
# Worker meldet intern immer deutsch, weil die Ablaufanzeige die Phase am
# deutschen Anfang erkennt (PHASEN); uebersetzt wird erst fuer die Anzeige.
STATUS_EN = (
    ("Vergleichsvideo wird erstellt", "Creating comparison video"),
    ("Erzeuge einmalig ein Basisprofil", "Creating a base profile (only once)"),
    ("Schreibe Sidecar", "Writing sidecar"),
    ("Suche defekte Pixel", "Finding defective pixels"),
)


def status_sprache(text, lang='de'):
    """
    Der Anfang einer Statuszeile in der Sprache der Oberflaeche.
    "Analysiere RAWs: 12/56" -> "Measure RAWs: 12/56" (englisch),
    "Nachkalibrierung 2" -> "Recalibration 2". Unbekanntes bleibt, wie es ist.
    """
    text = str(text or "")
    if lang != 'en':
        return text
    for de, en in STATUS_EN:
        if text.startswith(de):
            return en + text[len(de):]
    for praefix, _k, _de, en in PHASEN:
        if text.startswith(praefix):
            return en + text[len(praefix):]
    return text


# Anfang der Bezeichnung -> (Schluessel, Titel deutsch, Titel englisch)
PHASEN = [
    ("Erzeuge einmalig ein Basisprofil", 'basis', "Basisprofil", "Base profile"),
    ("Suche defekte Pixel", 'pixel', "Defekte Pixel suchen", "Find dead pixels"),
    ("Lese Daten", 'lesen', "Bilder messen", "Measure frames"),
    ("Analysiere RAWs", 'analyse', "RAWs messen", "Measure RAWs"),
    ("Schreibe Sidecar", 'schreiben', "Profile schreiben", "Write profiles"),
    ("Entwicklung", 'entwicklung', "Entwicklung", "Development"),
    ("Messe Ergebnis", 'messung', "Ergebnis messen", "Measure result"),
    ("Nachkalibrierung", 'kalib', "Nachkalibrierung", "Recalibration"),
    ("Analysiere Kamera-Wackeln", 'stab', "Stabilisierung", "Stabilisation"),
    ("Rendere Video", 'video', "Video rendern", "Render video"),
    ("Rohfassung", 'roh', "Rohfassung", "Plain version"),
    ("Vergleichsvideo", 'vergleich', "Vergleichsvideo", "Comparison video"),
    ("Schnellvorschau lesen", 'schnell_lesen', "Vorschaubilder lesen", "Read previews"),
    ("Schnellvorschau Video", 'schnell_video', "Video erzeugen", "Encode video"),
]


def phase_titel(key, lang='de'):
    for _anfang, k, de, en in PHASEN:
        if k == key:
            return en if lang == 'en' else de
    return str(key)


def phase_schluessel(label):
    """Zu welchem Schritt gehoert diese Bezeichnung? Unbekanntes bildet
    einen eigenen Schritt und wird unter seinem Namen gezeigt."""
    for anfang, key, _de, _en in PHASEN:
        if str(label).startswith(anfang):
            return key
    return str(label)


def ablauf_plan(params):
    """
    Die Schritte, die ein Lauf voraussichtlich durchlaeuft.

    Nur eine Vorschau fuer die Anzeige: kommt ein Schritt nicht vor, wird
    er als "nicht noetig" gezeigt, kommt ein unerwarteter hinzu, reiht er
    sich ein. Der Worker richtet sich nicht nach diesem Plan.
    """
    p = params or {}
    modus = p.get('mode', 'normal')
    if modus == 'plain':
        return ['roh']
    if modus == 'compare':
        return ['vergleich']
    if modus == 'schnell':
        return ['schnell_lesen', 'schnell_video']
    if modus == 'preview':
        return []
    video = bool(p.get('make_video', True))
    if p.get('format') != 'raw':
        plan = ['lesen']
        if video and p.get('stabilize'):
            plan.append('stab')
        if video:
            plan.append('video')
        return plan
    if p.get('raw_mode') == 'pass1':
        return ['analyse', 'schreiben']
    plan = ['entwicklung', 'messung']
    try:
        if int(p.get('calib_rounds', 2)) > 0:
            plan.append('kalib')
    except (TypeError, ValueError):
        pass
    if video and p.get('stabilize'):
        plan.append('stab')
    if video:
        plan.append('video')
    return plan


class Ablauf:
    """
    Der zeitliche Ablauf eines Laufs.

    Zustaende je Schritt: 'offen', 'aktiv', 'fertig', 'entfallen', 'fehler'.
    Reine Buchfuehrung ohne Oberflaeche - gezeichnet wird in AblaufLeiste.
    """

    def __init__(self, plan=None, jetzt=None):
        self.start = time.time() if jetzt is None else jetzt
        self.ende = None
        self.erfolg = None
        self.schritte = [self._neu(k) for k in (plan or [])]

    @staticmethod
    def _neu(key):
        return {'key': key, 'zustand': 'offen', 'dauer': 0.0, 'seit': None,
                'beginn': None, 'ende': None, 'label': "", 'teil_seit': None,
                'fertig': 0, 'gesamt': 0, 'runde': 0}

    def aktiver(self):
        for s in self.schritte:
            if s['zustand'] == 'aktiv':
                return s
        return None

    def melde(self, label, fertig=0, gesamt=0, jetzt=None):
        """Eine Statuszeile ist eingetroffen."""
        if self.ende is not None or not label:
            return
        jetzt = time.time() if jetzt is None else jetzt
        key = phase_schluessel(label)
        # Die Messungen nach einer Nachkalibrierung gehoeren zu dieser.
        if key == 'messung' and any(s['key'] == 'kalib' and s['zustand'] != 'offen'
                                    for s in self.schritte):
            key = 'kalib'
        akt = self.aktiver()
        if akt is None or akt['key'] != key:
            if akt is not None:
                self._beenden(akt, 'fertig', jetzt)
            idx = next((i for i, s in enumerate(self.schritte) if s['key'] == key), None)
            if idx is None:
                # Unerwarteter Schritt: hinter den letzten begonnenen.
                idx = 0
                for i, s in enumerate(self.schritte):
                    if s['zustand'] != 'offen':
                        idx = i + 1
                self.schritte.insert(idx, self._neu(key))
            for s in self.schritte[:idx]:
                if s['zustand'] == 'offen':
                    s['zustand'] = 'entfallen'
            akt = self.schritte[idx]
            akt['zustand'] = 'aktiv'
            akt['seit'] = jetzt
            if akt['beginn'] is None:
                akt['beginn'] = jetzt
            akt['label'] = ""
        if akt['label'] != label:
            # Neuer Teilschritt: die Restzeit rechnet ab hier.
            akt['label'] = label
            akt['teil_seit'] = jetzt
            m = re.search(r"(\d+)\s*$", str(label))
            if key == 'kalib' and m and str(label).startswith("Nachkalibrierung"):
                akt['runde'] = int(m.group(1))
        akt['fertig'], akt['gesamt'] = int(fertig or 0), int(gesamt or 0)

    def _beenden(self, s, zustand, jetzt):
        if s['seit'] is not None:
            s['dauer'] += max(0.0, jetzt - s['seit'])
        s['seit'] = None
        s['ende'] = jetzt
        s['zustand'] = zustand

    def abschliessen(self, erfolg=True, jetzt=None):
        """Der Lauf ist zu Ende - gut oder nicht."""
        if self.ende is not None:
            return
        jetzt = time.time() if jetzt is None else jetzt
        akt = self.aktiver()
        if akt is not None:
            self._beenden(akt, 'fertig' if erfolg else 'fehler', jetzt)
        if erfolg:
            for s in self.schritte:
                if s['zustand'] == 'offen':
                    s['zustand'] = 'entfallen'
        self.ende = jetzt
        self.erfolg = bool(erfolg)

    def dauer(self, s, jetzt=None):
        """Bisherige Dauer eines Schritts in Sekunden."""
        jetzt = time.time() if jetzt is None else jetzt
        laufend = (jetzt - s['seit']) if s['seit'] is not None else 0.0
        return max(0.0, s['dauer'] + laufend)

    def rest(self, s, jetzt=None):
        """Geschaetzte Restzeit des laufenden Teilschritts, oder None."""
        if s['zustand'] != 'aktiv' or s['teil_seit'] is None:
            return None
        if s['fertig'] <= 0 or s['gesamt'] <= 0:
            return None
        jetzt = time.time() if jetzt is None else jetzt
        je = max(0.0, jetzt - s['teil_seit']) / s['fertig']
        return max(0.0, je * (s['gesamt'] - s['fertig']))

    def gesamt_dauer(self, jetzt=None):
        ende = self.ende if self.ende is not None else (
            time.time() if jetzt is None else jetzt)
        return max(0.0, ende - self.start)


def uhrzeit(zeitpunkt):
    """Sekunden seit 1970 als Uhrzeit HH:MM."""
    try:
        return datetime.datetime.fromtimestamp(float(zeitpunkt)).strftime("%H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return "--:--"


def ablauf_texte(ablauf, s, lang='de', jetzt=None):
    """
    Beschriftung eines Schritts fuer die Anzeige.
    Rueckgabe: (Titelzeile, Zeitzeile, Hinweis fuer den Tooltip)
    """
    en = (lang == 'en')
    titel = phase_titel(s['key'], lang)
    if s['runde'] and s['zustand'] == 'aktiv':
        titel += f" ({'round' if en else 'Runde'} {s['runde']})"
    z = s['zustand']
    d = dauer_text(ablauf.dauer(s, jetzt))
    tip = ""
    if s['beginn'] is not None:
        tip = (f"started {uhrzeit(s['beginn'])}" if en
               else f"begonnen {uhrzeit(s['beginn'])}")
        if s['ende'] is not None and z != 'aktiv':
            tip += (f", finished {uhrzeit(s['ende'])}" if en
                    else f", beendet {uhrzeit(s['ende'])}")
    if z == 'fertig':
        return ("✓  " + titel,
                f"{d}  ·  {'until' if en else 'bis'} {uhrzeit(s['ende'])}", tip)
    if z == 'aktiv':
        rest = ablauf.rest(s, jetzt)
        zeit = f"{'for' if en else 'seit'} {d}"
        if rest is not None:
            zeit += (f"  ·  approx. {dauer_text(rest)} left" if en
                     else f"  ·  Rest ca. {dauer_text(rest)}")
        if s['gesamt']:
            tip += f"\n{s['fertig']} / {s['gesamt']}"
        return ("●  " + titel, zeit, tip.strip())
    if z == 'fehler':
        return ("✕  " + titel,
                f"{'stopped after' if en else 'abgebrochen nach'} {d}", tip)
    if z == 'entfallen':
        return ("–  " + titel, "not needed" if en else "nicht nötig", tip)
    return ("○  " + titel, "pending" if en else "steht aus", tip)


def ablauf_kopf(ablauf, lang='de', jetzt=None):
    """Die Zeile rechts neben dem Status: Beginn, Dauer, Ende."""
    if ablauf is None:
        return ""
    en = (lang == 'en')
    d = dauer_text(ablauf.gesamt_dauer(jetzt))
    if ablauf.ende is None:
        return (f"started {uhrzeit(ablauf.start)}  ·  running for {d}" if en
                else f"gestartet {uhrzeit(ablauf.start)}  ·  läuft seit {d}")
    return (f"{uhrzeit(ablauf.start)} – {uhrzeit(ablauf.ende)}  ·  took {d}" if en
            else f"{uhrzeit(ablauf.start)} – {uhrzeit(ablauf.ende)}  ·  Dauer {d}")


# ==========================================================================
#  PROTOKOLL
#
#  Jede Meldung bekommt Datum und Uhrzeit. Ueberschriften, Warnungen,
#  Fehler und Erfolgsmeldungen sind farblich abgesetzt, lange Befehlszeilen
#  treten zurueck. Der Wortlaut der Meldungen bleibt, wie er ist.
# ==========================================================================
LOG_PROMPT = "purelapse@engine:~$"


def log_art(zeile):
    """Ordnet eine Protokollzeile ein. Rueckgabe: (Art, anzuzeigender Text)"""
    roh = str(zeile).rstrip()
    if roh.startswith(LOG_PROMPT):
        text = roh[len(LOG_PROMPT):].strip()
        gross = text.upper()
        if "FEHLER" in gross or "ABBRUCH" in gross:
            return 'fehler', text
        return 'kopf', text
    eingerueckt = roh.startswith("    ") or roh.startswith("\t")
    text = roh.strip()
    if text.startswith("> "):
        text = text[2:].strip()
    elif text == ">":
        text = ""
    gross = text.upper()
    if gross.startswith("[FEHLER]") or gross.startswith("FEHLER") or gross.startswith("ERROR"):
        return 'fehler', text
    if gross.startswith(("WARNUNG", "ACHTUNG", "WARNING")):
        return 'warnung', text
    if eingerueckt:
        return 'fort', text
    if ("ffmpeg" in text and " -" in text) or "-cli" in text and " -" in text:
        return 'befehl', text
    if (text.startswith(("Fertig", "Erfolg", "Ziel erreicht", "Done", "Target reached"))
            or "✔" in text or "erfolgreich" in text.lower()):
        return 'ok', text
    return 'text', text


LOG_ZEICHEN = {'fehler': "✕ ", 'warnung': "⚠ ", 'ok': "✓ ",
               'kopf': "▸ "}


def log_stempel(wann):
    """Datum und Uhrzeit einer Meldung: 16.11. 21:04:13"""
    return wann.strftime("%d.%m. %H:%M:%S")


def log_html(msg, wann, farben):
    """
    Eine Meldung als HTML fuer das Protokollfenster.

    Die erste Zeile traegt Datum und Uhrzeit, Folgezeilen sind eingerueckt.
    Leerzeilen, die bisher nur als Abstand dienten, entfallen - den
    Abstand macht jetzt die Ueberschrift selbst.
    """
    t = farben
    farbe = {'kopf': t['text'], 'fehler': t['err'], 'warnung': t['warn'],
             'ok': t['ok'], 'befehl': t['faint'], 'fort': t['dim'],
             'text': t['log_fg']}
    stempel = log_stempel(wann)
    leer = "&nbsp;" * len(stempel)
    aus = []
    erste = True
    for zeile in str(msg).split("\n"):
        if not zeile.strip():
            continue
        art, text = log_art(zeile)
        if not text:
            continue
        inhalt = html.escape(LOG_ZEICHEN.get(art, "") + text).replace("  ", "&nbsp; ")
        if art == 'fort':
            inhalt = "&nbsp;&nbsp;" + inhalt
        fett = "font-weight:bold;" if art in ('kopf', 'fehler') else ""
        kopf = (f'<span style="color:{t["faint"]};">{stempel}</span>'
                if erste else leer)
        aus.append(f'{kopf}&nbsp;&nbsp;<span style="color:{farbe[art]};{fett}">'
                   f'{inhalt}</span>')
        erste = False
    return "<br>".join(aus)


# ==========================================================================
#  PARALLELE ENTWICKLUNG
#
#  ART und RawTherapee parallelisieren die Entwicklung EINES Bildes intern.
#  Das skaliert aber nur bis etwa vier bis acht Threads: Teile der Kette
#  sind einstraengig, und am Ende jeder Stufe warten alle Threads
#  aufeinander. Mehrere Prozesse mit je wenigen Threads lasten eine
#  vielkernige Maschine deshalb deutlich besser aus als ein Prozess, der
#  alle Kerne bekommt.
#
#  Begrenzt wird das von drei Dingen: der eingestellten Kernzahl, dem
#  freien Arbeitsspeicher (jede Instanz haelt ein ganzes RAW samt
#  Arbeitspuffern) und der Anzahl der Bilder.
# ==========================================================================
THREADS_PRO_PROZESS = 4      # Zielgroesse je Instanz
VIDEO_THREADS_MAX = 4        # Vorauslesen beim Rendern; mehr kostet nur Speicher
DT_MAX_PROZESSE = 4          # darktable-cli: mehr bringt auf einer Grafikkarte nichts
DT_GB_PRO_PROZESS = 3.0      # darktable-cli braucht mehr Speicher als ART
DT_ZEITLIMIT_S = 600         # haengt ein darktable-cli laenger, wird es beendet
GB_PRO_PROZESS = 2.5         # Schaetzung des Speicherbedarfs je Instanz
MAX_PROZESSE = 8             # darueber bringt es erfahrungsgemaess nichts
# Auswahl in der Oberflaeche; 0 bedeutet "automatisch"
PROZESS_WAHL = [0, 1, 2, 3, 4, 6, 8]


def cache_ordner():
    """Zwischenspeicher von Purelapse (keine Einstellungen, nur Wegwerfbares)."""
    if os.name == 'nt':
        basis = os.environ.get('LOCALAPPDATA') or os.path.expanduser("~")
        return os.path.join(basis, "purelapse", "cache")
    basis = os.environ.get('XDG_CACHE_HOME') or os.path.expanduser("~/.cache")
    return os.path.join(basis, "purelapse")


def freier_speicher_gb():
    """Verfuegbarer Arbeitsspeicher in GiB, oder None wenn unbekannt."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for zeile in f:
                if zeile.startswith("MemAvailable:"):
                    return int(zeile.split()[1]) / (1024.0 * 1024.0)
    except (OSError, ValueError, IndexError):
        pass
    if sys.platform.startswith("win"):
        # Windows kennt /proc/meminfo nicht; ohne diese Abfrage liefe die
        # Entwicklung dort ohne Speichergrenze.
        try:
            import ctypes

            class _Speicher(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = _Speicher()
            m.dwLength = ctypes.sizeof(_Speicher)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return m.ullAvailPhys / (1024.0 ** 3)
        except Exception:
            pass
    return None


# ==========================================================================
#  GLEICHZEITIGES MESSEN
#
#  Die Messungen (RAWs in Pass 1, entwickelte JPGs in Pass 2) laufen auf
#  mehreren Kernen. An den ZAHLEN aendert das nichts: jedes Bild wird von
#  derselben Funktion auf dieselbe Weise vermessen wie im Einzellauf, nur
#  eben mehrere zugleich, und die Ergebnisse stehen in Bildreihenfolge.
#
#  Bewusst NICHT gemacht: die Bilder verkleinert zu dekodieren. Das waere
#  noch einmal deutlich schneller, wuerde aber die Messwerte veraendern -
#  und an denen haengt die Entflackerung.
# ==========================================================================
# Unter dieser Streuung (EV) gilt das Ergebnis als ruhig.
RESTFLACKERN_ZIEL = 0.008
MESS_THREADS_MAX = 8          # darueber bremst die Platte, nicht der Rechner
MESS_MB_JE_BILD = 450         # Arbeitsspeicher, den ein Bild beim Messen belegt


def mess_threads(kerne, frei_gb=None):
    """Wie viele Bilder gleichzeitig vermessen werden."""
    n = max(1, min(int(kerne or 1), MESS_THREADS_MAX))
    if frei_gb is None:
        frei_gb = freier_speicher_gb()
    if frei_gb:
        # hoechstens die Haelfte des freien Speichers belegen
        n = min(n, max(1, int(frei_gb * 1024 * 0.5 // MESS_MB_JE_BILD)))
    return n


def parallel_messen(funktion, argumente, threads, pruefe_abbruch=None, melde=None):
    """
    Ruft funktion(*argument) fuer jedes Argument auf, mehrere zugleich.

    Die Ergebnisliste hat dieselbe Reihenfolge wie die Argumente. Ein
    Abbruch wird alle Viertelsekunde geprueft und nimmt die noch nicht
    begonnenen Messungen zurueck.
    """
    n = len(argumente)
    ergebnisse = [None] * n
    if threads <= 1 or n < 2:
        for i, a in enumerate(argumente):
            if pruefe_abbruch:
                pruefe_abbruch()
            ergebnisse[i] = funktion(*a)
            if melde:
                melde(i + 1, n)
        return ergebnisse
    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
        auftraege = [pool.submit(funktion, *a) for a in argumente]
        try:
            for i, auftrag in enumerate(auftraege):
                while True:
                    if pruefe_abbruch:
                        pruefe_abbruch()
                    try:
                        ergebnisse[i] = auftrag.result(timeout=0.25)
                        break
                    except concurrent.futures.TimeoutError:
                        continue
                if melde:
                    melde(i + 1, n)
        except BaseException:
            for auftrag in auftraege:
                auftrag.cancel()
            raise
    return ergebnisse


def prozess_anzahl(n_bilder, kerne, wunsch=0, frei_gb=None):
    """
    Wie viele CLI-Prozesse parallel laufen sollen.

    wunsch=0 heisst automatisch. frei_gb nur fuer die Pruefungen
    einsetzbar; normalerweise wird der Wert selbst ermittelt.
    """
    kerne = max(1, int(kerne))
    n_bilder = max(0, int(n_bilder))
    if n_bilder == 0:
        return 1
    if wunsch and int(wunsch) > 0:
        jobs = int(wunsch)
    else:
        jobs = max(1, kerne // THREADS_PRO_PROZESS)
    jobs = min(jobs, MAX_PROZESSE, kerne, n_bilder)
    if frei_gb is None:
        frei_gb = freier_speicher_gb()
    if frei_gb:
        jobs = min(jobs, max(1, int(frei_gb // GB_PRO_PROZESS)))
    return max(1, jobs)


def bilder_aufteilen(files, jobs):
    """
    Verteilt die Bilder reihum auf die Prozesse: files[i::jobs].

    Reihum und nicht in zusammenhaengenden Bloecken, damit jeder Prozess
    eine Mischung aus hellen und dunklen Aufnahmen bekommt. Bei Bloecken
    haette bei einer Nachtsequenz ein Prozess alle langsamen Bilder und
    waere lange nach den anderen noch beschaeftigt.
    """
    jobs = max(1, int(jobs))
    teile = [files[i::jobs] for i in range(jobs)]
    return [t for t in teile if t]


def find_dri_device():
    """Erster Render-Knoten der Grafikkarte, fuer VAAPI und QuickSync."""
    for n in range(128, 136):
        dev = f"/dev/dri/renderD{n}"
        if os.path.exists(dev):
            return dev
    return "/dev/dri/renderD128"


# ==========================================================================
#  VIDEO-CODECS
#
#  Eine Tabelle statt verstreuter if/elif-Ketten: Beschriftung, FFmpeg-
#  Aufruf, Groessenschaetzung und Selbsttest lesen alle aus derselben Zeile.
#
#  WICHTIG: Der Index ist Teil der gespeicherten Einstellungen
#  (codec_idx in der Konfigurationsdatei und in der Warteschlange).
#  Neue Codecs deshalb nur ANHAENGEN, niemals dazwischen einfuegen.
#
#  Felder
#    label  Text in der Auswahlliste
#    enc    FFmpeg-Encoder
#    args   Funktion(crf) -> zusaetzliche Argumente
#    pix    erzwungenes Pixelformat hinter den Encoder-Argumenten
#    pre    Argumente VOR "-i" (Geraeteauswahl bei VAAPI)
#    vf     Filterkette, falls die Bilder in den Grafikspeicher muessen
#    ext    Dateiendung des Containers (ProRes passt nicht in MP4)
#    mult   Faktor fuer die Dateigroessen-Schaetzung
#    hw     None = reine CPU (kein Selbsttest), sonst Art der Beschleunigung
#    fb     Index des CPU-Codecs, auf den zurueckgefallen wird
# ==========================================================================
def _args_x26x(crf):
    # "slow" statt "fast": bei gleicher Qualitaetsstufe sichtbar weniger
    # Artefakte in feinen Strukturen (Wolken, Laub), kostet nur Kodierzeit.
    return ["-preset", "slow", "-crf", crf]


def _args_nvenc(crf):
    # p6 statt p4: gruendlichere Bewegungssuche, auf jeder NVENC-Generation
    # verfuegbar, die p4 kennt.
    return ["-preset", "p6", "-cq", crf]


def _args_nvenc10(crf):
    return _args_nvenc(crf) + ["-profile:v", "main10"]


def _args_qsv(crf):
    return ["-preset", "slow", "-global_quality", crf]


def _args_vaapi(crf):
    return ["-rc_mode", "CQP", "-qp", crf]


def _args_prores(_crf):
    return ["-profile:v", "3", "-qscale:v", "9"]


VIDEO_CODECS = [
    dict(label="H.264 (CPU Standard)",        enc="libx264",    args=_args_x26x,
         pix="yuv420p", pre=[], vf=None, ext=".mp4", mult=1.0,  hw=None,     fb=0),
    dict(label="H.264 (NVIDIA GPU)",          enc="h264_nvenc", args=_args_nvenc,
         pix="yuv420p", pre=[], vf=None, ext=".mp4", mult=1.0,  hw="nvenc",  fb=0),
    dict(label="H.265/HEVC (CPU)",            enc="libx265",    args=_args_x26x,
         pix="yuv420p", pre=[], vf=None, ext=".mp4", mult=0.6,  hw=None,     fb=2),
    dict(label="H.265/HEVC (NVIDIA GPU)",     enc="hevc_nvenc", args=_args_nvenc,
         pix="yuv420p", pre=[], vf=None, ext=".mp4", mult=0.6,  hw="nvenc",  fb=2),
    # ProRes kann MP4 nicht aufnehmen - FFmpeg bricht sonst mit
    # "Could not find tag for codec prores" ab, bevor ein Bild geschrieben ist.
    dict(label="Apple ProRes 422 HQ",         enc="prores_ks",  args=_args_prores,
         pix=None,      pre=[], vf=None, ext=".mov", mult=12.0, hw=None,     fb=4,
         pix_intern="yuv422p10le"),
    # --- ab hier angehaengt (Version 2.12.0) -----------------------------
    dict(label="H.264 (Intel QuickSync)",     enc="h264_qsv",   args=_args_qsv,
         pix="nv12",    pre=[], vf=None, ext=".mp4", mult=1.1,  hw="qsv",    fb=0),
    dict(label="H.265/HEVC (Intel QuickSync)", enc="hevc_qsv",  args=_args_qsv,
         pix="nv12",    pre=[], vf=None, ext=".mp4", mult=0.7,  hw="qsv",    fb=2),
    dict(label="H.264 (VAAPI: AMD/Intel)",    enc="h264_vaapi", args=_args_vaapi,
         pix=None,      pre=["-vaapi_device", "@DRI@"],
         vf="format=nv12,hwupload", ext=".mp4", mult=1.1, hw="vaapi", fb=0),
    dict(label="H.265/HEVC (VAAPI: AMD/Intel)", enc="hevc_vaapi", args=_args_vaapi,
         pix=None,      pre=["-vaapi_device", "@DRI@"],
         vf="format=nv12,hwupload", ext=".mp4", mult=0.7, hw="vaapi", fb=2),
    # --- ab hier angehaengt (Version 2.42.0) -----------------------------
    dict(label="H.265/HEVC 10 Bit (CPU)",     enc="libx265",    args=_args_x26x,
         pix="yuv420p10le", pre=[], vf=None, ext=".mp4", mult=0.65, hw=None,  fb=9),
    dict(label="H.265/HEVC 10 Bit (NVIDIA GPU)", enc="hevc_nvenc", args=_args_nvenc10,
         pix="p010le",  pre=[], vf=None, ext=".mp4", mult=0.65, hw="nvenc", fb=9),
]


def codec_def(idx):
    """Codec-Zeile zum gespeicherten Index, mit Rueckfall auf libx264."""
    if isinstance(idx, int) and 0 <= idx < len(VIDEO_CODECS):
        return VIDEO_CODECS[idx]
    return VIDEO_CODECS[0]


# Farbraum des Videos. Die JPGs sind sRGB; Player gehen bei HD-Video von
# BT.709 aus. Ohne Angabe rechnete FFmpeg nach BT.601 (Standard-Definition)
# um und kennzeichnete nichts - Gruen- und Rottoene waren leicht
# verschoben. Jetzt wird nach BT.709 umgerechnet und das auch so in die
# Datei geschrieben.
FARBRAUM_ARGS = ["-colorspace", "bt709", "-color_primaries", "bt709",
                 "-color_trc", "bt709"]


def codec_filter(c):
    """Filterkette: RGB -> YUV mit BT.709 im eingeschraenkten Bereich,
    dann das Pixelformat des Encoders (bzw. dessen eigener Filter)."""
    umrechnen = "scale=out_color_matrix=bt709:out_range=tv"
    if c.get('vf'):
        return f"{umrechnen},{c['vf']}"
    ziel = c.get('pix') or c.get('pix_intern')
    return f"{umrechnen},format={ziel}" if ziel else umrechnen


def codec_pre_args(c):
    """pre-Argumente mit eingesetztem Render-Knoten."""
    return [find_dri_device() if a == "@DRI@" else a for a in c['pre']]


def probe_encoder(idx, crf="23", timeout=30):
    """
    Kodiert drei schwarze Testbilder ins Nichts, um zu pruefen, ob der
    gewaehlte Encoder auf diesem Rechner wirklich arbeitet.

    Das kostet unter einer Sekunde und erspart die Entdeckung, dass die
    Grafikkarte nicht mitspielt, erst nach Stunden Entwicklungsarbeit.

    Rueckgabe: (True, "") oder (False, "Grund in Klartext")
    """
    global FFMPEG_BIN
    # Erst das eingestellte FFmpeg, dann die anderen: kann ein anderes den
    # Encoder, wird fuer diesen Programmlauf auf dieses umgestellt.
    reihe = [FFMPEG_BIN] + [k for k in ffmpeg_kandidaten() if k != FFMPEG_BIN]
    erster_grund = None
    for programm in reihe:
        ok, grund = _probe_mit(programm, idx, crf, timeout)
        if ok:
            if programm != FFMPEG_BIN:
                FFMPEG_BIN = programm
            return True, ""
        if erster_grund is None:
            erster_grund = grund
    return False, erster_grund or "FFmpeg wurde nicht gefunden."


def _probe_mit(programm, idx, crf="23", timeout=30):
    """Ein Encoder-Testlauf mit einem bestimmten FFmpeg."""
    c = codec_def(idx)
    if not os.path.exists(programm) and not shutil.which(programm):
        return False, "FFmpeg wurde nicht gefunden."
    cmd = [programm, "-hide_banner", "-loglevel", "error"]
    cmd += codec_pre_args(c)
    cmd += ["-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=0.4"]
    cmd += ["-vf", codec_filter(c)]
    cmd += ["-c:v", c['enc']] + c['args'](crf)
    if c['pix']:
        cmd += ["-pix_fmt", c['pix']]
    cmd += FARBRAUM_ARGS
    cmd += ["-frames:v", "3", "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "Der Testlauf von FFmpeg hat nicht geantwortet."
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {e}"
    if proc.returncode == 0:
        return True, ""
    txt = proc.stderr.decode("utf-8", errors="ignore").strip()
    # Aus der FFmpeg-Ausgabe die Zeilen heraussuchen, die den Grund nennen.
    schluessel = ("driver", "nvenc", "qsv", "vaapi", "mfx", "cuda",
                  "not support", "no such", "unknown encoder", "permission",
                  "no va display", "failed", "invalid")
    zeilen = [z.strip() for z in txt.splitlines()
              if any(k in z.lower() for k in schluessel)]
    grund = "\n".join(zeilen[:4]) if zeilen else txt[:400]
    return False, grund or f"FFmpeg endete mit Fehlercode {proc.returncode}."


def probe_grund_text(grund, lang='de'):
    """Die eigenen Meldungen des Encoder-Selbsttests in der Sprache der
    Oberflaeche. Was FFmpeg selbst schreibt, bleibt unveraendert."""
    grund = str(grund or "")
    if lang != 'en':
        return grund
    feste = {"FFmpeg wurde nicht gefunden.": "FFmpeg was not found.",
             "Der Testlauf von FFmpeg hat nicht geantwortet.":
                 "The FFmpeg test run did not respond."}
    if grund in feste:
        return feste[grund]
    m = re.match(r"^FFmpeg endete mit Fehlercode (-?\d+)\.$", grund)
    if m:
        return f"FFmpeg exited with error code {m.group(1)}."
    return grund


def get_theme():
    v = konfig_lesen('design', standard='dark')
    return v if v in THEMES else 'dark'

def save_theme(name):
    konfig_setzen('design', name)

def get_lang():
    v = konfig_lesen('sprache', standard='de')
    return v if v in ("de", "en") else "de"

def save_lang(lang):
    konfig_setzen('sprache', lang)

# ==========================================================================
#  KERN-FUNKTIONEN
# ==========================================================================
def load_preview_image(filepath, max_width=None):
    """
    Laedt ein Bild als BGR-Array, unabhaengig vom Format.
    cv2.imdecode kann keine RAW-Dateien lesen und liefert dann None. Jede
    Stelle, die ein Vorschaubild braucht, muss deshalb hierueber gehen.
    """
    img = None
    try:
        if is_raw_file(filepath):
            with rawpy.imread(filepath) as raw:
                rgb = raw.postprocess(use_camera_wb=True, half_size=True,
                                      no_auto_bright=True)
            img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imdecode(np.fromfile(filepath, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        return None
    if img is None:
        return None
    if max_width and img.shape[1] > max_width:
        scale = max_width / img.shape[1]
        img = cv2.resize(img, (int(img.shape[1] * scale), int(img.shape[0] * scale)))
    return np.ascontiguousarray(img)

def get_last_path():
    return str(konfig_lesen('letzter_ordner', standard="") or "")

def save_last_path(path):
    konfig_setzen('letzter_ordner', path)

def get_brightness_jpg(filepath, roi_rel=None):
    img = cv2.imdecode(np.fromfile(filepath, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    if roi_rel:
        h, w = img.shape[:2]
        rx, ry, rw, rh = roi_rel
        x1 = min(max(0, int(rx * w)), w - 1)
        y1 = min(max(0, int(ry * h)), h - 1)
        w1 = max(1, min(int(rw * w), w - x1))
        h1 = max(1, min(int(rh * h), h - y1))
        roi_img = img[y1:y1 + h1, x1:x1 + w1]
        b_mean, g_mean, r_mean = cv2.mean(roi_img, jpg_lichtermaske(roi_img))[:3]
    else:
        b_mean, g_mean, r_mean = cv2.mean(img, jpg_lichtermaske(img))[:3]
    luma = 0.2989 * r_mean + 0.5870 * g_mean + 0.1140 * b_mean
    return (luma, b_mean, g_mean, r_mean)

def _srgb_tabelle():
    x = np.arange(256, dtype=np.float64) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


_SRGB16 = None


def _srgb_tabelle16():
    global _SRGB16
    if _SRGB16 is None:
        x = np.arange(65536, dtype=np.float64) / 65535.0
        _SRGB16 = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    return _SRGB16


def jpg_lichtermaske(img, grenze=250):
    """Maske (255 = messen) ohne ausgebrannte Bildpunkte eines 8- oder
    16-Bit-Bildes; None, wenn so viel ausgebrannt ist, dass ueber alles
    gemessen wird. grenze gilt fuer 8 Bit und wird fuer 16 Bit umgerechnet."""
    if img.dtype == np.uint16:
        grenze = grenze * 257
    b, g, r = cv2.split(img)
    hoechst = cv2.max(cv2.max(b, g), r)
    voll = cv2.compare(hoechst, grenze, cv2.CMP_GE)
    if not cv2.countNonZero(voll):
        return None
    maske = np.where(lichter_saum(voll > 0), 0, 255).astype(np.uint8)
    gut = cv2.countNonZero(maske)
    if gut == maske.size:
        return None
    if gut < MESS_MIN_ANTEIL * maske.size:
        return None
    return maske


def jpg_belichtung(img, maske=None):
    """
    Mittlere Helligkeit eines 8-Bit-BGR-Bildes in linearem Licht.

    Exakt und ohne Gleitkomma-Zwischenbilder: weil das Mittel linear ist,
    genuegt je Farbkanal ein Histogramm der 256 Stufen, gewichtet mit
    ihrem linearen Wert. maske (uint8, 0 = auslassen) begrenzt die
    Messung auf bestimmte Bildpunkte.
    """
    anzahl = (img.shape[0] * img.shape[1]) if maske is None else int(cv2.countNonZero(maske))
    if anzahl <= 0:
        return None
    mittel = []
    if img.dtype == np.uint16:
        lin = _srgb_tabelle16()
        auswahl = None if maske is None else (maske > 0)
        for kanal in range(3):
            werte = img[..., kanal] if auswahl is None else img[..., kanal][auswahl]
            hist = np.bincount(werte.ravel(), minlength=65536)
            mittel.append(float(np.dot(hist.astype(np.float64), lin)) / anzahl)
    else:
        lin = _srgb_tabelle()
        for kanal in range(3):
            hist = cv2.calcHist([img], [kanal], maske, [256], [0, 256]).ravel()
            mittel.append(float(np.dot(hist.astype(np.float64), lin)) / anzahl)
    return 0.1140 * mittel[0] + 0.5870 * mittel[1] + 0.2989 * mittel[2]


_SRGB_LUT = None
def srgb_to_linear(values):
    """8-Bit sRGB nach linearem Licht. Nötig, damit Mittelwerte physikalisch
    einer Belichtung entsprechen und Differenzen echte Blendenstufen sind."""
    global _SRGB_LUT
    if _SRGB_LUT is None:
        x = np.arange(256, dtype=np.float64) / 255.0
        _SRGB_LUT = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    return _SRGB_LUT[values]

def measure_jpg_linear(filepath, roi_rel=None):
    """
    Helligkeit eines entwickelten JPGs in linearem Licht.

    Frueher wurde das Bild vor der Messung auf 320 x 213 Punkte verkleinert,
    und zwar ohne Mittelung: von 20 x 20 Punkten blieb einer stehen. Sterne
    und feine Details erzeugten so Messrauschen, das in die
    Nachkalibrierung ging. Jetzt zaehlt jeder Bildpunkt (siehe
    jpg_belichtung).
    """
    img = bild_lesen(filepath)
    if img is None:
        return None
    if roi_rel:
        h, w = img.shape[:2]
        rx, ry, rw, rh = roi_rel
        x1 = min(max(0, int(rx * w)), w - 1)
        y1 = min(max(0, int(ry * h)), h - 1)
        w1 = max(1, min(int(rw * w), w - x1))
        h1 = max(1, min(int(rh * h), h - y1))
        img = img[y1:y1 + h1, x1:x1 + w1]
    return jpg_belichtung(img, jpg_lichtermaske(img))

def measure_nef(filepath, roi_rel=None):
    """
    Misst Helligkeit eines RAWs in linearem Licht.
    16 Bit und Gamma 1.0: bei 8-Bit-Gamma-Ausgabe fallen in Nachtaufnahmen
    große Teile des Bildes auf Schwarz zusammen, dort ist der Mittelwert
    kein verlässliches Maß für die Belichtung mehr.
    """
    wb = None
    zellen_voll = None
    try:
        with rawpy.imread(filepath) as raw:
            # Ausgebrannt ist, was auf dem Sensor am Anschlag steht. Nach
            # Weissabgleich und Umrechnung in sRGB stuende ein kraeftiges
            # Rot schon bei voll, obwohl der Sensor noch Reserve hatte.
            sensor_clip = None
            try:
                weiss = float(raw.white_level)
                roh = raw.raw_image_visible
                if weiss > 0 and roh is not None and roh.size:
                    # Je 2x2-Zelle des Farbfilters (ein Bildpunkt): voll,
                    # sobald einer ihrer Sensorpunkte voll ist. Auf dem
                    # Sensor ist auch ein einzelner voller Kanal verloren.
                    h2, w2 = (roh.shape[0] // 2) * 2, (roh.shape[1] // 2) * 2
                    zellen = roh[:h2, :w2].reshape(h2 // 2, 2, w2 // 2, 2).max(axis=(1, 3))
                    zellen_voll = zellen >= 0.98 * weiss
                    sensor_clip = float(zellen_voll.mean())
            except Exception:
                sensor_clip = None
            rgb = raw.postprocess(use_camera_wb=True, half_size=True,
                                  no_auto_bright=True, gamma=(1, 1), output_bps=16)
            try:
                wb = [float(v) for v in raw.camera_whitebalance[:3]]
            except Exception:
                wb = None
    except Exception:
        return None
    # Ausgebrannte Bildpunkte: vom Sensor (je Bildpunkt eine 2x2-Zelle,
    # passt zur halben Groesse von postprocess), sonst aus dem Bild.
    voll = None
    if zellen_voll is not None and abs(zellen_voll.shape[0] - rgb.shape[0]) <= 2 \
            and abs(zellen_voll.shape[1] - rgb.shape[1]) <= 2:
        hh = min(zellen_voll.shape[0], rgb.shape[0])
        ww = min(zellen_voll.shape[1], rgb.shape[1])
        rgb = rgb[:hh, :ww]
        voll = zellen_voll[:hh, :ww]
    if voll is None:
        voll = rgb[..., :3].max(axis=2) >= 64000
    if roi_rel:
        h, w = rgb.shape[:2]
        rx, ry, rw, rh = roi_rel
        x1 = min(max(0, int(rx * w)), w - 1)
        y1 = min(max(0, int(ry * h)), h - 1)
        w1 = max(1, min(int(rw * w), w - x1))
        h1 = max(1, min(int(rh * h), h - y1))
        rgb = rgb[y1:y1 + h1, x1:x1 + w1]
        voll = voll[y1:y1 + h1, x1:x1 + w1]
    # 32 statt 64 Bit: halber Speicher je Mess-Thread, Ergebnis gleich
    lum = rgb[..., 0].astype(np.float32) * np.float32(0.2989)
    lum += rgb[..., 1].astype(np.float32) * np.float32(0.5870)
    lum += rgb[..., 2].astype(np.float32) * np.float32(0.1140)
    res = {
        'luma': belichtung_ohne_lichter(lum, voll),
        # Anteil der PIXEL, in denen mindestens ein Kanal anschlaegt.
        # Vorher war es das Mittel ueber alle Kanalwerte: ein Sonnenball,
        # in dem nur Rot anschlaegt, zaehlte dann nur zu einem Drittel und
        # blieb unter der Warnschwelle.
        'clip': (sensor_clip if sensor_clip is not None
                 else float((np.sort(rgb, axis=2)[..., 1] >= 64000).mean())),
        'black': float((lum <= 64).mean()),
        'wb_rg': 0.0, 'wb_bg': 0.0,
    }
    if wb and len(wb) >= 3 and wb[1] > 0:
        res['wb_rg'] = wb[0] / wb[1]
        res['wb_bg'] = wb[2] / wb[1]
    return res

# Anteil der Bildpunkte, der fuer die Messung mindestens uebrig bleiben
# muss. Ist mehr ausgebrannt, wird ueber alle gemessen wie frueher.
MESS_MIN_ANTEIL = 0.20


def lichter_saum(voll):
    """
    Erweitert die ausgebrannten Flaechen um einen schmalen Saum.

    Am Rand einer ausgebrannten Flaeche (Sonnenrand) liegen Bildpunkte
    knapp unter der Grenze. Ob sie gerade noch mitzaehlen, wechselt von
    Bild zu Bild - und weil sie sehr hell sind, wackelte der Messwert.
    Ohne Saum zeigte sich das als Flackern in der Nachkalibrierung.
    """
    if voll is None or not voll.any():
        return voll
    r = max(2, int(round(max(voll.shape) / 1000.0)) * 2)
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(voll.astype(np.uint8), kern) > 0


def belichtung_ohne_lichter(lum, voll):
    """
    Mittlere Helligkeit in linearem Licht - ohne ausgebrannte Bildpunkte.

    Ausgebranntes (Sonne, Lampen) bleibt gleich hell, egal wie die Kamera
    belichtet. Im Mittel zieht es den Messwert zu sich: eine Blende, die
    5 % mehr Licht durchlaesst, wurde dann als weniger gemessen und zu
    schwach ausgeglichen. Darum zaehlen nur Bildpunkte, die das Licht
    noch abbilden. Das Mittel bleibt dabei ein gewoehnliches - anders als
    ein logarithmisches haengt es nicht vom Rauschen ab, das sich mit der
    ISO-Stufe aendert.
    """
    if voll is None or not voll.any():
        return float(lum.mean(dtype=np.float64))
    voll = lichter_saum(voll)
    gut = ~voll
    if gut.mean() < MESS_MIN_ANTEIL:
        return float(lum.mean(dtype=np.float64))
    return float(lum[gut].mean(dtype=np.float64))


# ==========================================================================
#  NACHMESSUNG IN PASS 2: AUSGEBRANNTES FUER DIE GANZE SEQUENZ
#
#  Im fertigen Bild haengt "ausgebrannt" von der Korrektur ab, die gerade
#  gemessen werden soll: eine Sonne, die um 0,3 EV abgedunkelt wurde, ist im
#  JPG grau statt weiss. Je Bild entschieden, zaehlte sie mal mit und mal
#  nicht - die Nachkalibrierung "korrigierte" dann Flackern, das es nicht
#  gab, und machte es sichtbar. Deshalb misst jedes Bild Blocksummen und
#  merkt sich, welche Bloecke ausgebrannt sind; ausgewertet wird ueber die
#  Bloecke, die in KEINEM Bild der Sequenz ausgebrannt sind.
# ==========================================================================
BLOCK_RASTER = 256        # hoechstens so viele Bloecke je Bildbreite


def jpg_bloecke(filepath, roi_rel=None):
    """
    Blocksummen der linearen Helligkeit eines entwickelten Bildes.
    Rueckgabe: (Summen float32, ausgebrannt bool, Bildpunkte je Block) oder None
    """
    img = bild_lesen(filepath)
    if img is None:
        return None
    if roi_rel:
        h, w = img.shape[:2]
        rx, ry, rw, rh = roi_rel
        x1 = min(max(0, int(rx * w)), w - 1)
        y1 = min(max(0, int(ry * h)), h - 1)
        w1 = max(1, min(int(rw * w), w - x1))
        h1 = max(1, min(int(rh * h), h - y1))
        img = img[y1:y1 + h1, x1:x1 + w1]
    h, w = img.shape[:2]
    bs = max(2, -(-w // BLOCK_RASTER))
    gh, gw = h // bs, w // bs
    if gh < 1 or gw < 1:
        return None
    img = img[:gh * bs, :gw * bs]
    tief = img.dtype == np.uint16
    tab = (_srgb_tabelle16() if tief else _srgb_tabelle()).astype(np.float32)
    lum = tab[img[..., 0]] * np.float32(0.1140)
    lum += tab[img[..., 1]] * np.float32(0.5870)
    lum += tab[img[..., 2]] * np.float32(0.2989)
    summen = lum.reshape(gh, bs, gw, bs).sum(axis=(1, 3), dtype=np.float64).astype(np.float32)
    grenze = 250 * 257 if tief else 250
    voll = (img.max(axis=2) >= grenze).reshape(gh, bs, gw, bs).any(axis=(1, 3))
    return summen, voll, bs * bs


def sequenz_helligkeit(bloecke):
    """
    Helligkeit je Bild ueber die Bloecke, die in keinem Bild ausgebrannt
    sind (plus ein Block Saum). Bleibt so zu wenig uebrig, entscheidet
    jedes Bild fuer sich.
    bloecke: Liste von jpg_bloecke-Ergebnissen (None = unlesbar)
    Rueckgabe: Liste der Helligkeiten (None fuer unlesbare Bilder)
    """
    gueltig = [b for b in bloecke if b is not None]
    if not gueltig:
        return [None] * len(bloecke)
    form = gueltig[0][0].shape
    kern = np.ones((3, 3), np.uint8)
    gemeinsam = np.zeros(form, bool)
    for b in gueltig:
        if b[0].shape == form:
            gemeinsam |= b[1]
    gemeinsam = cv2.dilate(gemeinsam.astype(np.uint8), kern) > 0
    gemeinsam_ok = (~gemeinsam).mean() >= MESS_MIN_ANTEIL
    verhaeltnis = [None] * len(bloecke) if gemeinsam_ok else _verhaeltnis_messung(bloecke, form, kern)
    out = []
    for nr, b in enumerate(bloecke):
        if b is None:
            out.append(None)
            continue
        summen, voll, n_px = b
        if gemeinsam_ok and summen.shape == form:
            gut = ~gemeinsam
        else:
            if verhaeltnis[nr] is not None:
                out.append(verhaeltnis[nr])
                continue
            gut = ~(cv2.dilate(voll.astype(np.uint8), kern) > 0)
            if gut.mean() < MESS_MIN_ANTEIL:
                gut = np.ones_like(voll)
        anzahl = int(gut.sum())
        out.append(float(summen[gut].sum(dtype=np.float64)) / (anzahl * n_px) if anzahl else None)
    return out


def _nan_median_spalten(a):
    """Median je Spalte ohne NaN, NaN wo eine Spalte keinen Wert hat.
    Ueber Sortieren - np.nanmedian ist hier rund zwanzigmal langsamer."""
    a = a.reshape(a.shape[0], -1)
    sortiert = np.sort(a, axis=0)              # NaN landen hinten
    anzahl = np.isfinite(a).sum(axis=0)
    unten = np.clip((anzahl - 1) // 2, 0, a.shape[0] - 1)
    oben = np.clip(anzahl // 2, 0, a.shape[0] - 1)
    spalten = np.arange(a.shape[1])
    med = (sortiert[unten, spalten] + sortiert[oben, spalten]) / 2.0
    med[anzahl == 0] = np.nan
    return med


def _verhaeltnis_messung(bloecke, form, kern, fenster=12):
    """
    Helligkeit ueber Verhaeltnisse zu benachbarten Bildern - fuer Serien,
    in denen fast ueberall irgendwann etwas ausbrennt.

    Bisher entschied in diesem Fall jedes Bild fuer sich, welche Bloecke
    zaehlen. Das kippt bei der Nachkalibrierung: wird ein Bild heller,
    brennen mehr Bloecke aus, fallen aus der Messung heraus, und uebrig
    bleiben die dunklen Ecken. Das Bild misst sich DUNKLER, wird noch
    heller gemacht - und so fort bis zum Anschlag. Gesehen in einem
    Kerzenlicht-Zeitraffer mit Slider: einzelne Bilder sprangen um fast
    eine Blende.

    Hier wird jeder Block mit demselben Block eines Bezugs verglichen -
    dem Median der Nachbarbilder (+-fenster), damit auch eine Kamerafahrt
    passt -, und je Bild zaehlt der Median dieser Verhaeltnisse. Wird ein
    Bild um den Faktor k heller, sind alle nicht ausgebrannten
    Verhaeltnisse k, gleich welche Bloecke gerade ausbrennen.
    Rueckgabe: Liste wie bloecke (None, wo so nicht messbar).
    """
    idx = [i for i, b in enumerate(bloecke) if b is not None and b[0].shape == form]
    out = [None] * len(bloecke)
    if len(idx) < 2:
        return out
    s = np.stack([bloecke[i][0].ravel() for i in idx]).astype(np.float64)
    v = np.stack([(cv2.dilate(bloecke[i][1].astype(np.uint8), kern) > 0).ravel() for i in idx])
    s_frei = np.where(v, np.nan, s)
    n = len(idx)
    for j, i in enumerate(idx):
        von, bis = max(0, j - fenster), min(n, j + fenster + 1)
        bezug = _nan_median_spalten(s_frei[von:bis])
        frei = np.isfinite(bezug) & ~v[j]
        if not frei.any():
            continue
        # Sehr dunkle Bloecke rauschen - sie bestimmen das Verhaeltnis nicht mit
        frei &= bezug > np.nanmax(bezug) * 0.01
        if frei.sum() < max(4, int(0.05 * frei.size)):
            continue
        q = s[j][frei] / bezug[frei]
        skala = float(np.nanmean(bezug[np.isfinite(bezug)])) / bloecke[i][2]
        out[i] = float(np.median(q)) * skala
    return out


def get_brightness_nef(filepath, roi_rel=None):
    res = measure_nef(filepath, roi_rel)
    return res['luma'] if res else None

SCHNELL_BREITE_MAX = 1280   # Schnellvorschau: hoechstens so breit


def schnell_bild_laden(pfad, breite, roi_rel=None):
    """
    Liest ein Bild so schnell wie moeglich fuer die Schnellvorschau.

    RAW: das eingebettete Kamera-JPEG statt einer Entwicklung - das ist
    rund zwanzigmal schneller. JPG: verkleinert dekodiert.
    Rueckgabe: (JPEG-Bytes des verkleinerten Bildes, Helligkeit linear)
    oder (None, None).
    """
    img = None
    try:
        if is_raw_file(pfad):
            with rawpy.imread(pfad) as raw:
                try:
                    th = raw.extract_thumb()
                    if th.format == rawpy.ThumbFormat.JPEG:
                        img = cv2.imdecode(np.frombuffer(th.data, np.uint8),
                                           cv2.IMREAD_REDUCED_COLOR_2)
                    else:
                        img = cv2.cvtColor(th.data, cv2.COLOR_RGB2BGR)
                except Exception:
                    rgb = raw.postprocess(use_camera_wb=True, half_size=True,
                                          no_auto_bright=True)
                    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        else:
            daten = np.fromfile(pfad, dtype=np.uint8)
            img = cv2.imdecode(daten, cv2.IMREAD_REDUCED_COLOR_2)
            if img is not None and img.shape[1] < breite:
                img = cv2.imdecode(daten, cv2.IMREAD_COLOR)
    except Exception:
        img = None
    if img is None or img.size == 0:
        return None, None
    h, w = img.shape[:2]
    if w > breite:
        img = cv2.resize(img, (breite, max(1, int(round(h * breite / float(w))))),
                         interpolation=cv2.INTER_AREA)
    mess = img
    if roi_rel:
        hh, ww = img.shape[:2]
        rx, ry, rw, rh = roi_rel
        x1 = min(max(0, int(rx * ww)), ww - 1)
        y1 = min(max(0, int(ry * hh)), hh - 1)
        mess = img[y1:y1 + max(1, int(rh * hh)), x1:x1 + max(1, int(rw * ww))]
    lin = srgb_to_linear(mess)
    luma = float((lin[..., 2] * 0.2126 + lin[..., 1] * 0.7152
                  + lin[..., 0] * 0.0722).mean())
    ok, kodiert = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return (kodiert.tobytes() if ok else None), luma


def helligkeit_lut(faktor):
    """Tabelle fuer cv2.LUT: hebt ein 8-Bit-sRGB-Bild in linearem Licht
    um 'faktor' an."""
    x = np.arange(256, dtype=np.float64) / 255.0
    lin = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    lin = np.clip(lin * float(faktor), 0.0, 1.0)
    s = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)
    return np.clip(s * 255.0 + 0.5, 0, 255).astype(np.uint8)


def process_single_thumb(args):
    f, roi_rel = args
    img = None
    is_raw = is_raw_file(f)
    try:
        if is_raw:
            with rawpy.imread(f) as raw:
                try:
                    thumb = raw.extract_thumb()
                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        img = cv2.imdecode(np.frombuffer(thumb.data, np.uint8), cv2.IMREAD_COLOR)
                    else:
                        img = cv2.cvtColor(thumb.data, cv2.COLOR_RGB2BGR)
                except Exception:
                    rgb = raw.postprocess(use_camera_wb=True, half_size=True, no_auto_bright=True)
                    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_COLOR)
    except Exception:
        pass
    if img is None:
        return f, None, None
    # --- Kleineres 3:2 Format für das Raster-Layout ---
    thumb_w, thumb_h = 128, 85
    img_small = cv2.resize(img, (thumb_w, thumb_h))
    if roi_rel:
        rx, ry, rw, rh = roi_rel
        x1 = min(max(0, int(rx * thumb_w)), thumb_w - 1)
        y1 = min(max(0, int(ry * thumb_h)), thumb_h - 1)
        w1 = max(1, min(int(rw * thumb_w), thumb_w - x1))
        h1 = max(1, min(int(rh * thumb_h), thumb_h - y1))
        roi_img = img_small[y1:y1 + h1, x1:x1 + w1]
        b_mean, g_mean, r_mean = cv2.mean(roi_img)[:3]
    else:
        b_mean, g_mean, r_mean = cv2.mean(img_small)[:3]
    luma = 0.2989 * r_mean + 0.5870 * g_mean + 0.1140 * b_mean
    hist_h, hist_w = 30, thumb_w
    hist_bgr = np.zeros((hist_h, hist_w, 3), dtype=np.uint8)
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    for i in range(3):
        hist = cv2.calcHist([img_small], [i], None, [hist_w], [0, 256])
        cv2.normalize(hist, hist, 0, hist_h - 2, cv2.NORM_MINMAX)
        pts = np.column_stack((np.arange(hist_w), hist_h - np.int32(np.round(hist.flatten()))))
        cv2.polylines(hist_bgr, [pts], False, colors[i], 1, cv2.LINE_AA)
    hist_bgr[0, :] = [60, 60, 60]
    if roi_rel:
        cv2.rectangle(img_small, (x1, y1), (x1 + w1, y1 + h1), (0, 255, 255), 1)
    rgb_img = cv2.cvtColor(img_small, cv2.COLOR_BGR2RGB)
    hist_rgb = cv2.cvtColor(hist_bgr, cv2.COLOR_BGR2RGB)
    combined_img = np.vstack((rgb_img, hist_rgb))
    is_kf = check_is_keyframe(sidecar(f))
    # Farbstich in den Lichtern schon beim Einlesen messen - das kostet
    # auf dem 128er Vorschaubild nichts und zeigt, ob das Problem die
    # ganze Sequenz betrifft oder nur ein paar Bilder.
    hl_bunt = lichter_farbstich(rgb_img, linear=False)[0]
    daten = {
        'hl_bunt': float(hl_bunt),
        'luma': float(luma),
        'kf': bool(is_kf),
        'wb': float(np.log2(max(r_mean, 1e-3) / max(b_mean, 1e-3))),
        'clip': ausgebrannt_anteil(img_small),
    }
    return f, combined_img, daten

def get_exif_data(filepath):
    data = {'shutter': 0.0, 'iso': 100, 'aperture': 0.0, 'time': ''}
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            if 'EXIF ExposureTime' in tags:
                val = tags['EXIF ExposureTime'].values[0]
                data['shutter'] = float(val.num) / float(val.den)
            if 'EXIF ISOSpeedRatings' in tags:
                data['iso'] = int(tags['EXIF ISOSpeedRatings'].values[0])
            if 'EXIF FNumber' in tags:
                val = tags['EXIF FNumber'].values[0]
                data['aperture'] = float(val.num) / float(val.den)
            if 'Image DateTime' in tags:
                data['time'] = str(tags['Image DateTime'])
    except Exception:
        pass
    return data

def exif_series(files):
    """
    Belichtungswert und Aufnahmeabstand je Bild aus den EXIF-Daten.
    EV100 = log2(Blende^2 / Zeit) - log2(ISO/100).
    """
    import datetime
    ev, intervall, zeiten = [], [], []
    for f in files:
        d = get_exif_data(f)
        t, iso, ap = d.get('shutter', 0.0), d.get('iso', 0), d.get('aperture', 0.0)
        if t > 0 and ap > 0 and iso > 0:
            ev.append(math.log2(ap * ap / t) - math.log2(iso / 100.0))
        else:
            ev.append(float('nan'))
        try:
            zeiten.append(datetime.datetime.strptime(d.get('time', ''),
                                                     "%Y:%m:%d %H:%M:%S"))
        except ValueError:
            zeiten.append(None)
    for i in range(len(zeiten)):
        if i > 0 and zeiten[i] and zeiten[i - 1]:
            intervall.append((zeiten[i] - zeiten[i - 1]).total_seconds())
        else:
            intervall.append(float('nan'))
    return ev, intervall

def scan_exif(files):
    """
    Liest die Aufnahmedaten einmal fuer die ganze Sequenz.
    Rueckgabe: dict mit 'times', 'ev' und 'interval', jeweils in Dateireihenfolge.
    """
    import datetime
    times, ev = [], []
    for f in files:
        d = get_exif_data(f)
        try:
            times.append(datetime.datetime.strptime(d.get('time', ''), "%Y:%m:%d %H:%M:%S"))
        except ValueError:
            times.append(None)
        s = d.get('shutter', 0.0) or 0.0
        iso = d.get('iso', 0) or 0
        ap = d.get('aperture', 0.0) or 0.0
        if s > 0 and ap > 0 and iso > 0:
            ev.append(math.log2(ap * ap / s) - math.log2(iso / 100.0))
        else:
            ev.append(float('nan'))
    interval = [float('nan')] * len(files)
    for i in range(1, len(files)):
        if times[i] and times[i - 1]:
            d = (times[i] - times[i - 1]).total_seconds()
            if d > 0:
                interval[i] = d
    if len(interval) > 1 and not math.isnan(interval[1]):
        interval[0] = interval[1]
    return {'times': times, 'ev': ev, 'interval': interval}

def find_sequence_gaps(times, tolerance=1.6, window=21):
    """
    Sucht fehlende Bilder anhand der Aufnahmezeiten, robust gegen die
    wachsende/schrumpfende Belichtungszeit bei Holy-Grail-Aufnahmen (mit-
    laufender Median statt fester Vergleichswert).
    Rueckgabe: (Liste von (Index, Sekunden, fehlende Bilder),
                [kleinstes, mittleres, groesstes uebliches Intervall])
    """
    paare = [(i, (times[i] - times[i - 1]).total_seconds())
             for i in range(1, len(times)) if times[i] and times[i - 1]]
    paare = [(i, d) for i, d in paare if d > 0]
    if len(paare) < 8:
        return [], [0.0, 0.0, 0.0]
    idx = np.array([i for i, _ in paare])
    d = np.array([v for _, v in paare], dtype=np.float64)
    h = max(3, window // 2)
    basis = np.array([np.median(d[max(0, k - h):min(d.size, k + h + 1)])
                      for k in range(d.size)])
    gaps = []
    for k in range(d.size):
        if basis[k] <= 0:
            continue
        verhaeltnis = d[k] / basis[k]
        if verhaeltnis >= tolerance:
            gaps.append((int(idx[k]), float(d[k]), max(1, int(round(verhaeltnis)) - 1)))
    return gaps, [float(basis.min()), float(np.median(basis)), float(basis.max())]

def format_shutter(s):
    if s <= 0:
        return "N/A"
    if s < 0.3:
        return f"1/{int(round(1/s))}s"
    return f"{s:.1f}s"
# ==========================================================================
#  DEFLICKER-BASISWERTE UND DATEI-HELFER
# ==========================================================================
def pl_ordner(target_dir, anlegen=False):
    """Der Purelapse-Ordner im Bilderordner. Beim Schreiben anlegen=True."""
    d = os.path.join(target_dir, PL_ORDNER)
    if anlegen:
        os.makedirs(d, exist_ok=True)
    return d


def pl_datei(target_dir, name, anlegen=False):
    """Pfad einer Purelapse-Datei (Messwerte, Protokolle) im Purelapse-Ordner."""
    return os.path.join(pl_ordner(target_dir, anlegen), name)


def zwischen_ordner(target_dir):
    """Ordner der entwickelten Zwischenbilder (Deflickered_JPG)."""
    return os.path.join(pl_ordner(target_dir), ZWISCHEN_ORDNER)


def ist_purelapse_video(name):
    return "_Purelapse_" in name and name.lower().endswith((".mp4", ".mov"))


def alte_ablage_umraeumen(target_dir):
    """
    Bis 2.42 lagen Videos, Deflickered_JPG und die purelapse_*-Dateien lose
    im Bilderordner. Raeumt sie einmalig in den Purelapse-Ordner.
    Liegt dort schon eine gleichnamige Datei, bleibt die alte, wo sie ist -
    ueberschrieben wird nichts.
    Rueckgabe: (verschobene Namen, nicht verschobene Namen)
    """
    try:
        namen = os.listdir(target_dir)
    except OSError:
        return [], []
    alt = set((DEFLICKER_DB, CALIB_DB, RESULT_DB, ZWISCHEN_ORDNER) + PROTOKOLLE)
    kandidaten = sorted(n for n in namen
                        if (n in alt or ist_purelapse_video(n))
                        and (os.path.isfile(os.path.join(target_dir, n))
                             or (n == ZWISCHEN_ORDNER
                                 and os.path.isdir(os.path.join(target_dir, n)))))
    if not kandidaten:
        return [], []
    try:
        ziel_ordner = pl_ordner(target_dir, anlegen=True)
    except OSError:
        return [], kandidaten
    verschoben, geblieben = [], []
    for n in kandidaten:
        ziel = os.path.join(ziel_ordner, n)
        if os.path.exists(ziel):
            geblieben.append(n)
            continue
        try:
            shutil.move(os.path.join(target_dir, n), ziel)
            verschoben.append(n)
        except OSError:
            geblieben.append(n)
    return verschoben, geblieben


def save_base_ev(target_dir, mapping):
    # Ohne diese Werte fehlen Pass 2 die Grundlagen der Keyframe-Uebergaenge:
    # ein Fehler muss den Lauf anhalten, nicht nur auf der Konsole stehen.
    datei_atomar(pl_datei(target_dir, DEFLICKER_DB, anlegen=True),
                 json.dumps(mapping, indent=1))

def arp_fingerprint(arp_path):
    try:
        with open(arp_path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()[:16]
    except OSError:
        return ""

def load_dev_index(out_dir):
    try:
        with open(os.path.join(out_dir, DEV_INDEX), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def save_dev_index(out_dir, index):
    # Nur ein Merker zum Ueberspringen - fehlt er, wird neu entwickelt.
    try:
        datei_atomar(os.path.join(out_dir, DEV_INDEX), json.dumps(index, indent=0))
    except OSError:
        pass

# Zwischenbilder der Engine: JPG (Standard) oder 16-Bit-TIFF
ZW_JPG = (".jpg", ".JPG")
ZW_TIF = (".tif", ".TIF", ".tiff")


def zw_endungen(tief=False):
    return ZW_TIF if tief else ZW_JPG


def zw_datei(out_dir, stem, tief=False):
    """Pfad des vorhandenen Zwischenbildes oder None."""
    for ext in zw_endungen(tief):
        pfad = os.path.join(out_dir, stem + ext)
        if os.path.exists(pfad):
            return pfad
    return None


def _dev_kennung(f, tief):
    # Das Format gehoert zum Entwicklungsstand: wer umschaltet, bekommt die
    # Bilder neu entwickelt, statt alte im falschen Format weiterzuverwenden.
    return arp_fingerprint(sidecar(f)) + ("|16" if tief else "")


def pending_development(files, out_dir, tief=False):
    index = load_dev_index(out_dir)
    todo = []
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        if zw_datei(out_dir, stem, tief) is None or index.get(stem, "") != _dev_kennung(f, tief):
            todo.append(f)
    return todo

def mark_developed(files, out_dir, tief=False):
    """Merkt sich, mit welchem Profilstand ein Bild entwickelt wurde -
    aber nur fuer Bilder, deren Zwischenbild auch wirklich da ist."""
    index = load_dev_index(out_dir)
    for f in files:
        stem = os.path.splitext(os.path.basename(f))[0]
        if zw_datei(out_dir, stem, tief) is not None:
            index[stem] = _dev_kennung(f, tief)
    save_dev_index(out_dir, index)


def bild_lesen(pfad):
    """JPG (8 Bit) oder TIFF (16 Bit bleibt 16 Bit), immer als BGR."""
    try:
        daten = np.fromfile(pfad, dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(daten, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_COLOR)


def bild_hoechstwert(img):
    return 65535 if img.dtype == np.uint16 else 255

def load_queue():
    data = konfig_lesen('warteschlange', standard=[])
    return data if isinstance(data, list) else []

def save_queue(jobs):
    konfig_setzen('warteschlange', list(jobs))

def load_residuals(target_dir, files=None):
    """
    Restflackern des letzten Pass-2-Laufs aus purelapse_result.json.
    Wird 'files' übergeben, kommt die Rückgabe exakt in dieser Reihenfolge
    und Länge zurück (fehlende Werte als NaN) - so bleibt die Kurve auch
    dann korrekt zugeordnet, wenn sich die Dateimenge zwischen zwei Läufen
    veraendert hat.
    """
    try:
        with open(pl_datei(target_dir, RESULT_DB), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if files is None:
        return [float(v) for _, v in sorted(data.items())]
    out = []
    for f in files:
        key = os.path.basename(f)
        try:
            out.append(float(data.get(key, float('nan'))))
        except (TypeError, ValueError):
            out.append(float('nan'))
    return out

def save_residuals(target_dir, mapping):
    # Nur fuer die Anzeige im Diagramm.
    try:
        datei_atomar(pl_datei(target_dir, RESULT_DB, anlegen=True), json.dumps(mapping, indent=0))
    except OSError:
        pass

def load_calib(target_dir):
    try:
        with open(pl_datei(target_dir, CALIB_DB), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

def save_calib(target_dir, mapping):
    # Gehoert zu den Korrekturen in den Sidecars: geht sie verloren, rechnet
    # der naechste Lauf mit falschen Ausgangswerten.
    datei_atomar(pl_datei(target_dir, CALIB_DB, anlegen=True), json.dumps(mapping, indent=1))

def write_check_log(target_dir, filename, header, issues, checked):
    try:
        with open(pl_datei(target_dir, filename, anlegen=True), "w", encoding="utf-8") as f:
            f.write(header + "\n")
            f.write(f"Geprueft: {checked} Profile\n")
            f.write(f"Auffaelligkeiten: {len(issues)}\n\n")
            if not issues:
                f.write("Keine Abweichungen gefunden. Die Profile entsprechen "
                        "formal dem Original.\n")
            else:
                for line in issues:
                    f.write(line + "\n")
    except OSError as e:
        print(f"Fehler beim Schreiben von {filename}: {e}")

def save_report(target_dir, filename, rows):
    """Schreibt ein Messprotokoll als CSV in den Purelapse-Ordner."""
    if not rows:
        return
    try:
        import csv
        path = pl_datei(target_dir, filename, anlegen=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    except OSError as e:
        print(f"Fehler beim Schreiben von {filename}: {e}")

def load_base_ev(target_dir):
    try:
        with open(pl_datei(target_dir, DEFLICKER_DB), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}

# ==========================================================================
#  GLÄTTUNG DER ZIEL-HELLIGKEITSKURVE
# ==========================================================================
def _pava_monotone(y, increasing=True):
    """Isotone Regression (Pool Adjacent Violators)."""
    v_in = np.asarray(y, dtype=np.float64)
    if not increasing:
        v_in = -v_in
    n = v_in.size
    vals = np.empty(n, dtype=np.float64)
    wts = np.empty(n, dtype=np.float64)
    lens = np.empty(n, dtype=np.int64)
    j = -1
    for i in range(n):
        j += 1
        vals[j] = v_in[i]
        wts[j] = 1.0
        lens[j] = 1
        while j > 0 and vals[j - 1] > vals[j]:
            w = wts[j - 1] + wts[j]
            vals[j - 1] = (wts[j - 1] * vals[j - 1] + wts[j] * vals[j]) / w
            wts[j - 1] = w
            lens[j - 1] += lens[j]
            j -= 1
    out = np.empty(n, dtype=np.float64)
    pos = 0
    for k in range(j + 1):
        out[pos:pos + lens[k]] = vals[k]
        pos += lens[k]
    return out if increasing else -out

def two_pass_smooth(data_array, is_sunset_sunrise_mode=0, smooth_amount=50):
    """Erzeugt die geglättete Ziel-Helligkeitskurve (Rückgabe linear, nicht EV)."""
    data = np.asarray(data_array, dtype=np.float64)
    n = data.size
    if n < 3:
        return data.copy()
    ev = np.log2(np.maximum(data, 1e-6))
    x = np.arange(n, dtype=np.float64)
    slope, intercept = np.polyfit(x, ev, 1)
    trend = slope * x + intercept
    resid = ev - trend
    s = float(max(1, min(100, int(smooth_amount))))
    w_lin = min(1.0, max(0.0, (s - 85.0) / 15.0))
    if w_lin >= 1.0:
        smoothed_ev = trend
    else:
        sigma1 = min(1.0 + 0.60 * s, n / 3.0)
        sigma2 = min(max(1.0, sigma1 / 3.0), n / 6.0)
        base = gaussian_filter1d(resid, sigma=sigma1, mode='reflect')
        dev = resid - base
        mad = float(np.median(np.abs(dev - np.median(dev))))
        limit = max(0.05, 2.5 * 1.4826 * mad)
        clamped = base + np.clip(dev, -limit, limit)
        smoothed_ev = trend + gaussian_filter1d(clamped, sigma=sigma2, mode='reflect')
    final_ev = (1.0 - w_lin) * smoothed_ev + w_lin * trend
    if is_sunset_sunrise_mode == 1:
        final_ev = _pava_monotone(final_ev, increasing=True)
    elif is_sunset_sunrise_mode == 2:
        final_ev = _pava_monotone(final_ev, increasing=False)
    return 2.0 ** final_ev

def build_hotpixel_map(files, status_sig, check_abort, samples=15, threshold=24):
    """Findet defekte Sensorpixel anhand der gesamten Sequenz."""
    if len(files) < 3:
        return None
    step = max(1, len(files) // samples)
    picks = files[::step][:samples]
    counter = None
    used = 0
    for i, f in enumerate(picks):
        check_abort()
        img = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            continue
        med = cv2.medianBlur(img, 3)
        dev = cv2.absdiff(img, med)
        hit = (dev > threshold).astype(np.uint16)
        counter = hit if counter is None else counter + hit
        used += 1
        status_sig.emit(f"Suche defekte Pixel: {i+1}/{len(picks)}")
    if counter is None or used < 3:
        return None
    mask = counter >= max(3, int(used * 0.85))
    idx = np.nonzero(mask)
    return idx if idx[0].size else None

# ==========================================================================
#  KAMERAFAHRT
#
#  Der Ausschnitt wurde bisher auf ganze Bildpunkte gerundet, Breite und
#  Hoehe jeweils fuer sich. Bei einer langsamen Fahrt sprang er dadurch
#  sichtbar, und das Seitenverhaeltnis "atmete" um einen Punkt. Jetzt wird
#  er mit Bruchteilen von Bildpunkten gesetzt (siehe ausschnitt_subpixel).
# ==========================================================================
KAMERA_RAMPE = 0.10    # Anteil der Laufzeit fuer Anfahren und Abbremsen
KAMERA_WEICH = 0.4     # Weichzeichnung vor dem Abtasten, in Zielpunkten


def kamera_verlauf(t, rampe=KAMERA_RAMPE):
    """
    Fortschritt der Kamerafahrt fuer t in [0, 1].

    In der Mitte gleichmaessig, am Anfang und Ende sanft an- und
    abgebremst (Geschwindigkeit steigt bzw. faellt linear). Vorher fuhr die
    Kamera mit voller Geschwindigkeit los und hielt schlagartig an.
    """
    t = min(1.0, max(0.0, float(t)))
    r = min(0.45, max(0.0, float(rampe)))
    if r <= 0.0:
        return t
    if t < r:
        return t * t / (2.0 * r * (1.0 - r))
    if t > 1.0 - r:
        return 1.0 - (1.0 - t) ** 2 / (2.0 * r * (1.0 - r))
    return (t - r / 2.0) / (1.0 - r)


def ausschnitt_subpixel(img, x0, y0, bw, bh, width, height):
    """
    Schneidet das Rechteck (x0, y0, bw, bh) - in Bildpunkten, mit
    Nachkommastellen - aus und bringt es auf width x height.

    Erst wird so weichgezeichnet, wie es die Verkleinerung verlangt (sonst
    Treppen und Moire), dann wird mit Bruchteilen von Bildpunkten genau
    abgetastet. Anders als bei einer Verschiebung hinterher bleibt die
    Schaerfe dabei gleich, egal wo zwischen zwei Bildpunkten der
    Ausschnitt gerade liegt - sonst wuerde feine Struktur bei einer
    langsamen Fahrt im Takt der Bildpunkte flimmern.
    """
    ih, iw = img.shape[:2]
    bw = max(1.0, min(float(bw), iw))
    bh = max(1.0, min(float(bh), ih))
    x0 = max(0.0, min(float(x0), iw - bw))
    y0 = max(0.0, min(float(y0), ih - bh))
    sx, sy = width / bw, height / bh            # Zielpunkte je Quellpunkt
    rand = 6
    ix0 = max(0, int(math.floor(x0)) - rand)
    iy0 = max(0, int(math.floor(y0)) - rand)
    ix1 = min(iw, int(math.ceil(x0 + bw)) + rand)
    iy1 = min(ih, int(math.ceil(y0 + bh)) + rand)
    grob = img[iy0:iy1, ix0:ix1]
    if sx < 1.0 or sy < 1.0:
        grob = cv2.GaussianBlur(grob, (0, 0),
                                sigmaX=KAMERA_WEICH / min(1.0, sx),
                                sigmaY=KAMERA_WEICH / min(1.0, sy))
    # Zielpunkt (u, v) -> Quellpunkt im Ausschnitt (Pixelmitten)
    m = np.array([[1.0 / sx, 0.0, x0 - ix0 + 0.5 / sx - 0.5],
                  [0.0, 1.0 / sy, y0 - iy0 + 0.5 / sy - 0.5]], dtype=np.float64)
    return cv2.warpAffine(grob, m, (int(width), int(height)),
                          flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                          borderMode=cv2.BORDER_REPLICATE)


_EXIF_MERKER = {}


def exif_gemerkt(pfad):
    """get_exif_data mit Zwischenspeicher - beim Rendern wird jedes Bild
    sonst ein weiteres Mal aus der RAW-Datei gelesen."""
    try:
        st = os.stat(pfad)
        key = (pfad, st.st_mtime_ns, st.st_size)
    except OSError:
        return get_exif_data(pfad)
    merker = _EXIF_MERKER
    wert = merker.get(key)
    if wert is None:
        wert = get_exif_data(pfad)
        if len(merker) > 20000:
            merker.clear()
        merker[key] = wert
    return dict(wert)


def telemetrie_zeichnen(bild, text, hoehe, hoechst):
    """
    Schreibt die Telemetrie-Zeile unten links ins Bild (auf schwarzem
    Kasten), in 8 und in 16 Bit.

    OpenCV zeichnet Text nur noch in 8-Bit-Bilder (ab OpenCV 5:
    "img.depth() == CV_8U"). Mit 16-Bit-Zwischenbildern brach das Rendern
    deshalb am ersten Bild ab. Fuer 16 Bit wird der Text als 8-Bit-Maske
    gezeichnet und mit ihrer Kantenglaettung in das Bild uebertragen -
    das Ergebnis entspricht dem 8-Bit-Bild mal 257.
    """
    schrift, groesse = cv2.FONT_HERSHEY_SIMPLEX, 0.5
    (tw, _th), _ = cv2.getTextSize(text, schrift, groesse, 1)
    cv2.rectangle(bild, (10, hoehe - 35), (20 + tw, hoehe - 10), (0, 0, 0), -1)
    if bild.dtype == np.uint8:
        cv2.putText(bild, text, (15, hoehe - 18), schrift, groesse,
                    (hoechst, hoechst, hoechst), 1, cv2.LINE_AA)
        return bild
    maske = np.zeros(bild.shape[:2], np.uint8)
    cv2.putText(maske, text, (15, hoehe - 18), schrift, groesse, 255, 1, cv2.LINE_AA)
    y0, y1 = max(0, hoehe - 35), max(0, hoehe - 10) + 1
    x0, x1 = 10, 20 + tw + 1
    teil = maske[y0:y1, x0:x1].astype(np.float32) * (float(hoechst) / 255.0)
    ziel = bild[y0:y1, x0:x1]
    ziel[...] = (teil[..., None] + 0.5).astype(bild.dtype)
    return bild


def apply_hotpixel_fix(img, idx):
    """Ersetzt die als defekt erkannten Punkte durch den lokalen Median."""
    if idx is None:
        return img
    med = cv2.medianBlur(img, 3)
    img[idx] = med[idx]
    return img

def calculate_stabilization(files, status_sig, prog_sig, check_abort):
    transforms = [[0.0, 0.0, 0.0]]
    prev_gray = None
    prev_pts = None
    start_time = time.time()
    for i, f in enumerate(files):
        check_abort()
        img = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        scale = 800.0 / max(img.shape[0], img.shape[1])
        img_small = cv2.resize(img, (0, 0), fx=scale, fy=scale)
        if prev_gray is None:
            prev_gray = img_small
            prev_pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=200, qualityLevel=0.01, minDistance=30)
            continue
        if prev_pts is None or len(prev_pts) < 10:
            prev_pts = cv2.goodFeaturesToTrack(prev_gray, maxCorners=200, qualityLevel=0.01, minDistance=30)
        if prev_pts is not None and len(prev_pts) > 0:
            curr_pts, status, err = cv2.calcOpticalFlowPyrLK(prev_gray, img_small, prev_pts, None)
            idx = np.where(status == 1)[0]
            if len(idx) >= 10:
                m, inliers = cv2.estimateAffinePartial2D(prev_pts[idx], curr_pts[idx])
                if m is not None:
                    dx = m[0, 2] / scale
                    dy = m[1, 2] / scale
                    da = np.arctan2(m[1, 0], m[0, 0])
                    transforms.append([dx, dy, da])
                else:
                    transforms.append([0.0, 0.0, 0.0])
            else:
                transforms.append([0.0, 0.0, 0.0])
            prev_pts = curr_pts[idx].reshape(-1, 1, 2)
        else:
            transforms.append([0.0, 0.0, 0.0])
        prev_gray = img_small
        status_sig.emit(fortschritt_text("Analysiere Kamera-Wackeln",
                                         i + 1, len(files), start_time))
        prog_sig.emit(i + 1, len(files))
    traj = np.cumsum(transforms, axis=0)
    smoothed = np.copy(traj)
    smoothed[:, 0] = gaussian_filter1d(traj[:, 0], sigma=30, mode='nearest')
    smoothed[:, 1] = gaussian_filter1d(traj[:, 1], sigma=30, mode='nearest')
    smoothed[:, 2] = gaussian_filter1d(traj[:, 2], sigma=30, mode='nearest')
    return smoothed - traj

# ==========================================================================
#  SONNENSTAND (optionales Zusatzfeature, rein informativ)
# ==========================================================================
def compute_sun_elevation(times, lat, lon, utc_offset_hours):
    """
    Sonnenstand (Grad ueber Horizont) je Aufnahmezeitpunkt.
    times: Liste von datetime (wie von scan_exif() gelesen, ohne Zeitzone)
           oder None, wo der Zeitstempel fehlt.
    utc_offset_hours: Zeitzone der Kamera zur Aufnahmezeit, z.B. 2.0 für MESZ.
    Rückgabe: Liste von float, NaN wo kein Zeitstempel vorhanden ist.
    Rein optionales Feature: liefert nur NaN-Werte, wenn 'astral' fehlt oder
    lat/lon ungueltig sind - beeinflusst den eigentlichen Deflicker nicht.
    """
    import datetime
    try:
        from astral import Observer
        from astral.sun import elevation as sun_elevation
    except ImportError:
        return [float('nan')] * len(times)
    try:
        obs = Observer(latitude=float(lat), longitude=float(lon), elevation=0)
        tz = datetime.timezone(datetime.timedelta(hours=float(utc_offset_hours)))
    except (TypeError, ValueError):
        return [float('nan')] * len(times)
    out = []
    for t in times:
        if t is None:
            out.append(float('nan'))
            continue
        try:
            aware = t.replace(tzinfo=tz)
            out.append(float(sun_elevation(obs, aware)))
        except Exception:
            out.append(float('nan'))
    return out

# ==========================================================================
#  DIALOGE (ROI & CAMERA PATH)
# ==========================================================================
class ROIDialog(QtWidgets.QDialog):
    def __init__(self, qimg, parent=None, lang='de'):
        super().__init__(parent)
        de = (lang == 'de')
        self.setWindowTitle("Referenzbereich (ROI) markieren" if de
                            else "Mark reference area (ROI)")
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.roi_rel = None
        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Ziehe mit gedrückter linker Maustaste einen Rahmen. (Abbrechen = kein Rahmen)"
            if de else
            "Drag a frame with the left mouse button held down. (Cancel = no frame)")
        info.setStyleSheet("color: #ffaa00; font-weight: bold;")
        layout.addWidget(info)
        self.lbl = QtWidgets.QLabel()
        self.lbl.setPixmap(QtGui.QPixmap.fromImage(qimg))
        self.lbl.setCursor(QtCore.Qt.CrossCursor)
        layout.addWidget(self.lbl)
        self.rubberBand = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self.lbl)
        self.origin = QtCore.QPoint()
        self.lbl.mousePressEvent = self.mousePressEvent
        self.lbl.mouseMoveEvent = self.mouseMoveEvent
        self.lbl.mouseReleaseEvent = self.mouseReleaseEvent
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def mousePressEvent(self, event):
        self.origin = event.pos()
        self.rubberBand.setGeometry(QtCore.QRect(self.origin, QtCore.QSize()))
        self.rubberBand.show()

    def mouseMoveEvent(self, event):
        self.rubberBand.setGeometry(QtCore.QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        rect = self.rubberBand.geometry()
        w, h = self.lbl.width(), self.lbl.height()
        self.roi_rel = (rect.x() / w, rect.y() / h, rect.width() / w, rect.height() / h)


class CameraPathDialog(QtWidgets.QDialog):
    def __init__(self, img_path, current_kf, parent=None, lang='de'):
        super().__init__(parent)
        de = (lang == 'de')
        self.setWindowTitle("Kamerafahrt und 16:9 Ausschnitt festlegen" if de
                            else "Define camera move and 16:9 crop")
        self.setMinimumSize(1000, 700)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        img = load_preview_image(img_path, max_width=1800)
        if img is None:
            raise ValueError(f"Bild konnte nicht gelesen werden: {img_path}" if de
                             else f"Could not read image: {img_path}")
        self.img_h, self.img_w = img.shape[:2]
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        layout = QtWidgets.QHBoxLayout(self)
        self.view = pg.PlotWidget()
        self.view.setAspectLocked(True)
        self.view.invertY(True)
        self.view.hideAxis('left')
        self.view.hideAxis('bottom')
        img_item = pg.ImageItem(img_rgb, axisOrder='row-major')
        self.view.addItem(img_item)
        layout.addWidget(self.view, stretch=4)
        self.roi = pg.ROI([0, 0], [160, 90], pen=pg.mkPen('#ffaa00', width=3))
        self.roi.maxBounds = QtCore.QRectF(0, 0, self.img_w, self.img_h)
        self.roi.addScaleHandle([1, 1], [0, 0], lockAspect=True)
        self.roi.addScaleHandle([0, 0], [1, 1], lockAspect=True)
        self.roi.addScaleHandle([1, 0], [0, 1], lockAspect=True)
        self.roi.addScaleHandle([0, 1], [1, 0], lockAspect=True)
        self.view.addItem(self.roi)
        right_panel = QtWidgets.QVBoxLayout()
        info = QtWidgets.QLabel(
            "<b>Ausschnitt bestimmen (16:9)</b><br><br>Passe den Rahmen für Start- und "
            "Endpunkt an. Das Video fährt dann weich von A nach B." if de else
            "<b>Choose the crop (16:9)</b><br><br>Adjust the frame for the start and end "
            "point. The video then moves smoothly from A to B.")
        info.setWordWrap(True)
        right_panel.addWidget(info)
        right_panel.addSpacing(20)
        self.rb_start = QtWidgets.QRadioButton(
            "📍 Start-Bild (erstes Bild)" if de else "📍 Start frame (first image)")
        self.rb_start.setChecked(True)
        self.rb_start.setStyleSheet("font-weight: bold; color: #ffaa00;")
        self.rb_end = QtWidgets.QRadioButton(
            "🏁 End-Bild (letztes Bild)" if de else "🏁 End frame (last image)")
        self.rb_end.setStyleSheet("font-weight: bold; color: #00aaff;")
        right_panel.addWidget(self.rb_start)
        right_panel.addWidget(self.rb_end)
        right_panel.addSpacing(15)
        btn_copy = QtWidgets.QPushButton(
            "Start auf Ende kopieren" if de else "Copy start to end")
        btn_copy.setToolTip(
            "Setzt einen festen 16:9 Ausschnitt ohne Kamerafahrt." if de else
            "Sets a fixed 16:9 crop without a camera move.")
        right_panel.addWidget(btn_copy)
        right_panel.addStretch()
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        right_panel.addWidget(btn_box)
        layout.addLayout(right_panel, stretch=1)
        self.kf = current_kf or {}
        if not self.kf:
            w = self.img_w
            h = int(w * 9 / 16)
            if h > self.img_h:
                h = self.img_h
                w = int(h * 16 / 9)
            x = (self.img_w - w) / 2
            y = (self.img_h - h) / 2
            self.kf = {
                'start': [x / self.img_w, y / self.img_h, w / self.img_w, h / self.img_h],
                'end':   [x / self.img_w, y / self.img_h, w / self.img_w, h / self.img_h]
            }
        self._de = de
        self.active_state = 'start'
        self._set_roi_from_kf('start')
        self.roi.sigRegionChanged.connect(self._on_roi_changed)
        self.rb_start.toggled.connect(self._on_radio_toggled)
        btn_copy.clicked.connect(self._copy_start_to_end)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

    def _set_roi_from_kf(self, state):
        try:
            self.roi.sigRegionChanged.disconnect(self._on_roi_changed)
        except TypeError:
            pass
        rx, ry, rw, rh = self.kf[state]
        self.roi.setPos([rx * self.img_w, ry * self.img_h])
        self.roi.setSize([rw * self.img_w, rh * self.img_h])
        self.roi.sigRegionChanged.connect(self._on_roi_changed)

    def _on_roi_changed(self):
        pos = self.roi.pos()
        size = self.roi.size()
        rx = max(0.0, pos.x() / self.img_w)
        ry = max(0.0, pos.y() / self.img_h)
        rw = min(1.0, size.x() / self.img_w)
        rh = min(1.0, size.y() / self.img_h)
        self.kf[self.active_state] = [rx, ry, rw, rh]

    def _on_radio_toggled(self):
        if self.rb_start.isChecked():
            self.active_state = 'start'
            self.roi.setPen(pg.mkPen('#ffaa00', width=3))
        else:
            self.active_state = 'end'
            self.roi.setPen(pg.mkPen('#00aaff', width=3))
        self._set_roi_from_kf(self.active_state)

    def _copy_start_to_end(self):
        self.kf['end'] = list(self.kf['start'])
        if self.active_state == 'end':
            self._set_roi_from_kf('end')
        QtWidgets.QMessageBox.information(
            self, "Kopiert" if self._de else "Copied",
            "Der Start-Rahmen gilt jetzt auch für das Ende. Das Video zeigt damit "
            "einen festen 16:9 Ausschnitt ohne Bewegung." if self._de else
            "The start frame now also applies to the end. The video will show a "
            "fixed 16:9 crop without movement.")


class ResetDialog(QtWidgets.QDialog):
    """Arbeitsdateien im Bilderordner loeschen."""
    def __init__(self, target_dir, lang, parent=None):
        super().__init__(parent)
        self.target_dir = target_dir
        de = (lang == 'de')
        self.setWindowTitle("Zuruecksetzen" if de else "Reset")
        self.setMinimumWidth(560)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        groups = self._scan()
        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Waehle aus, was im Bilderordner geloescht werden soll.<br>"
            "<b>Deine RAW- und JPG-Dateien werden nie angetastet.</b>" if de else
            "Choose what to delete in the image folder.<br>"
            "<b>Your RAW and JPG files are never touched.</b>")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addSpacing(8)
        self.boxes = {}
        labels = {
            'logs': ("Protokolle und Messdaten (CSV, LOG)",
                     "Logs and measurement data (CSV, LOG)"),
            'state': ("Betriebsdaten (Deflicker-Basiswerte, Kalibrierung)",
                      "Working data (deflicker base values, calibration)"),
            'output': ("Entwickelte Bilder im Ordner Purelapse/Deflickered_JPG",
                       "Developed images in the Purelapse/Deflickered_JPG folder"),
            # Generisch statt "ART"/".arp und .xmp" hart codiert, damit der
            # Text zur jeweils aktiven Engine (ART/RawTherapee/Darktable) passt.
            'sidecars': (f"Sidecars ({eng('ext')} und .xmp) - LOESCHT DEINE "
                         f"{eng('label').upper()}-BEARBEITUNGEN UND KEYFRAMES",
                         f"Sidecars ({eng('ext')} and .xmp) - DELETES YOUR "
                         f"{eng('label').upper()} EDITS AND KEYFRAMES"),
        }
        for key in ('logs', 'state', 'output', 'sidecars'):
            files = groups[key]
            cb = QtWidgets.QCheckBox(f"{labels[key][0 if de else 1]}   ({len(files)})")
            cb.setEnabled(bool(files))
            if key in ('logs', 'state'):
                cb.setChecked(bool(files))
            if key == 'sidecars':
                cb.setStyleSheet("color: #ff6666; font-weight: bold;")
            layout.addWidget(cb)
            self.boxes[key] = cb
        layout.addSpacing(6)
        hint = QtWidgets.QLabel(
            "Ohne Sidecars bleiben Keyframes und Bearbeitungen erhalten; es genuegt dann,"
            " Pass 1 und Pass 2 erneut laufen zu lassen." if de else
            "Leaving the sidecars keeps your keyframes and edits; running pass 1 and"
            " pass 2 again is then enough.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888888; font-style: italic;")
        layout.addWidget(hint)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                         QtWidgets.QDialogButtonBox.Cancel)
        btn.button(QtWidgets.QDialogButtonBox.Ok).setText("Loeschen" if de else "Delete")
        btn.accepted.connect(self._confirm)
        btn.rejected.connect(self.reject)
        layout.addWidget(btn)
        self._groups = groups
        self._de = de
        self.deleted = 0

    def _scan(self):
        d = self.target_dir
        g = {'logs': [], 'state': [], 'output': [], 'sidecars': []}
        for name in PROTOKOLLE:
            p = pl_datei(d, name)
            if os.path.exists(p):
                g['logs'].append(p)
        for name in (DEFLICKER_DB, CALIB_DB):
            p = pl_datei(d, name)
            if os.path.exists(p):
                g['state'].append(p)
        out = zwischen_ordner(d)
        if os.path.isdir(out):
            g['output'] = sorted({p for ext in ZW_JPG + ZW_TIF
                                  for p in glob.glob(os.path.join(out, "*" + ext))})
        # Ueber ein Set gesammelt, damit .xmp (Darktable-Endung) nicht doppelt
        # gezaehlt wird, wenn eng('ext') bereits '.xmp' ist.
        sidecar_paths = set()
        for ext in ('*' + eng('ext'), '*' + eng('ext').upper(), "*.xmp", "*.XMP"):
            sidecar_paths.update(glob.glob(os.path.join(d, ext)))
        g['sidecars'] = sorted(sidecar_paths)
        return g

    def _confirm(self):
        chosen = [k for k, cb in self.boxes.items() if cb.isChecked()]
        if not chosen:
            self.reject()
            return
        n = sum(len(self._groups[k]) for k in chosen)
        if 'sidecars' in chosen:
            warn = ("Damit gehen alle vorgenommenen Bearbeitungen und alle "
                    "Keyframe-Markierungen unwiderruflich verloren.\n\n"
                    f"Insgesamt {n} Dateien loeschen?" if self._de else
                    "This permanently removes every edit and all keyframe "
                    f"marks.\n\nDelete {n} files in total?")
        else:
            warn = (f"{n} Dateien loeschen?" if self._de else f"Delete {n} files?")
        ok = QtWidgets.QMessageBox.warning(
            self, "Zuruecksetzen" if self._de else "Reset", warn,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No)
        if ok != QtWidgets.QMessageBox.Yes:
            return
        for k in chosen:
            for p in self._groups[k]:
                try:
                    os.remove(p)
                    self.deleted += 1
                except OSError:
                    pass
        # Leer gewordene Ordner mit wegraeumen (rmdir loescht nur leere)
        for leer in (zwischen_ordner(self.target_dir), pl_ordner(self.target_dir)):
            try:
                os.rmdir(leer)
            except OSError:
                pass
        self.accept()


class CompareDialog(QtWidgets.QDialog):
    """Zwei fertige Videos gegenueberstellen."""
    def __init__(self, start_dir, lang, parent=None):
        super().__init__(parent)
        de = (lang == 'de')
        self._de = de
        self.start_dir = start_dir
        self.setWindowTitle("Vergleichsvideo" if de else "Comparison video")
        self.setMinimumWidth(640)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        lay = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(
            "Stellt zwei bereits erzeugte Videos gegenueber. Ueblich ist die "
            "Rohfassung links und das bearbeitete Ergebnis rechts." if de else
            "Places two finished videos next to each other. Usually the untouched "
            "version on the left and the processed result on the right.")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addSpacing(8)
        self.txt_a = self._row(lay, "Links (Rohfassung):" if de else "Left (untouched):")
        self.txt_b = self._row(lay, "Rechts (bearbeitet):" if de else "Right (processed):")
        lay.addSpacing(8)
        lay.addWidget(QtWidgets.QLabel("Darstellung:" if de else "Layout:"))
        self.cmb_style = QtWidgets.QComboBox()
        self.cmb_style.addItems(
            ["Nebeneinander (beide Videos vollstaendig)",
             "Geteiltes Bild (linke Haelfte / rechte Haelfte)"] if de else
            ["Side by side (both videos in full)",
             "Split screen (left half / right half)"])
        lay.addWidget(self.cmb_style)
        hint = QtWidgets.QLabel(
            "Das geteilte Bild setzt voraus, dass beide Videos dieselbe Groesse und "
            "denselben Bildausschnitt haben." if de else
            "Split screen requires both videos to share the same size and framing.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888888; font-style: italic;")
        lay.addWidget(hint)
        lay.addSpacing(8)
        self.txt_out = self._row(lay, "Ziel-Datei:" if de else "Output file:", save=True)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                         QtWidgets.QDialogButtonBox.Cancel)
        btn.button(QtWidgets.QDialogButtonBox.Ok).setText("Erstellen" if de else "Create")
        btn.accepted.connect(self._check)
        btn.rejected.connect(self.reject)
        lay.addWidget(btn)

    def _row(self, lay, label, save=False):
        lay.addWidget(QtWidgets.QLabel(label))
        row = QtWidgets.QHBoxLayout()
        edit = QtWidgets.QLineEdit()
        edit.setReadOnly(not save)
        row.addWidget(edit, stretch=5)
        b = QtWidgets.QPushButton("...")
        b.setMaximumWidth(40)
        b.clicked.connect(lambda: self._pick(edit, save))
        row.addWidget(b, stretch=1)
        lay.addLayout(row)
        return edit

    def _pick(self, edit, save):
        flt = "Video (*.mp4 *.mov *.mkv);;" + ("Alle Dateien (*)" if self._de else "All files (*)")
        if save:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Ziel-Datei" if self._de else "Output file",
                os.path.join(self.start_dir, "Vergleich.mp4"), flt)
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Video waehlen" if self._de else "Select video", self.start_dir, flt)
        if path:
            edit.setText(path)
            if not self.txt_out.text():
                self.txt_out.setText(os.path.join(os.path.dirname(path), "Vergleich.mp4"))

    def _check(self):
        a, b, o = self.txt_a.text().strip(), self.txt_b.text().strip(), self.txt_out.text().strip()
        if not (os.path.isfile(a) and os.path.isfile(b)):
            QtWidgets.QMessageBox.warning(
                self, "Fehlt" if self._de else "Missing",
                "Bitte beide Videos auswaehlen." if self._de else "Please select both videos.")
            return
        if not o:
            QtWidgets.QMessageBox.warning(
                self, "Fehlt" if self._de else "Missing",
                "Bitte eine Ziel-Datei angeben." if self._de else "Please choose an output file.")
            return
        self.accept()

    def values(self):
        style = 'split' if self.cmb_style.currentIndex() == 1 else 'side'
        return (self.txt_a.text().strip(), self.txt_b.text().strip(),
                style, self.txt_out.text().strip())


class PreviewDialog(QtWidgets.QDialog):
    """Zeigt die Vorschaubilder nebeneinander mit Bildnummer."""
    def __init__(self, entries, lang, parent=None):
        super().__init__(parent)
        de = (lang == 'de')
        self.setWindowTitle("Vorschau der aktuellen Einstellungen" if de
                            else "Preview of the current settings")
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.resize(1100, 480)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel(
            "So sehen die fertigen Videobilder aus. Ausschnitt, Belichtung und "
            "Keyframe-Look sind bereits angewendet." if de else
            "This is what the finished video frames look like. Crop, exposure and "
            "keyframe look are already applied."))
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(inner)
        for idx, path in entries:
            col = QtWidgets.QVBoxLayout()
            pic = QtWidgets.QLabel()
            pm = QtGui.QPixmap(path)
            if not pm.isNull():
                pic.setPixmap(pm.scaledToWidth(340, QtCore.Qt.SmoothTransformation))
            pic.setAlignment(QtCore.Qt.AlignCenter)
            col.addWidget(pic)
            cap = QtWidgets.QLabel(("Bild " if de else "Frame ") + str(idx + 1))
            cap.setAlignment(QtCore.Qt.AlignCenter)
            cap.setStyleSheet("color: #ffaa00; font-weight: bold;")
            col.addWidget(cap)
            row.addLayout(col)
        row.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll)
        btn = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        btn.rejected.connect(self.reject)
        btn.accepted.connect(self.accept)
        lay.addWidget(btn)


# ==========================================================================
#  GALERIE-WORKER
# ==========================================================================
# ==========================================================================
#  ORDNERWAHL MIT VORSCHAU
#
#  Beim Oeffnen eines Bilderordners zeigt der Dialog rechts, was darin liegt:
#  Anzahl und Art der Bilder und ALLE Bilder als scrollbares Raster.
#  Geladen werden nur die Kacheln, die gerade zu sehen sind (plus eine Zeile
#  Vorlauf) - so bleibt das Durchklicken bei 50 wie bei 5000 Bildern
#  fluessig. Gelesen werden die eingebetteten Vorschaubilder der Kamera bzw.
#  JPGs in verkleinerter Aufloesung.
# ==========================================================================
ORDNER_KACHEL_B = 148      # Rasterzelle in logischen Pixeln
ORDNER_KACHEL_H = 104
ORDNER_BILD_KANTE = 280    # Vorschaubild doppelt so gross: scharf auf HiDPI


def ordner_bilder(ordner):
    """
    Die Bilder eines Ordners fuer die Ordnerwahl.
    Rueckgabe: (Liste der Bilder, Art) mit Art 'raw', 'jpg' oder None.
    RAW hat Vorrang - so arbeitet auch das Hauptfenster.
    """
    try:
        namen = sorted(os.listdir(ordner))
    except OSError:
        return [], None
    raw = [os.path.join(ordner, n) for n in namen if is_raw_file(n)]
    if raw:
        return raw, 'raw'
    jpg = [os.path.join(ordner, n) for n in namen if n.lower().endswith((".jpg", ".jpeg"))]
    return jpg, ('jpg' if jpg else None)


def raster_bereich(roll, hoehe, breite, anzahl, kachel_b=ORDNER_KACHEL_B,
                   kachel_h=ORDNER_KACHEL_H, vorlauf=1):
    """
    Welche Kacheln eines Rasters sind sichtbar?

    roll: Rollposition in Pixeln, hoehe/breite: sichtbarer Bereich.
    Rueckgabe: Liste der Indizes, die oben sichtbaren zuerst - in dieser
    Reihenfolge laedt der Hintergrundlader. Eine Zeile Vorlauf ober- und
    unterhalb, damit beim langsamen Scrollen kein Loch aufblitzt.
    """
    if anzahl <= 0 or hoehe <= 0:
        return []
    spalten = max(1, int(breite) // kachel_b)
    zeilen = (anzahl + spalten - 1) // spalten
    erste = max(0, int(roll) // kachel_h - vorlauf)
    letzte = min(zeilen - 1, (int(roll) + int(hoehe)) // kachel_h + vorlauf)
    return [i for z in range(erste, letzte + 1)
            for i in range(z * spalten, min(anzahl, (z + 1) * spalten))]


def ordner_vorschau_bild(pfad, kante=320):
    """Kleines Vorschaubild (BGR) - bei RAW das eingebettete der Kamera."""
    img = None
    try:
        if is_raw_file(pfad):
            with rawpy.imread(pfad) as raw:
                try:
                    thumb = raw.extract_thumb()
                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        # Eingebettete Vorschauen sind meist nur 1 bis 2 MP gross
                        img = cv2.imdecode(np.frombuffer(thumb.data, np.uint8), cv2.IMREAD_COLOR)
                    else:
                        img = cv2.cvtColor(thumb.data, cv2.COLOR_RGB2BGR)
                except Exception:
                    # Ohne eingebettetes Bild: selbst entwickeln, halbe Groesse
                    rgb = raw.postprocess(use_camera_wb=True, half_size=True, no_auto_bright=True)
                    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        else:
            img = cv2.imdecode(np.fromfile(pfad, dtype=np.uint8), cv2.IMREAD_REDUCED_COLOR_4)
    except Exception:
        img = None
    if img is None or img.size == 0:
        return None
    h, w = img.shape[:2]
    faktor = kante / float(max(h, w))
    if faktor < 1.0:
        img = cv2.resize(img, (max(1, int(w * faktor)), max(1, int(h * faktor))),
                         interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(img)


class OrdnerRasterLader(QtCore.QThread):
    """
    Laedt Vorschaubilder im Hintergrund, in der Reihenfolge einer
    Wunschliste, die der Dialog beim Scrollen jederzeit ersetzen kann.

    Ist die Liste leer, endet der Lader. Kommen danach neue Wuensche,
    legt der Dialog einen neuen an - wuenschen() sagt ihm, ob dieser hier
    noch annimmt. Beides geschieht unter derselben Sperre, damit kein
    Wunsch in einem gerade endenden Lader verloren geht.
    """
    bild = QtCore.pyqtSignal(int, int, object)

    def __init__(self, nummer, dateien, kante=ORDNER_BILD_KANTE):
        super().__init__()
        self.nummer = nummer
        self.dateien = list(dateien)
        self.kante = kante
        self._sperre = threading.Lock()
        self._wunsch = []
        self._nimmt_an = True
        self._abbruch = False

    def wuenschen(self, indizes):
        """Neue Wunschliste. False: dieser Lader ist schon fertig."""
        with self._sperre:
            if not self._nimmt_an:
                return False
            self._wunsch = [i for i in indizes if 0 <= i < len(self.dateien)]
            return True

    def abbrechen(self):
        with self._sperre:
            self._abbruch = True
            self._wunsch = []

    def run(self):
        while True:
            with self._sperre:
                if self._abbruch or not self._wunsch:
                    self._nimmt_an = False
                    return
                i = self._wunsch.pop(0)
            self.bild.emit(self.nummer, i, ordner_vorschau_bild(self.dateien[i], self.kante))


class OrdnerDialog(QtWidgets.QFileDialog):
    """Ordnerwahl, groesser als der Standard und mit allen Bildern als Raster."""

    def __init__(self, parent, titel, start, lang='de'):
        super().__init__(parent, titel, start)
        self._de = (lang != 'en')
        self.setFileMode(QtWidgets.QFileDialog.Directory)
        self.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
        self.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        self._nummer = 0
        self._lader = None
        self._alte_lader = []
        self._ordner = None
        self._bilder = []
        self._fertig = set()          # Kacheln, die schon ein Bild haben
        self._bau_vorschau()
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._laden)
        # Beim Scrollen kurz warten, bis die Position steht
        self._roll_timer = QtCore.QTimer(self)
        self._roll_timer.setSingleShot(True)
        self._roll_timer.setInterval(60)
        self._roll_timer.timeout.connect(self._sichtbare_laden)
        self.raster.verticalScrollBar().valueChanged.connect(lambda _w: self._roll_timer.start())
        self.currentChanged.connect(self._gewaehlt)
        self.directoryEntered.connect(self._gewaehlt)
        # Etwa die halbe Flaeche des Hauptfensters: 70 % Breite und Hoehe
        if parent is not None:
            self.resize(max(980, int(parent.width() * 0.7)),
                        max(600, int(parent.height() * 0.7)))
        self._gewaehlt(start)

    def _t(self, de, en):
        return de if self._de else en

    def _bau_vorschau(self):
        self.vorschau = QtWidgets.QFrame()
        self.vorschau.setObjectName("statuscard")
        # Platz fuer drei Spalten Kacheln samt Bildlaufleiste
        self.vorschau.setMinimumWidth(3 * ORDNER_KACHEL_B + 40)
        v = QtWidgets.QVBoxLayout(self.vorschau)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(6)
        self.lbl_v_titel = QtWidgets.QLabel(self._t("Vorschau", "Preview"))
        self.lbl_v_titel.setObjectName("statustitel")
        self.lbl_v_titel.setWordWrap(True)
        v.addWidget(self.lbl_v_titel)
        self.lbl_v_info = QtWidgets.QLabel("")
        self.lbl_v_info.setObjectName("hint")
        self.lbl_v_info.setWordWrap(True)
        v.addWidget(self.lbl_v_info)
        self.raster = QtWidgets.QListWidget()
        self.raster.setObjectName("ordnerraster")
        self.raster.setViewMode(QtWidgets.QListView.IconMode)
        self.raster.setMovement(QtWidgets.QListView.Static)
        self.raster.setResizeMode(QtWidgets.QListView.Adjust)
        self.raster.setUniformItemSizes(True)
        self.raster.setGridSize(QtCore.QSize(ORDNER_KACHEL_B, ORDNER_KACHEL_H))
        self.raster.setIconSize(QtCore.QSize(ORDNER_KACHEL_B - 8, ORDNER_KACHEL_H - 8))
        self.raster.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.raster.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.raster.verticalScrollBar().setSingleStep(ORDNER_KACHEL_H // 3)
        self.raster.setFocusPolicy(QtCore.Qt.NoFocus)
        v.addWidget(self.raster, 1)
        gitter = self.layout()
        if isinstance(gitter, QtWidgets.QGridLayout):
            gitter.addWidget(self.vorschau, 0, gitter.columnCount(), gitter.rowCount(), 1)

    def resizeEvent(self, ereignis):
        super().resizeEvent(ereignis)
        if hasattr(self, '_roll_timer'):
            self._roll_timer.start()       # breiter: mehr Spalten sichtbar

    def _gewaehlt(self, pfad):
        if pfad and os.path.isdir(pfad):
            self._ordner = pfad
            self._timer.start()

    def _anhalten(self):
        if self._lader is not None:
            self._lader.abbrechen()
            self._alte_lader.append(self._lader)
            self._lader = None
        self._alte_lader = [l for l in self._alte_lader if l.isRunning()]

    def _laden(self):
        ordner = self._ordner
        self._anhalten()
        self._nummer += 1
        self._fertig = set()
        self.raster.clear()
        bilder, art = ordner_bilder(ordner) if ordner else ([], None)
        self._bilder = bilder
        self.lbl_v_titel.setText(os.path.basename(os.path.normpath(ordner or "")) or (ordner or ""))
        if not bilder:
            self.lbl_v_info.setText(self._t("Keine Bilder in diesem Ordner.",
                                            "No images in this folder."))
            return
        endung = os.path.splitext(bilder[0])[1].lstrip(".").upper()
        anzahl = len(bilder)
        text = (self._t(f"{anzahl} Bilder ({endung})", f"{anzahl} images ({endung})"))
        text += "  ·  " + os.path.basename(bilder[0]) + " … " + os.path.basename(bilder[-1])
        if anzahl < 50:
            text += "\n" + self._t("Für einen Zeitraffer braucht Purelapse mindestens 50 Bilder.",
                                    "Purelapse needs at least 50 images for a timelapse.")
        self.lbl_v_info.setText(text)
        # Leere Kacheln fuer alle Bilder - die Bilder kommen beim Scrollen
        for i, pfad in enumerate(bilder):
            eintrag = QtWidgets.QListWidgetItem()
            eintrag.setToolTip(f"{i + 1}  ·  {os.path.basename(pfad)}")
            eintrag.setSizeHint(QtCore.QSize(ORDNER_KACHEL_B, ORDNER_KACHEL_H))
            self.raster.addItem(eintrag)
        self.raster.verticalScrollBar().setValue(0)
        self._sichtbare_laden()

    def _sichtbare_laden(self):
        """Laedt, was gerade zu sehen ist und noch kein Bild hat."""
        if not self._bilder:
            return
        sicht = self.raster.viewport()
        wunsch = [i for i in raster_bereich(self.raster.verticalScrollBar().value(),
                                            sicht.height(), sicht.width(), len(self._bilder))
                  if i not in self._fertig]
        if not wunsch:
            return
        if self._lader is not None and self._lader.wuenschen(wunsch):
            return
        if self._lader is not None:
            self._alte_lader.append(self._lader)
        self._lader = OrdnerRasterLader(self._nummer, self._bilder)
        self._lader.bild.connect(self._bild_da)
        self._lader.wuenschen(wunsch)
        self._lader.start()

    def _bild_da(self, nummer, index, img):
        if nummer != self._nummer or not (0 <= index < self.raster.count()):
            return
        self._fertig.add(index)
        if img is None:
            return
        h, w = img.shape[:2]
        rgb = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        qimg = QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format_RGB888).copy()
        self.raster.item(index).setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(qimg)))

    def done(self, ergebnis):
        self._timer.stop()
        self._roll_timer.stop()
        self._anhalten()
        for l in self._alte_lader:
            l.wait(2000)
        super().done(ergebnis)

    def ordner(self):
        """Der gewaehlte Ordner nach exec_(), sonst ''."""
        wahl = self.selectedFiles()
        return wahl[0] if wahl else ""


class VorschauLader(QtCore.QThread):
    """
    Laedt das Vorschaubild einmalig im Hintergrund.

    Ein RAW zu entwickeln dauert auch in halber Aufloesung rund eine
    Sekunde. Im Hauptfaden wuerde der Dialog so lange einfrieren, noch
    bevor man den ersten Regler sieht.
    """
    fertig = QtCore.pyqtSignal(object)

    def __init__(self, pfad):
        super().__init__()
        self.pfad = pfad

    def run(self):
        try:
            bild, pegel = vorschau_basis_pegel(self.pfad)
        except Exception:
            bild, pegel = None, 0.0
        iso = 100
        try:
            iso = int(get_exif_data(self.pfad).get('iso', 100) or 100)
        except Exception:
            pass
        self.fertig.emit((bild, iso, pegel))


class ZoomBild(QtWidgets.QScrollArea):
    """
    Vorschaubild zum Hineinzoomen.

    Mausrad: zoomen, an der Stelle unter dem Mauszeiger. Ziehen mit der
    linken Maustaste: verschieben. Doppelklick: wieder das ganze Bild.
    Nimmt dieselben Aufrufe an wie das QLabel, das hier vorher stand
    (setPixmap, setText).
    """

    def __init__(self, parent=None, lang='de'):
        super().__init__(parent)
        self._pixmap = None
        self._zoom = 1.0
        self._zieh = None
        self.setWidgetResizable(False)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._lbl = QtWidgets.QLabel()
        self._lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.setWidget(self._lbl)
        self.viewport().installEventFilter(self)
        if lang == 'en':
            self.setToolTip("Mouse wheel: zoom  \u00b7  Drag: pan  "
                            "\u00b7  Double-click: whole image")
        else:
            self.setToolTip("Mausrad: zoomen  \u00b7  Ziehen: verschieben  "
                            "\u00b7  Doppelklick: ganzes Bild")

    def setText(self, text):
        self._pixmap = None
        self._lbl.setPixmap(QtGui.QPixmap())
        self._lbl.setText(text)
        self._lbl.adjustSize()

    def setPixmap(self, pixmap):
        self._pixmap = pixmap
        self._zeichnen()

    def zoom(self):
        return self._zoom

    def _passend(self):
        """Faktor, mit dem das ganze Bild gerade hineinpasst."""
        pm = self._pixmap
        if pm is None or pm.isNull() or pm.width() <= 0 or pm.height() <= 0:
            return 1.0
        vp = self.viewport()
        return min(max(1, vp.width()) / float(pm.width()),
                   max(1, vp.height()) / float(pm.height()))

    def _zeichnen(self):
        pm = self._pixmap
        if pm is None or pm.isNull():
            return
        f = self._passend() * self._zoom
        b = max(1, int(round(pm.width() * f)))
        h = max(1, int(round(pm.height() * f)))
        self._lbl.setPixmap(pm.scaled(b, h, QtCore.Qt.KeepAspectRatio,
                                      QtCore.Qt.SmoothTransformation))
        self._lbl.resize(b, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._zeichnen()

    def zoom_setzen(self, neu, pos=None):
        """Zoomt auf 'neu' (1 = ganzes Bild); der Punkt unter 'pos' bleibt stehen."""
        neu = max(1.0, min(ZOOM_MAX, float(neu)))
        if abs(neu - self._zoom) < 1e-6:
            return
        hb, vb = self.horizontalScrollBar(), self.verticalScrollBar()
        anteil = None
        if pos is not None and self._lbl.width() > 0 and self._lbl.height() > 0:
            p = self._lbl.mapFrom(self.viewport(), pos)
            anteil = (p.x() / float(self._lbl.width()), p.y() / float(self._lbl.height()))
        self._zoom = neu
        self._zeichnen()
        if anteil is not None:
            hb.setValue(int(anteil[0] * self._lbl.width() - pos.x()))
            vb.setValue(int(anteil[1] * self._lbl.height() - pos.y()))

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            typ = event.type()
            if typ == QtCore.QEvent.Wheel:
                try:
                    delta = event.angleDelta().y()
                except Exception:
                    delta = 0
                if delta:
                    self.zoom_setzen(self._zoom * (1.25 if delta > 0 else 0.8),
                                     event.pos())
                return True
            if typ == QtCore.QEvent.MouseButtonDblClick:
                self.zoom_setzen(1.0)
                return True
            if (typ == QtCore.QEvent.MouseButtonPress
                    and event.button() == QtCore.Qt.LeftButton and self._zoom > 1.0):
                self._zieh = (event.pos(), self.horizontalScrollBar().value(),
                              self.verticalScrollBar().value())
                self.viewport().setCursor(QtCore.Qt.ClosedHandCursor)
                return True
            if typ == QtCore.QEvent.MouseMove and self._zieh is not None:
                start, h0, v0 = self._zieh
                d = event.pos() - start
                self.horizontalScrollBar().setValue(h0 - d.x())
                self.verticalScrollBar().setValue(v0 - d.y())
                return True
            if typ == QtCore.QEvent.MouseButtonRelease and self._zieh is not None:
                self._zieh = None
                self.viewport().unsetCursor()
                return True
        return super().eventFilter(obj, event)


class EngineVorschau(QtCore.QThread):
    """
    Laesst die Engine ein Bild mit einem bestimmten Profil entwickeln.

    Das ist die einzige Vorschau, die stimmt: dieselbe Engine, derselbe
    Aufruf und dasselbe Profil wie spaeter in Pass 2, nur kleiner
    ausgegeben. Gearbeitet wird in einem eigenen Ordner, der danach
    wieder verschwindet - die Begleitdatei des Bildes bleibt unberuehrt.
    """
    fertig = QtCore.pyqtSignal(object)

    def __init__(self, cli, bild, profil, kennung, kante=VORSCHAU_BREITE):
        super().__init__()
        self.cli = cli
        self.bild = bild
        self.profil = profil
        self.kennung = kennung
        self.kante = kante
        self._proc = None
        self._abbruch = False

    def abbrechen(self):
        """Die Regler stehen inzwischen anders - dieses Bild will keiner mehr."""
        self._abbruch = True
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    def run(self):
        start = time.time()
        erg = {'kennung': self.kennung, 'rgb': None, 'dauer': 0.0,
               'fehler': "", 'abgebrochen': False, 'faden': self}
        ordner = tempfile.mkdtemp(prefix="purelapse_vorschau_")
        try:
            if eng('kind') == 'darktable':
                slots, _q = dt_konfig_slots(1, os.path.join(cache_ordner(), "darktable_vorschau"))
                cmd, ziel = dt_vorschau_befehl(self.cli, self.bild, self.profil,
                                               ordner, self.kante, configdir=slots[0])
            else:
                profil_pfad = os.path.join(ordner, "vorschau" + eng('ext'))
                ziel = os.path.join(ordner, "vorschau.jpg")
                write_arp_dict_ini(profil_pfad,
                                   vorschau_profil(self.profil, self.kante))
                cmd = vorschau_befehl(self.cli, self.bild, profil_pfad, ziel)
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                          stderr=subprocess.STDOUT)
            if self._abbruch:
                self._proc.kill()
            try:
                ausgabe, _ = self._proc.communicate(timeout=240)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                ausgabe, _ = self._proc.communicate()
                erg['fehler'] = "Zeitueberschreitung"
            if self._abbruch:
                erg['abgebrochen'] = True
            elif os.path.exists(ziel):
                roh = cv2.imdecode(np.fromfile(ziel, dtype=np.uint8),
                                   cv2.IMREAD_COLOR)
                if roh is not None:
                    erg['rgb'] = np.ascontiguousarray(
                        cv2.cvtColor(roh, cv2.COLOR_BGR2RGB))
            if erg['rgb'] is None and not erg['abgebrochen'] and not erg['fehler']:
                zeilen = [z.strip() for z in
                          (ausgabe or b"").decode("utf-8", "ignore").splitlines()
                          if z.strip()]
                erg['fehler'] = zeilen[-1][:200] if zeilen else "kein Bild erhalten"
        except Exception as e:
            erg['fehler'] = str(e)[:200]
        finally:
            # Nach einem Abbruch kann die Engine noch einen Augenblick an
            # ihren Dateien haengen - dann kurz warten und nachfassen.
            for _ in range(20):
                shutil.rmtree(ordner, ignore_errors=True)
                if not os.path.exists(ordner):
                    break
                time.sleep(0.05)
        erg['dauer'] = time.time() - start
        self.fertig.emit(erg)


class QuickLookDialog(QtWidgets.QDialog):
    """
    Schnelleinstellungen fuer ein Keyframe-Bild, ohne ART oder
    RawTherapee zu oeffnen.

    Geschrieben wird in das Sidecar des Bildes. Die vorhandene
    Keyframe-Interpolation traegt die Werte danach auf die Nachbarbilder
    weiter - diese Funktion muss dafuer selbst nichts tun.

    Zwei Entwurfsentscheidungen, die man im Dialog sieht:

    Jeder Regler hat ein eigenes Haekchen. Ohne Haekchen wird der Wert im
    Profil nicht angefasst. Sonst wuerde das Oeffnen und Schliessen des
    Dialogs eine in ART gemachte Bearbeitung mit Neutralwerten
    ueberschreiben.

    Regler, deren Sektion im Profil fehlt, werden gesperrt und nicht
    stillschweigend geschrieben. Ein Schluessel, den die Engine nicht
    kennt, wuerde beim Entwickeln ohne Fehlermeldung verfallen.
    """

    def __init__(self, parent, bildname, profil, lang='de', bild_pfad=None,
                 andere=None, cli_pfad=None):
        super().__init__(parent)
        self.lang = lang
        # Echte Vorschau: die Engine entwickelt selbst. Geht nur mit einem
        # RAW, einem auffindbaren Programm und einem INI-Profil.
        self._profil0 = {sec: dict(par) for sec, par in (profil or {}).items()}
        self._cli = None
        if (cli_pfad and os.path.isfile(cli_pfad) and eng('kind') in ('ini', 'darktable')
                and bild_pfad and is_raw_file(bild_pfad)
                and profile_is_complete(profil)):
            self._cli = cli_pfad
        self._echt_merker = {}       # Kennung -> Bild der Engine
        self._echt_fehlschlag = set()
        self._echt_faden = None      # laeuft gerade
        self._echt_alle = []         # alle je gestarteten, bis zum Schliessen
        self._echt_bild = None       # zuletzt gezeigtes Bild der Engine
        self._echt_zustand = None    # die Einstellungen dazu
        self._echt_lin = None        # dasselbe, linear und in Anzeigegroesse
        self._gezeigt_echt = False
        self._pegel = 1.0
        self._zu = False
        self._de = (lang != 'en')
        self.bild_pfad = bild_pfad
        self._basis_voll = None     # Vorschaubild in voller Ladegroesse
        self._basis = None          # auf die Anzeigebreite gebracht
        self._anzeige_breite = 0
        self._iso = 100
        self._lader = None
        self._andere = list(andere or [])   # [(Name, Sidecar-Pfad), ...]
        self.setWindowTitle(self._t(f"Schnelleinstellungen - {bildname}",
                                    f"Quick settings - {bildname}"))
        self.setMinimumWidth(620)
        self.setSizeGripEnabled(True)
        # Groesser starten, damit man auf dem Bild etwas erkennt; das
        # Fenster laesst sich darueber hinaus ziehen, die Vorschau waechst
        # bis zur geladenen Aufloesung mit.
        self.resize(940, 860)
        self.regler = {}          # id -> (QCheckBox, QSlider, QLabel, def)
        self._ursprung = {}       # id -> (Reglerstellung, Haken) beim Oeffnen
        vorhanden, fehlend = quick_available(profil)
        werte = quick_read(profil)

        aussen = QtWidgets.QVBoxLayout(self)
        kopf = QtWidgets.QLabel(self._t(
            f"Die Werte gehen in das {eng('ext')}-Profil dieses Keyframes. "
            f"{eng('label')} entwickelt danach damit, und die Keyframe-"
            "Interpolation traegt sie weich auf die Nachbarbilder weiter.\n"
            "Die Belichtung bleibt ausgenommen - die gehoert dem Deflicker.",
            f"The values go into this keyframe's {eng('ext')} profile. "
            f"{eng('label')} then develops with them, and keyframe "
            "interpolation carries them smoothly to the neighbouring "
            "frames.\nExposure is left out - that belongs to the "
            "deflicker."))
        kopf.setWordWrap(True)
        aussen.addWidget(kopf)

        # ---- Vorschau -------------------------------------------------
        self.lbl_vorschau = ZoomBild(lang=self.lang)
        self.lbl_vorschau.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_vorschau.setMinimumHeight(260)
        self.lbl_vorschau.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                        QtWidgets.QSizePolicy.Expanding)
        self.lbl_vorschau.setText(self._t("Vorschau wird geladen…",
                                          "Loading preview…"))
        # Bild und Histogramm nebeneinander: das Bild bekommt die ganze
        # Hoehe, das Histogramm steht rechts oben daneben.
        zeile_bild = QtWidgets.QHBoxLayout()
        zeile_bild.setSpacing(10)
        zeile_bild.addWidget(self.lbl_vorschau, stretch=1)
        spalte_hist = QtWidgets.QVBoxLayout()
        spalte_hist.setSpacing(4)
        aussen.addLayout(zeile_bild, stretch=1)
        self.lbl_histogramm = QtWidgets.QLabel()
        self.lbl_histogramm.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_histogramm.setFixedHeight(HISTOGRAMM_HOEHE)
        self.lbl_histogramm.setToolTip(self._t(
            "Verteilung von Rot, Gruen und Blau im Vorschaubild.\n"
            "Ein blauer Streifen links heisst: Tiefen laufen zu.\n"
            "Ein roter Streifen rechts heisst: Lichter brennen aus.",
            "Distribution of red, green and blue in the preview.\n"
            "A blue bar on the left means shadows are being crushed.\n"
            "A red bar on the right means highlights are blowing out."))
        self.lbl_histogramm.setFixedWidth(HISTOGRAMM_BREITE)
        spalte_hist.addWidget(self.lbl_histogramm)
        spalte_hist.addStretch()
        zeile_bild.addLayout(spalte_hist)
        # Groesse der Anzeige nachfuehren, wenn das Fenster gezogen wird.
        self._groesse_timer = QtCore.QTimer(self)
        self._groesse_timer.setSingleShot(True)
        self._groesse_timer.setInterval(90)
        self._groesse_timer.timeout.connect(self._vorschau_neu_skalieren)
        zeile_v = QtWidgets.QHBoxLayout()
        self.chk_vorher = QtWidgets.QCheckBox(self._t("Vorher zeigen",
                                                      "Show before"))
        self.chk_vorher.setToolTip(self._t(
            "Zeigt das Bild ohne die hier gesetzten Werte, zum Vergleich.",
            "Shows the image without the values set here, for comparison."))
        self.chk_vorher.toggled.connect(self._vorschau_anfordern)
        zeile_v.addWidget(self.chk_vorher)
        self.chk_echt = QtWidgets.QCheckBox(self._t(
            f"Echte Vorschau ({eng('label')})",
            f"True preview ({eng('label')})"))
        self.chk_echt.setChecked(self._cli is not None)
        self.chk_echt.setEnabled(self._cli is not None)
        self.chk_echt.setToolTip(self._t(
            f"{eng('label')} entwickelt das Bild selbst, mit genau dem "
            "Profil, das beim Speichern geschrieben wird. Die Vorschau "
            "zeigt damit, was Pass 2 aus diesem Bild macht - auch Schaerfe "
            "und Entrauschen.\n\n"
            "Das dauert je Aenderung ein paar Sekunden. Waehrend man einen "
            "Regler bewegt, steht kurz eine Naeherung da; sobald der Regler "
            "ruht, kommt das echte Bild.\n\n"
            "Ohne Haekchen bleibt es bei der Naeherung."
            + ("" if self._cli else
               f"\n\nNicht verfuegbar: der Pfad zu {eng('bin')} fehlt, "
               "oder das Bild ist kein RAW."),
            f"{eng('label')} develops the image itself, with exactly the "
            "profile that is written on saving. The preview therefore "
            "shows what pass 2 makes of this frame - sharpening and "
            "denoising included.\n\n"
            "This takes a few seconds per change. While a slider moves an "
            "approximation is shown; once it rests the true image "
            "follows.\n\nWithout the tick the approximation stays."
            + ("" if self._cli else
               f"\n\nNot available: the path to {eng('bin')} is missing, "
               "or the image is not a RAW file.")))
        self.chk_echt.toggled.connect(self._vorschau_anfordern)
        zeile_v.addWidget(self.chk_echt)
        self.lbl_echt = QtWidgets.QLabel("")
        self.lbl_echt.setStyleSheet("font-size: 10px; font-weight: bold;")
        zeile_v.addWidget(self.lbl_echt)
        zeile_v.addStretch()
        self._echt_timer = QtCore.QTimer(self)
        self._echt_timer.setSingleShot(True)
        self._echt_timer.setInterval(ECHT_WARTEZEIT_MS)
        self._echt_timer.timeout.connect(self._echt_starten)
        self.lbl_vorschau_hinweis = QtWidgets.QLabel(self._t(
            "Näherung: Weißabgleich, Helligkeit, Kontrast, Sättigung. "
            "Schärfe und Entrauschen zeigt sie nicht. Das endgültige "
            f"Aussehen bestimmt {eng('label')}."
            if self._cli is None else
            f"Das Bild entwickelt {eng('label')} selbst - so sieht es "
            "nach Pass 2 aus. Beim Schieben steht kurz eine Näherung da.",
            "Approximation: white balance, brightness, contrast, "
            "saturation. Sharpening and denoising are not shown. "
            f"{eng('label')} decides the final look."
            if self._cli is None else
            f"{eng('label')} develops the image itself - this is how it "
            "looks after pass 2. While sliding, an approximation is shown "
            "briefly."))
        self.lbl_vorschau_hinweis.setWordWrap(True)
        self.lbl_vorschau_hinweis.setStyleSheet("font-size: 10px;")
        zeile_v.addWidget(self.lbl_vorschau_hinweis, stretch=1)
        aussen.addLayout(zeile_v)

        # Neuzeichnen gebuendelt: beim Ziehen eines Reglers kommen viele
        # Ereignisse kurz hintereinander.
        self._v_timer = QtCore.QTimer(self)
        self._v_timer.setSingleShot(True)
        self._v_timer.setInterval(40)
        self._v_timer.timeout.connect(self._vorschau_zeichnen)

        # ---- Lichter-Rekonstruktion -----------------------------------
        self.cmb_hl = None
        self._hl_verfuegbar = hl_verfuegbar(profil)
        if self._hl_verfuegbar:
            zeile_hl = QtWidgets.QHBoxLayout()
            self.chk_hl = QtWidgets.QCheckBox(
                self._t("Lichter rekonstruieren", "Reconstruct highlights"))
            zeile_hl.addWidget(self.chk_hl)
            self.cmb_hl = QtWidgets.QComboBox()
            for schluessel, name, erklaerung in hl_optionen():
                if schluessel == "Off":
                    continue
                self.cmb_hl.addItem(name, schluessel)
                self.cmb_hl.setItemData(self.cmb_hl.count() - 1,
                                        f"{name}: {erklaerung}",
                                        QtCore.Qt.ToolTipRole)
            jetzt = hl_lesen(profil)
            if jetzt != "Off":
                idx = self.cmb_hl.findData(jetzt)
                if idx >= 0:
                    self.cmb_hl.setCurrentIndex(idx)
                self.chk_hl.setChecked(True)
            else:
                idx = self.cmb_hl.findData(hl_empfohlen())
                if idx >= 0:
                    self.cmb_hl.setCurrentIndex(idx)
            hinweis_hl = self._t(
                "Gegen ausgebrannte Lichter, die farbig statt weiss werden "
                "- der rosa Sonnenball.\n\n"
                "Grund: im Kern der Sonne steht Gruen zuerst am Anschlag, "
                "und die Faktoren des Weissabgleichs heben Rot und Blau "
                "danach weiter an. Eine negative Belichtung hilft dagegen "
                "nicht, sie macht den Fleck nur dunkler.\n\n"
                "Die Rekonstruktion schaetzt den fehlenden Kanal aus der "
                "Umgebung.",
                "Against blown highlights that turn coloured instead of "
                "white - the pink sun.\n\nReason: in the sun's core green "
                "saturates first, and the white balance factors then lift "
                "red and blue further. Negative exposure does not help, it "
                "only makes the patch darker.\n\nReconstruction estimates "
                "the missing channel from its surroundings.")
            self.chk_hl.setToolTip(hinweis_hl)
            self.cmb_hl.setToolTip(hinweis_hl)
            self.chk_hl.toggled.connect(self.cmb_hl.setEnabled)
            self.cmb_hl.setEnabled(self.chk_hl.isChecked())
            self.chk_hl.toggled.connect(self._vorschau_anfordern)
            self.cmb_hl.currentIndexChanged.connect(self._vorschau_anfordern)
            zeile_hl.addWidget(self.cmb_hl, stretch=1)
            self.lbl_hl_warnung = QtWidgets.QLabel()
            self.lbl_hl_warnung.setWordWrap(True)
            self.lbl_hl_warnung.setVisible(False)
            zeile_hl.addWidget(self.lbl_hl_warnung, stretch=2)
            aussen.addLayout(zeile_hl)
            self._hl_ursprung = (self.chk_hl.isChecked(),
                                 self.cmb_hl.currentIndex())

        if self._andere:
            zeile_u = QtWidgets.QHBoxLayout()
            zeile_u.addWidget(QtWidgets.QLabel(
                self._t("Von anderem Keyframe übernehmen:",
                        "Copy from another keyframe:")))
            self.cmb_uebernehmen = QtWidgets.QComboBox()
            self.cmb_uebernehmen.addItem(self._t("— auswählen —",
                                                 "— choose —"))
            for name, _pfad in self._andere:
                self.cmb_uebernehmen.addItem(name)
            self.cmb_uebernehmen.setToolTip(self._t(
                "Liest die Schnelleinstellungen aus dem Profil eines "
                "anderen Keyframes und setzt sie hier ein.\n\n"
                "Gespeichert wird dadurch nichts - das Ergebnis steht "
                "sofort in der Vorschau, und \u201eZurücksetzen\u201c "
                "nimmt es wieder zurueck.",
                "Reads the quick settings from another keyframe's profile "
                "and applies them here.\n\nNothing is saved by this - the "
                "result appears in the preview straight away, and "
                "\u201cReset\u201d undoes it."))
            self.cmb_uebernehmen.currentIndexChanged.connect(self._uebernehmen)
            zeile_u.addWidget(self.cmb_uebernehmen, stretch=1)
            aussen.addLayout(zeile_u)

        gitter = QtWidgets.QGridLayout()
        gitter.setColumnStretch(2, 1)   # der Schieber bekommt den Platz
        gitter.setHorizontalSpacing(4)
        zeile = 0
        for d in vorhanden:
            chk = QtWidgets.QCheckBox(self._t(d['de'], d['en']))
            # Vorangekreuzt nur, wo das Profil schon vom Neutralwert
            # abweicht - dort ist bereits etwas eingestellt.
            abweichung = abs(werte[d['id']] - float(d['neutral']))
            toleranz = max(1e-6, abs(float(d['neutral'])) * 1e-6, 10 ** -(d['dezimal'] + 1))
            chk.setChecked(abweichung > toleranz)
            chk.setToolTip(self._t(
                f"Schreibt [{d['sec']}] {d['key']} in das Profil.\n"
                "Ohne Haekchen bleibt der vorhandene Wert unberuehrt.",
                f"Writes [{d['sec']}] {d['key']} into the profile.\n"
                "Without the tick the existing value stays untouched."))
            faktor = 10 ** d['dezimal']
            sl = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            sl.setMinimum(int(round(d['ui_min'] * faktor)))
            sl.setMaximum(int(round(d['ui_max'] * faktor)))
            schritt = max(1, int(round(d['schritt'] * faktor)))
            sl.setSingleStep(schritt)
            sl.setPageStep(schritt * 10)
            start = max(d['ui_min'], min(d['ui_max'], werte[d['id']]))
            sl.setValue(int(round(start * faktor)))
            lbl = QtWidgets.QLabel()
            lbl.setMinimumWidth(78)
            lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            btn_neutral = QtWidgets.QPushButton(self._t("neutral", "neutral"))
            btn_neutral.setMaximumWidth(72)
            btn_neutral.setToolTip(self._t(
                f"Setzt den Regler auf {d['neutral']} - den Wert, bei dem "
                "die Engine nichts tut.",
                f"Sets the slider to {d['neutral']} - the value at which "
                "the engine does nothing."))
            # Feinschritt: ein Fuenftel des normalen Schritts, mindestens
            # die kleinste darstellbare Stufe. Mit der Maus trifft man auf
            # einem 300 Pixel breiten Schieber keine 10 Kelvin.
            fein = max(1, int(round(d['schritt'] * faktor)) // 5)
            fein_anzeige = fein / float(faktor)
            btn_minus = QtWidgets.QPushButton("\u2212")
            btn_plus = QtWidgets.QPushButton("+")
            for b in (btn_minus, btn_plus):
                b.setFixedWidth(30)
                b.setAutoRepeat(True)
                b.setAutoRepeatDelay(350)
                b.setAutoRepeatInterval(60)
            btn_minus.setToolTip(self._t(
                f"Eine Stufe kleiner ({fein_anzeige:g}). Gedrueckt halten "
                "laeuft weiter.",
                f"One step down ({fein_anzeige:g}). Hold to repeat."))
            btn_plus.setToolTip(self._t(
                f"Eine Stufe groesser ({fein_anzeige:g}). Gedrueckt halten "
                "laeuft weiter.",
                f"One step up ({fein_anzeige:g}). Hold to repeat."))

            def schritt_machen(_=None, sl=sl, fein=fein, richtung=1):
                sl.setValue(sl.value() + richtung * fein)

            btn_minus.clicked.connect(
                lambda _=None, f=schritt_machen: f(richtung=-1))
            btn_plus.clicked.connect(
                lambda _=None, f=schritt_machen: f(richtung=1))

            def zeige(_=None, d=d, sl=sl, lbl=lbl, faktor=faktor):
                v = sl.value() / float(faktor)
                lbl.setText(f"{v:.{d['dezimal']}f}{d['einheit']}")

            def auf_neutral(_=None, d=d, sl=sl, faktor=faktor):
                ziel = max(d['ui_min'], min(d['ui_max'], float(d['neutral'])))
                sl.setValue(int(round(ziel * faktor)))

            sl.valueChanged.connect(zeige)
            sl.valueChanged.connect(self._vorschau_anfordern)
            chk.toggled.connect(self._vorschau_anfordern)
            btn_neutral.clicked.connect(auf_neutral)
            for w in (sl, btn_neutral, btn_minus, btn_plus):
                chk.toggled.connect(w.setEnabled)
                w.setEnabled(chk.isChecked())
            zeige()

            gitter.addWidget(chk, zeile, 0)
            gitter.addWidget(lbl, zeile, 1)
            gitter.addWidget(sl, zeile, 2)
            gitter.addWidget(btn_minus, zeile, 3)
            gitter.addWidget(btn_plus, zeile, 4)
            gitter.addWidget(btn_neutral, zeile, 5)
            self.regler[d['id']] = (chk, sl, lbl, d)
            self._ursprung[d['id']] = (sl.value(), chk.isChecked())
            zeile += 1
        aussen.addLayout(gitter)

        if fehlend:
            namen = ", ".join(self._t(d['de'], d['en']) for d in fehlend)
            sek = ", ".join(sorted({d['sec'] for d in fehlend}))
            hinweis = QtWidgets.QLabel(self._t(
                f"Nicht verfuegbar: {namen}.\nDas Basisprofil enthaelt die "
                f"Sektion(en) [{sek}] nicht. Purelapse schreibt dort nichts "
                "hinein, weil die Engine einen unbekannten Schluessel ohne "
                "Fehlermeldung verwerfen wuerde. Das Profil einmal in "
                f"{eng('label')} mit diesen Werkzeugen speichern, dann sind "
                "die Regler da.",
                f"Not available: {namen}.\nThe base profile does not contain "
                f"the section(s) [{sek}]. Purelapse writes nothing there, "
                "because the engine would discard an unknown key without "
                f"any error. Save the profile once in {eng('label')} with "
                "those tools and the sliders will appear."))
            hinweis.setWordWrap(True)
            hinweis.setStyleSheet("font-size: 11px;")
            aussen.addWidget(hinweis)

        if not vorhanden:
            leer = QtWidgets.QLabel(self._t(
                "Fuer dieses Profil stehen keine Schnelleinstellungen zur "
                "Verfuegung.",
                "No quick settings are available for this profile."))
            leer.setWordWrap(True)
            aussen.addWidget(leer)

        # Ausgangswerte aus dem Profil - die Vorschau rechnet die
        # Differenz dazu, nicht einen absoluten Zustand.
        self._basis_temp = werte.get('wb_temp', 5500.0)
        self._basis_gruen = werte.get('wb_green', 1.0)
        if self.bild_pfad and os.path.exists(self.bild_pfad):
            self._lader = VorschauLader(self.bild_pfad)
            self._lader.fertig.connect(self._vorschau_geladen)
            self._lader.start()
        else:
            self.lbl_vorschau.setText(self._t("Keine Vorschau verfügbar.",
                                              "No preview available."))
            self.lbl_vorschau.setMinimumHeight(0)

        aussen.addStretch()
        knoepfe = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.btn_auto = knoepfe.addButton(
            self._t("Automatisch optimieren", "Auto-optimise"),
            QtWidgets.QDialogButtonBox.ActionRole)
        self.btn_auto.setToolTip(self._t(
            "Misst das Bild und schlaegt Werte fuer ein knackiges, "
            "heutiges Ergebnis vor.\n\n"
            "Gesetzt werden nur die Regler, nichts wird gespeichert - das "
            "Ergebnis steht sofort in der Vorschau und laesst sich von "
            "Hand nachziehen.\n\n"
            "Der Weissabgleich bleibt unberuehrt: ob eine warme "
            "Farbstimmung gewollt ist, kann kein Programm aus einem Bild "
            "ablesen.",
            "Measures the image and proposes values for a crisp, modern "
            "result.\n\nOnly the sliders are set, nothing is saved - the "
            "result appears in the preview straight away and can be "
            "adjusted by hand.\n\nWhite balance is left alone: no "
            "program can tell from one image whether a warm mood is "
            "intended."))
        self.btn_auto.clicked.connect(self._automatisch)
        self.btn_auto.setEnabled(False)
        self.btn_ursprung = knoepfe.addButton(
            self._t("Zurücksetzen", "Reset"),
            QtWidgets.QDialogButtonBox.ResetRole)
        self.btn_ursprung.setToolTip(self._t(
            "Stellt alle Regler auf den Stand beim Oeffnen zurueck - also "
            "auf das, was im Profil steht.\n\nNicht zu verwechseln mit "
            "\u201eneutral\u201c: das setzt einen einzelnen Regler auf "
            "den Wert, bei dem die Engine nichts tut.",
            "Puts every slider back to how it was when the dialog opened, "
            "i.e. to what the profile holds.\n\nNot the same as "
            "\u201cneutral\u201d, which sets a single slider to the value "
            "at which the engine does nothing."))
        self.btn_ursprung.clicked.connect(self._auf_ursprung)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        aussen.addWidget(knoepfe)

    def _t(self, de, en):
        return de if self._de else en

    def _auf_ursprung(self):
        """
        Alle Regler auf den Stand beim Oeffnen.

        Die Signale werden dabei angehalten und die Vorschau erst danach
        einmal neu gerechnet - sonst zeichnet sie bei acht Reglern acht
        Mal hintereinander.
        """
        for kid, (chk, sl, _lbl, _d) in self.regler.items():
            wert, haken = self._ursprung.get(kid, (sl.value(), chk.isChecked()))
            for w in (chk, sl):
                w.blockSignals(True)
            chk.setChecked(haken)
            sl.setValue(wert)
            for w in (chk, sl):
                w.blockSignals(False)
            sl.setEnabled(haken)
        if self.cmb_hl is not None:
            haken, idx = getattr(self, '_hl_ursprung', (False, 0))
            for w in (self.chk_hl, self.cmb_hl):
                w.blockSignals(True)
            self.chk_hl.setChecked(haken)
            self.cmb_hl.setCurrentIndex(idx)
            for w in (self.chk_hl, self.cmb_hl):
                w.blockSignals(False)
            self.cmb_hl.setEnabled(haken)
        # Beschriftungen und Knopfzustaende von Hand nachziehen, weil die
        # Signale eben abgeschaltet waren.
        for kid, (chk, sl, lbl, d) in self.regler.items():
            lbl.setText(f"{sl.value() / float(10 ** d['dezimal']):.{d['dezimal']}f}"
                        f"{d['einheit']}")
        self._vorschau_zeichnen()

    def _vorschau_geladen(self, ergebnis):
        """Das Bild ist da - ab jetzt kann gezeichnet werden."""
        if not isinstance(ergebnis, tuple):
            ergebnis = (ergebnis, 100, 1.0)
        bild, iso = ergebnis[0], ergebnis[1]
        self._pegel = float(ergebnis[2]) if len(ergebnis) > 2 else 1.0
        self._basis_voll = bild
        self._iso = iso
        if bild is None:
            self.lbl_vorschau.setText(self._t(
                "Dieses Bild konnte nicht gelesen werden.",
                "This image could not be read."))
            self.lbl_vorschau.setMinimumHeight(0)
            self.lbl_histogramm.setVisible(False)
            return
        self.btn_auto.setEnabled(True)
        self._vorschau_neu_skalieren()
        self._hl_pruefen()

    def _vorschau_neu_skalieren(self):
        """
        Bringt das geladene Bild auf die aktuelle Anzeigebreite.

        Gerechnet wird immer nur auf der Groesse, die auch zu sehen ist.
        Bei 1100 Pixeln dauerte ein Durchgang viermal so lang wie bei 520,
        ohne dass man mehr erkennt als das Fenster hergibt.
        """
        if self._basis_voll is None:
            return
        voll_h, voll_b = self._basis_voll.shape[:2]
        platz_b = max(320, self.lbl_vorschau.width() - 8)
        platz_h = max(200, self.lbl_vorschau.height() - 8)
        breite = int(min(voll_b, platz_b, platz_h * voll_b / float(voll_h)))
        breite = max(320, breite)
        if breite == self._anzeige_breite and self._basis is not None:
            return
        self._anzeige_breite = breite
        self._echt_lin = None
        if breite >= voll_b:
            self._basis = self._basis_voll
        else:
            hoehe = max(1, int(round(voll_h * breite / float(voll_b))))
            self._basis = cv2.resize(self._basis_voll, (breite, hoehe),
                                     interpolation=cv2.INTER_AREA)
        self._vorschau_zeichnen()

    def resizeEvent(self, event):
        """Fenster gezogen - Vorschau gebuendelt nachziehen."""
        super().resizeEvent(event)
        if self._basis_voll is not None:
            self._groesse_timer.start()

    def _uebernehmen(self, idx):
        """
        Holt die Schnelleinstellungen aus dem Profil eines anderen
        Keyframes.

        Uebernommen wird nur, was dieses Profil auch kennt, und nur Werte,
        die dort vom Neutralwert abweichen - sonst wuerde ein unbearbeitetes
        Keyframe die eigene Arbeit mit lauter Nullen ueberschreiben.
        """
        if idx <= 0 or idx > len(self._andere):
            return
        name, pfad = self._andere[idx - 1]
        try:
            fremd = read_arp_dict(pfad)
        except OSError:
            fremd = {}
        if not fremd:
            self.lbl_vorschau_hinweis.setText(self._t(
                f"{name}: kein lesbares Profil.",
                f"{name}: no readable profile."))
            return
        quelle = quick_read(fremd)
        gesetzt = []
        for kid, (chk, sl, lbl, d) in self.regler.items():
            if kid not in quelle:
                continue
            wert = float(quelle[kid])
            toleranz = max(1e-6, 10 ** -(d['dezimal'] + 1))
            if abs(wert - float(d['neutral'])) <= toleranz:
                continue
            faktor = 10 ** d['dezimal']
            wert = max(d['ui_min'], min(d['ui_max'], wert))
            for w in (chk, sl):
                w.blockSignals(True)
            sl.setValue(int(round(wert * faktor)))
            chk.setChecked(True)
            for w in (chk, sl):
                w.blockSignals(False)
            sl.setEnabled(True)
            lbl.setText(f"{sl.value() / float(faktor):.{d['dezimal']}f}"
                        f"{d['einheit']}")
            gesetzt.append(self._t(d['de'], d['en']))
        if gesetzt:
            self.lbl_vorschau_hinweis.setText(
                self._t(f"Von {name} übernommen: ", f"Copied from {name}: ")
                + ", ".join(gesetzt))
        else:
            self.lbl_vorschau_hinweis.setText(self._t(
                f"{name} hat keine abweichenden Werte.",
                f"{name} holds no values that differ."))
        self._vorschau_zeichnen()

    def _automatisch(self):
        """Misst das Bild und setzt die vorgeschlagenen Werte."""
        if self._basis is None:
            return
        vorschlag, begruendung = auto_optimieren(
            self._basis, iso=self._iso, erlaubt=set(self.regler.keys()),
            lang=self.lang)
        if not vorschlag:
            self.lbl_vorschau_hinweis.setText(self._t(
                "Nichts zu verbessern gefunden.", "Nothing found to improve."))
            return
        for kid, (chk, sl, lbl, d) in self.regler.items():
            if kid not in vorschlag:
                continue
            faktor = 10 ** d['dezimal']
            wert = max(d['ui_min'], min(d['ui_max'], float(vorschlag[kid])))
            for w in (chk, sl):
                w.blockSignals(True)
            sl.setValue(int(round(wert * faktor)))
            chk.setChecked(True)
            for w in (chk, sl):
                w.blockSignals(False)
            for w in (sl,):
                w.setEnabled(True)
            lbl.setText(f"{sl.value() / float(faktor):.{d['dezimal']}f}"
                        f"{d['einheit']}")
        if vorschlag.get('_hl') and self.cmb_hl is not None:
            self.chk_hl.blockSignals(True)
            self.chk_hl.setChecked(True)
            self.chk_hl.blockSignals(False)
            self.cmb_hl.setEnabled(True)
            idx = self.cmb_hl.findData(hl_empfohlen())
            if idx >= 0:
                self.cmb_hl.blockSignals(True)
                self.cmb_hl.setCurrentIndex(idx)
                self.cmb_hl.blockSignals(False)
        self._letzte_begruendung = begruendung
        self.lbl_vorschau_hinweis.setText(
            self._t("Vorschlag gesetzt: ", "Proposal applied: ")
            + "; ".join(b.split(":")[0] for b in begruendung[:4]))
        self.lbl_vorschau_hinweis.setToolTip("\n".join(begruendung))
        self._vorschau_zeichnen()

    def begruendung(self):
        """Die Begruendungen des letzten Vorschlags, fuer das Protokoll."""
        return list(getattr(self, '_letzte_begruendung', []))

    def _vorschau_anfordern(self, *_):
        """Neuzeichnen anstossen, aber gebuendelt."""
        if self._basis is not None:
            self._v_timer.start()

    def _vorschau_zeichnen(self):
        """
        Bringt den aktuellen Stand der Regler ins Bild.

        Mit echter Vorschau: liegt fuer genau diese Einstellungen schon ein
        Bild der Engine vor, wird es gezeigt. Sonst steht eine Naeherung
        da, und die Engine wird losgeschickt, sobald die Regler ruhen.
        """
        if self._basis is None:
            return
        if self._echt_an():
            profil = self._profil_jetzt()
            kennung = profil_kennung(profil)
            rgb = self._echt_merker.get(kennung)
            if rgb is not None:
                self._echt_zeigen(rgb, profil)
                return
            try:
                rgb = self._naeherung(profil)
            except Exception:
                rgb = None
            if rgb is not None:
                self._bild_setzen(rgb, echt=False)
            if kennung in self._echt_fehlschlag:
                return
            self.lbl_echt.setText(self._t("Näherung …", "approximation …"))
            self._echt_timer.start()
            return
        self.lbl_echt.setText("")
        werte = {} if self.chk_vorher.isChecked() else self.werte()
        try:
            rgb = vorschau_rechnen(self._basis, self._basis_temp,
                                   self._basis_gruen, werte)
        except Exception:
            return
        self._bild_setzen(rgb, echt=False)

    def _bild_setzen(self, rgb, echt):
        """Zeigt ein fertiges Bild samt Histogramm an."""
        rgb = np.ascontiguousarray(rgb)
        h, w, ch = rgb.shape
        bild = QtGui.QImage(rgb.data, w, h, ch * w,
                            QtGui.QImage.Format_RGB888).copy()
        self.lbl_vorschau.setPixmap(QtGui.QPixmap.fromImage(bild))
        self._gezeigt_echt = bool(echt)
        # Das Histogramm zeigt das, was oben zu sehen ist - also mit allen
        # gesetzten Werten. Nur so sieht man beim Schieben, wann die
        # Lichter anlaufen.
        hb = max(200, self.lbl_histogramm.width() - 4)
        hist = np.ascontiguousarray(histogramm_bild(rgb, hb, HISTOGRAMM_HOEHE))
        hh, hw, hc = hist.shape
        self.lbl_histogramm.setPixmap(QtGui.QPixmap.fromImage(
            QtGui.QImage(hist.data, hw, hh, hc * hw,
                         QtGui.QImage.Format_RGB888).copy()))
        if echt:
            self._hl_pruefen(rgb)

    # ---- Echte Vorschau ----------------------------------------------
    def _echt_an(self):
        return (self._cli is not None and not self._zu
                and self.chk_echt.isChecked())

    def _profil_jetzt(self):
        """Das Profil, das ein Klick auf OK jetzt schreiben wuerde."""
        if self.chk_vorher.isChecked():
            return schnell_profil(self._profil0, {}, None)[0]
        hl = self.hl_wert() if self.cmb_hl is not None else None
        return schnell_profil(self._profil0, self.werte(), hl)[0]

    def _zustand_von(self, profil):
        """Die Einstellungen eines Profils, soweit die Naeherung sie kennt."""
        z = quick_read(profil)
        z['wb_eigen'] = (profil.get('White Balance', {}).get('Setting')
                         == eng('wb_custom'))
        z['hl'] = hl_lesen(profil)
        return z

    def _einpassen(self, rgb):
        """Bringt ein Bild der Engine auf die Anzeigebreite."""
        h, w = rgb.shape[:2]
        breite = min(w, max(320, self._anzeige_breite or w))
        if breite >= w:
            return rgb
        hoehe = max(1, int(round(h * breite / float(w))))
        return cv2.resize(rgb, (breite, hoehe), interpolation=cv2.INTER_AREA)

    def _naeherung(self, profil):
        """
        Das Bild fuer die Zeit, in der die Engine noch rechnet.

        Gibt es schon ein Bild der Engine, wird nur der UNTERSCHIED zu
        dessen Einstellungen daraufgerechnet. Das liegt viel naeher am
        Ergebnis als eine Rechnung von Grund auf, weil Tonkurve, Farben
        und Belichtung der Engine schon im Bild stecken.
        """
        werte = {} if self.chk_vorher.isChecked() else self.werte()
        if self._echt_bild is None or self._echt_zustand is None:
            return vorschau_rechnen(self._basis, self._basis_temp,
                                    self._basis_gruen, werte)
        alt, neu = self._echt_zustand, self._zustand_von(profil)
        klein = self._einpassen(self._echt_bild)
        if alt['wb_eigen'] != neu['wb_eigen']:
            # Von "Kamera" auf einen eigenen Weissabgleich oder zurueck:
            # welche Temperatur die Kamera meinte, weiss nur die Engine.
            return klein
        if self._echt_lin is None:
            self._echt_lin = np.asarray(srgb_to_linear(klein),
                                        dtype=np.float32)
        delta = {}
        for k in ('brightness', 'contrast', 'saturation'):
            d = float(neu.get(k, 0.0)) - float(alt.get(k, 0.0))
            if d:
                delta[k] = d
        if neu['wb_eigen']:
            delta['wb_temp'] = neu.get('wb_temp', 5500.0)
            delta['wb_green'] = neu.get('wb_green', 1.0)
        if neu['hl'] != "Off" and alt['hl'] == "Off":
            delta['_hl_staerke'] = 1.0
        return vorschau_rechnen(self._echt_lin, alt.get('wb_temp', 5500.0),
                                alt.get('wb_green', 1.0), delta)

    def _echt_zeigen(self, rgb, profil):
        """Ein Bild der Engine ist da und gehoert zum jetzigen Stand."""
        self._echt_bild = rgb
        self._echt_zustand = self._zustand_von(profil)
        self._echt_lin = None
        self._bild_setzen(rgb, echt=True)
        self.lbl_echt.setText(self._t(
            f"\u2713 von {eng('label')} entwickelt",
            f"\u2713 developed by {eng('label')}"))
        self.lbl_echt.setToolTip("")

    def _echt_starten(self):
        """Die Regler ruhen - die Engine entwickelt den jetzigen Stand."""
        if not self._echt_an() or self._basis is None:
            return
        profil = self._profil_jetzt()
        kennung = profil_kennung(profil)
        if kennung in self._echt_merker:
            self._echt_zeigen(self._echt_merker[kennung], profil)
            return
        if kennung in self._echt_fehlschlag:
            return
        if self._echt_faden is not None:
            if self._echt_faden.kennung == kennung:
                return
            self._echt_faden.abbrechen()
        faden = EngineVorschau(self._cli, self.bild_pfad, profil, kennung,
                               kante=ECHT_KANTE)
        self._echt_faden = faden
        self._echt_alle.append(faden)
        faden.fertig.connect(self._echt_fertig)
        self.lbl_echt.setText(self._t(
            f"{eng('label')} entwickelt …", f"{eng('label')} is developing …"))
        faden.start()

    def _echt_fertig(self, erg):
        """Die Engine meldet sich zurueck."""
        if self._zu:
            return
        aktuell = erg.get('faden') is self._echt_faden
        if aktuell:
            self._echt_faden = None
        if erg.get('abgebrochen'):
            return
        kennung = erg.get('kennung')
        rgb = erg.get('rgb')
        if rgb is None:
            self._echt_fehlschlag.add(kennung)
            if aktuell:
                self.lbl_echt.setText(self._t(
                    "\u26a0 echte Vorschau nicht möglich - Näherung",
                    "\u26a0 true preview failed - approximation"))
                fehler = erg.get('fehler', "")
                if self.lang == 'en':
                    fehler = {"Zeitueberschreitung": "Timeout",
                              "kein Bild erhalten": "no image received"}.get(fehler, fehler)
                self.lbl_echt.setToolTip(fehler)
            return
        while len(self._echt_merker) >= ECHT_MERKER_MAX:
            self._echt_merker.pop(next(iter(self._echt_merker)))
        self._echt_merker[kennung] = rgb
        profil = self._profil_jetzt()
        if profil_kennung(profil) == kennung and self._echt_an():
            self._echt_zeigen(rgb, profil)
            self.lbl_echt.setToolTip(self._t(
                f"Entwickelt in {erg.get('dauer', 0.0):.1f} s.",
                f"Developed in {erg.get('dauer', 0.0):.1f} s."))

    def _echt_beenden(self):
        """Beim Schliessen: nichts im Hintergrund weiterlaufen lassen."""
        self._zu = True
        for t in (self._echt_timer, self._v_timer):
            t.stop()
        for faden in self._echt_alle:
            faden.abbrechen()
        for faden in self._echt_alle:
            faden.wait(5000)

    def done(self, ergebnis):
        self._echt_beenden()
        super().done(ergebnis)

    def closeEvent(self, event):
        """Den Ladethread nicht im Hintergrund weiterlaufen lassen."""
        if self._lader is not None and self._lader.isRunning():
            self._lader.wait(3000)
        super().closeEvent(event)

    def werte(self):
        """Nur die angekreuzten Regler, als {id: Zahl}."""
        out = {}
        for kid, (chk, sl, _lbl, d) in self.regler.items():
            if chk.isChecked():
                out[kid] = sl.value() / float(10 ** d['dezimal'])
        if self.hl_wert() != "Off":
            # Die Vorschau kennt nur eine Staerke, nicht das Verfahren -
            # sie naehert alle Verfahren gleich an.
            out['_hl_staerke'] = 1.0
        return out

    def hl_wert(self):
        """Gewaehltes Verfahren der Lichter-Rekonstruktion, sonst 'Off'."""
        if self.cmb_hl is None or not self.chk_hl.isChecked():
            return "Off"
        return self.cmb_hl.currentData() or "Off"

    def _hl_pruefen(self, rgb_echt=None):
        """
        Warnt, wenn die hellsten Stellen farbig statt weiss sind.

        Mit einem Bild der Engine wird an diesem gemessen - dann zaehlt,
        was wirklich herauskommt. Sonst an der Naeherung, und die nur,
        wenn die Lichter im RAW ueberhaupt am Anschlag liegen.
        """
        if self.cmb_hl is None:
            return
        if rgb_echt is not None:
            anteil, am_bild, richtung = lichter_farbstich(rgb_echt, linear=False)
        elif self._basis is None or self._gezeigt_echt:
            return
        elif self._pegel < HL_PEGEL_SCHWELLE:
            anteil, am_bild, richtung = 0.0, 0.0, ""
        else:
            anteil, am_bild, richtung = lichter_farbstich(self._basis)
        if anteil <= 0.15 or am_bild <= 0.0002:
            self.lbl_hl_warnung.setVisible(False)
            return
        t = THEMES[self.parent().theme] if hasattr(self.parent(), 'theme') \
            else {'warn': '#a55f00'}
        self.lbl_hl_warnung.setText(self._t(
            f"⚠ {100 * anteil:.0f} % der hellsten Stellen sind "
            "rosa verfärbt",
            f"⚠ {100 * anteil:.0f} % of the brightest areas are "
            "pink-tinted"))
        self.lbl_hl_warnung.setStyleSheet(
            f"color: {t.get('warn', '#a55f00')}; font-weight: bold;")
        self.lbl_hl_warnung.setToolTip(self._t(
            f"Gemessen an {100 * am_bild:.2f} % der Bildflaeche. "
            "Das ist der ausgebrannte Sonnenball: dort steht ein Kanal am "
            "Anschlag, die anderen nicht.\n"
            "Abhilfe: \u201eLichter rekonstruieren\u201c einschalten.",
            f"Measured over {100 * am_bild:.2f} % of the frame. This is "
            "the blown sun disc: one channel is at its limit there, the "
            "others are not.\nRemedy: switch on \u201creconstruct "
            "highlights\u201d."))
        self.lbl_hl_warnung.setVisible(True)


class GalleryWorker(QtCore.QThread):
    scan_done = QtCore.pyqtSignal(int, int, list, list, int)
    gaps_found = QtCore.pyqtSignal(list, list)
    curves_ready = QtCore.pyqtSignal(dict)
    status = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int, int)
    image_ready = QtCore.pyqtSignal(int, str, QtGui.QImage, object)
    finished_loading = QtCore.pyqtSignal()

    def __init__(self, target_dir, roi_rel=None, lang='de'):
        super().__init__()
        self.target_dir = target_dir
        self.roi_rel = roi_rel
        self.lang = lang
        self._abort = False

    def run(self):
        d = self.target_dir
        jpg = sorted(glob.glob(os.path.join(d, "*.jpg")) + glob.glob(os.path.join(d, "*.JPG")))
        nef = find_raw_files(d)
        if self._abort:
            return
        files = nef if len(nef) > 0 else jpg
        if len(files) == 0:
            self.scan_done.emit(len(jpg), len(nef), jpg, nef, 0)
            return
        key_idx = [i for i, f in enumerate(files) if check_is_keyframe(sidecar(f))]
        self.scan_done.emit(len(jpg), len(nef), jpg, nef, len(key_idx))
        # EXIF fuer die Kurven und die Sonnenstands-Berechnung
        try:
            exif = scan_exif(files)
            self.curves_ready.emit({'ev': exif['ev'], 'interval': exif['interval'],
                                    'times': exif['times']})
            gaps, basis = find_sequence_gaps(exif['times'])
            if gaps or (basis[2] > 0 and basis[2] > basis[0] * 1.5):
                self.gaps_found.emit(gaps, basis)
        except Exception:
            pass
        if self._abort:
            return
        workers = max(1, multiprocessing.cpu_count() - 1)
        tasks = [(f, self.roi_rel) for f in files]
        total = len(tasks)
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            results = executor.map(process_single_thumb, tasks)
            for i, (f, combined_img, daten) in enumerate(results):
                if self._abort:
                    break
                if combined_img is not None and daten is not None:
                    combined_img = np.ascontiguousarray(combined_img)
                    h, w, ch = combined_img.shape
                    bpl = ch * w
                    qimg = QtGui.QImage(combined_img.data, w, h, bpl, QtGui.QImage.Format_RGB888).copy()
                    name = os.path.basename(f)
                    self.image_ready.emit(i, name, qimg, daten)
                done = i + 1
                kopf = ("Reading images" if self.lang == 'en'
                        else "Lese Bilder ein")
                self.status.emit(fortschritt_text(kopf, done, total,
                                                  start_time, lang=self.lang))
                self.progress.emit(done, total)
        self.finished_loading.emit()


# ==========================================================================
#  WORKER-THREAD  (Render-Prozess)
# ==========================================================================
class Worker(QtCore.QThread):
    log = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int, int)
    finished_ok = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)
    output_ready = QtCore.pyqtSignal(str)
    # Anzahl betroffener Bilder, Gesamtzahl, [(Index, Anteil), ...]
    clip_report = QtCore.pyqtSignal(int, int, list)

    def __init__(self, params):
        super().__init__()
        self.p = params
        self._abort = False

    def cancel(self):
        self._abort = True

    def _t(self, de, en):
        """Text in der Sprache der Oberflaeche - fuer Fehlermeldungen, die
        als Dialog beim Benutzer ankommen."""
        return en if self.p.get('lang') == 'en' else de

    def _check_abort(self):
        if self._abort:
            raise RuntimeError(self._t("Vom Benutzer abgebrochen.", "Cancelled by user."))

    def _apply_camera_move(self, img, step, total_steps, width, calc_height):
        orig_h, orig_w = img.shape[:2]
        if self.p.get('cam_keyframes'):
            kf = self.p['cam_keyframes']
            t = kamera_verlauf(step / max(1, total_steps - 1))
            sx, sy, sw, sh = kf['start']
            ex, ey, ew, eh = kf['end']
            return ausschnitt_subpixel(
                img, (sx + (ex - sx) * t) * orig_w, (sy + (ey - sy) * t) * orig_h,
                (sw + (ew - sw) * t) * orig_w, (sh + (eh - sh) * t) * orig_h,
                width, calc_height)
        target_ratio = width / calc_height
        img_ratio = orig_w / orig_h
        if img_ratio > target_ratio:
            new_h = orig_h
            new_w = int(orig_h * target_ratio)
        else:
            new_w = orig_w
            new_h = int(orig_w / target_ratio)
        start_x = (orig_w - new_w) // 2
        start_y = (orig_h - new_h) // 2
        img_crop = img[start_y:start_y + new_h, start_x:start_x + new_w]
        return cv2.resize(img_crop, (width, calc_height), interpolation=cv2.INTER_AREA)

    def _fade(self, frame, step, total):
        """Blendet Anfang und Ende weich aus Schwarz auf bzw. nach Schwarz ab."""
        sec = float(self.p.get('fade_sec', 0.0))
        if sec <= 0 or total < 4:
            return frame
        try:
            fps = float(self.p['fps'])
        except (KeyError, ValueError):
            fps = 25.0
        span = max(1, int(round(sec * fps)))
        if step < span:
            f = (step + 1) / (span + 1)
        elif step >= total - span:
            f = (total - step) / (span + 1)
        else:
            return frame
        return (frame.astype(np.float32) * f + 0.5).astype(frame.dtype)

    def _start_encoder(self, ffmpeg_cmd):
        """
        Startet FFmpeg als Empfaenger der Bilddaten.

        Die Fehlerausgabe geht in eine temporaere Datei und nicht in eine
        Pipe: aus einer Pipe wird hier erst im Fehlerfall gelesen, und ein
        voller Pipe-Puffer laesst FFmpeg blockieren, waehrend Purelapse
        gleichzeitig auf das Schreiben des naechsten Bildes wartet - beide
        Prozesse stehen dann still.
        """
        self._enc_err = tempfile.TemporaryFile()
        return subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE,
                                stderr=self._enc_err)

    def _encoder_error(self):
        """Die gesammelten FFmpeg-Meldungen als Text."""
        try:
            self._enc_err.flush()
            self._enc_err.seek(0)
            return self._enc_err.read().decode('utf-8', errors='ignore').strip()
        except (OSError, ValueError, AttributeError):
            return ""

    def _finish_encoder(self, proc):
        """Schliesst die Eingabe, wartet und meldet einen Fehlschlag."""
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass
        proc.wait()
        if proc.returncode not in (0, None):
            raise RuntimeError(self._t(
                "Der Video-Encoder (FFmpeg) endete mit Fehlercode "
                f"{proc.returncode}.\nUrsache: {self._encoder_error()[:800]}",
                "The video encoder (FFmpeg) exited with code "
                f"{proc.returncode}.\nReason: {self._encoder_error()[:800]}"))

    def _build_ffmpeg_cmd(self, width, calc_height, out_video, tief=False):
        """Baut den FFmpeg-Aufruf aus der Codec-Tabelle (siehe VIDEO_CODECS)."""
        fps = str(self.p['fps'])
        crf_vals = ["16", "20", "23", "28"]
        crf = crf_vals[int(self.p['qual_idx'])]
        c = codec_def(self.p.get('codec_idx', 0))
        cmd = [FFMPEG_BIN, "-y", "-loglevel", "error"]
        cmd += codec_pre_args(c)
        cmd += ["-f", "rawvideo", "-vcodec", "rawvideo",
                "-s", f"{width}x{calc_height}", "-pix_fmt", "bgr48le" if tief else "bgr24",
                "-r", fps, "-i", "-"]
        cmd += ["-vf", codec_filter(c)]
        cmd += ["-c:v", c['enc']] + c['args'](crf)
        if c['pix']:
            cmd += ["-pix_fmt", c['pix']]
        cmd += FARBRAUM_ARGS
        cmd.append(out_video)
        return cmd

    def _get_output_video_path(self):
        p = self.p
        abs_target_dir = p['target_dir']
        parent_dir_name = os.path.basename(abs_target_dir)
        out_dir_mode = p['out_dir_mode']
        custom_dir = p.get('custom_out_dir', '')
        if out_dir_mode == 0:
            out_base = pl_ordner(abs_target_dir, anlegen=True)
        elif out_dir_mode == 1:
            out_base = os.path.dirname(abs_target_dir)
        elif out_dir_mode == 2:
            out_base = SCRIPT_DIR
        else:
            out_base = custom_dir if custom_dir else abs_target_dir
        base_filename = (f"{parent_dir_name}_Purelapse_{p['res_name']}_{p['fps']}fps"
                         + p.get('name_suffix', ''))
        # Die Endung bestimmt der Codec: ProRes liegt in .mov, alles
        # andere in .mp4. Mit .mp4 verweigert FFmpeg ProRes den Dienst.
        ext = codec_def(p.get('codec_idx', 0))['ext']
        self.output_ready.emit(out_base)
        out_video_path = os.path.join(out_base, base_filename + ext)
        if p['versioning']:
            counter = 1
            out_video_path = os.path.join(out_base, f"{base_filename}_v{counter}{ext}")
            while os.path.exists(out_video_path):
                counter += 1
                out_video_path = os.path.join(out_base, f"{base_filename}_v{counter}{ext}")
        return out_video_path

    def _video_bauen(self, eintraege, laden, exif_von, ffmpeg_proc, stab_diffs,
                     width, calc_height, speichern=None, entrauschen=False):
        """
        Die Bildstrecke vom geladenen Einzelbild bis zum Encoder - eine fuer
        den JPG-Ablauf und fuer RAW Pass 2 (vorher zweimal fast gleich).

        eintraege   Dateien in Abspielreihenfolge
        laden(f)    -> BGR-Bild (uint8) oder None; laeuft in Hilfsthreads
        exif_von(f) -> Datei, aus der Belichtungszeit und Telemetrie stammen
        speichern(bild, f)  legt das entflackerte Vollbild ab (JPG-Ablauf)

        Laden, Ablegen, Stabilisieren und Ausschnitt laufen in mehreren
        Threads voraus (OpenCV gibt dabei Pythons Sperre frei); was die
        Reihenfolge braucht - Astro-Clean, Bewegungsunschaerfe, Text,
        Blende, Encoder -, bleibt im eigenen Thread.
        """
        p = self.p
        mach_video = bool(p['make_video']) and ffmpeg_proc is not None
        astro = bool(p.get('astro_clean', False))
        max_blur, min_blur = max(1, int(p['max_blur'])), max(1, int(p['min_blur']))
        blur = deque(maxlen=max_blur)
        total = len(eintraege)
        threads = max(1, min(VIDEO_THREADS_MAX, int(p.get('cores', 1) or 1)))
        fenster = threads + 1
        start_time = time.time()
        reverse = bool(p.get('reverse_play'))

        def geometrie(vollbild, idx, pfad):
            if speichern is not None:
                speichern(vollbild, pfad)
            exif = exif_gemerkt(exif_von(pfad))
            if not mach_video:
                return None, exif
            img = vollbild
            if stab_diffs is not None and idx < len(stab_diffs):
                idx_stab = (total - 1 - idx) if reverse else idx
                dx, dy, da = stab_diffs[idx_stab]
                m = np.zeros((2, 3), np.float32)
                scale_stab = 1.03
                m[0, 0] = np.cos(da) * scale_stab
                m[0, 1] = -np.sin(da) * scale_stab
                m[1, 0] = np.sin(da) * scale_stab
                m[1, 1] = np.cos(da) * scale_stab
                h, w = img.shape[:2]
                m[0, 2] = dx + (1.0 - scale_stab) * w / 2.0
                m[1, 2] = dy + (1.0 - scale_stab) * h / 2.0
                img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_REPLICATE)
            return self._apply_camera_move(img, idx, total, width, calc_height), exif

        fertig = [0]

        def ausgeben(klein, exif, idx, pfad):
            if mach_video:
                blur.append(klein)
                ss = exif['shutter']
                curr_blur = max_blur if ss < 1.0 else (
                    min_blur if ss >= 3.0
                    else int(round(max_blur - ((ss - 1.0) / 2.0) * (max_blur - min_blur))))
                curr_blur = max(min_blur, min(max_blur, curr_blur))
                frames = list(blur)[-curr_blur:]
                hoechst = bild_hoechstwert(frames[0])
                if len(frames) == 1:
                    # Kopie: Text und Blende duerfen nicht in das Bild im
                    # Puffer geraten - es geht noch in die naechsten
                    # gemittelten Bilder ein (vorher: Geisterschrift).
                    final = frames[0].copy()
                else:
                    summe = np.zeros(frames[0].shape, np.float32)
                    for fr in frames:
                        summe += fr
                    final = np.clip(summe / len(frames) + 0.5, 0, hoechst).astype(frames[0].dtype)
                if entrauschen and p['denoise'] and exif['iso'] >= 800 and final.dtype == np.uint8:
                    d = min(15, max(3, int((exif['iso'] - 400) / 250)))
                    final = cv2.bilateralFilter(final, d, d * 2, d / 2)
                if p['telemetry']:
                    zeit = exif.get('time', '')[11:19]
                    text = (f"{zeit} | " if zeit else "") + (
                        f"ISO {exif['iso']} | f/{exif['aperture']} | "
                        f"{format_shutter(exif['shutter'])}")
                    telemetrie_zeichnen(final, text, calc_height, hoechst)
                try:
                    final = self._fade(final, idx, total)
                    ffmpeg_proc.stdin.write(np.ascontiguousarray(final).tobytes())
                except BrokenPipeError:
                    err_out = self._encoder_error()
                    raise RuntimeError(self._t(
                        f"Der Video-Encoder (FFmpeg) ist abgestürzt!\nUrsache: {err_out.strip()}",
                        f"The video encoder (FFmpeg) crashed!\nReason: {err_out.strip()}"))
            fertig[0] += 1
            self._fortschritt("Rendere Video", fertig[0], total, start_time,
                              zusatz=os.path.basename(pfad))

        pool = concurrent.futures.ThreadPoolExecutor(max_workers=threads)
        try:
            lade = deque()
            geo = deque()
            folge = iter(enumerate(eintraege))
            puffer = []          # Astro-Clean: die letzten geladenen Bilder

            def nachladen():
                while len(lade) < fenster:
                    try:
                        idx, f = next(folge)
                    except StopIteration:
                        return
                    lade.append((idx, f, pool.submit(laden, f)))

            def weiter(fertigbild, idx, f):
                while len(geo) >= fenster:
                    gi, gf, gfut = geo.popleft()
                    klein, exif = gfut.result()
                    ausgeben(klein, exif, gi, gf)
                geo.append((idx, f, pool.submit(geometrie, fertigbild, idx, f)))

            nachladen()
            while lade:
                self._check_abort()
                idx, f, fut = lade.popleft()
                bild = fut.result()
                nachladen()
                if bild is None:
                    continue
                if not astro:
                    weiter(bild, idx, f)
                    continue
                puffer.append((idx, f, bild))
                if len(puffer) == 1:
                    weiter(bild, idx, f)          # erstes Bild unveraendert
                elif len(puffer) == 3:
                    (_i0, _f0, b0), (i1, f1, b1), (_i2, _f2, b2) = puffer
                    weiter(self._remove_satellites(b0, b1, b2), i1, f1)
                    puffer.pop(0)
            if astro and len(puffer) >= 2:
                i_l, f_l, b_l = puffer[-1]
                weiter(b_l, i_l, f_l)             # letztes Bild unveraendert
            while geo:
                self._check_abort()
                gi, gf, fut = geo.popleft()
                klein, exif = fut.result()
                ausgeben(klein, exif, gi, gf)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
        return fertig[0]

    def _remove_satellites(self, prev_img, curr_img, next_img, threshold=30):
        # Die Schwelle gilt fuer 8 Bit; bei 16-Bit-Zwischenbildern waeren
        # 30 von 65535 Stufen schon Rauschen - jeder Bildpunkt fiele raus.
        if curr_img.dtype == np.uint16:
            threshold = threshold * 257
        diff_prev = cv2.subtract(curr_img, prev_img)
        _, mask_prev = cv2.threshold(cv2.cvtColor(diff_prev, cv2.COLOR_BGR2GRAY), threshold, 255, cv2.THRESH_BINARY)
        diff_next = cv2.subtract(curr_img, next_img)
        _, mask_next = cv2.threshold(cv2.cvtColor(diff_next, cv2.COLOR_BGR2GRAY), threshold, 255, cv2.THRESH_BINARY)
        outlier_mask = cv2.bitwise_and(mask_prev, mask_next)
        avg_bg = cv2.addWeighted(prev_img, 0.5, next_img, 0.5, 0)
        clean_img = curr_img.copy()
        np.copyto(clean_img, avg_bg, where=(outlier_mask[:, :, None] == 255))
        return clean_img

    def run(self):
        try:
            set_engine(self.p.get('engine', 'art'))
            # Auftraege aus der Warteschlange kommen ohne _set_folder hierher
            if self.p.get('target_dir'):
                verschoben, _ = alte_ablage_umraeumen(self.p['target_dir'])
                if verschoben:
                    self.log.emit(self._t(
                        f"> {len(verschoben)} Dateien aus einer aelteren Version in den Ordner "
                        f"{PL_ORDNER} verschoben.",
                        f"> Moved {len(verschoben)} files from an older version into the "
                        f"{PL_ORDNER} folder."))
            mode = self.p.get('mode', 'normal')
            if mode == 'plain':
                self._run_plain()
                return
            if mode == 'compare':
                self._run_compare()
                return
            if mode == 'preview':
                self._run_preview()
                return
            if mode == 'schnell':
                self._run_schnell()
                return
            fmt = self.p['format']
            if fmt == 'jpg':
                self._run_jpg()
            else:
                if self.p['raw_mode'] == 'pass1':
                    self._run_raw_pass1()
                else:
                    self._run_raw_pass2()
        except Exception as e:
            self.failed.emit(str(e))

    # ----------------------------------------------------------------------
    #  Rohfassung: Zeitraffer ohne jede Bildbearbeitung
    # ----------------------------------------------------------------------
    def _load_frame_plain(self, filepath, target_w):
        """Liest ein Bild so neutral wie moeglich ein."""
        if is_raw_file(filepath):
            try:
                with rawpy.imread(filepath) as raw:
                    rgb = raw.postprocess(use_camera_wb=True,
                                          half_size=(target_w <= 2560),
                                          no_auto_bright=True)
                return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            except Exception:
                return None
        return cv2.imdecode(np.fromfile(filepath, dtype=np.uint8), cv2.IMREAD_COLOR)

    def _run_preview(self):
        """Entwickelt einige ueber die Sequenz verteilte Bilder mit den aktuellen Einstellungen."""
        p = self.p
        files = p['files']
        count = min(p.get('preview_count', 5), len(files))
        picks = [int(round(i * (len(files) - 1) / max(1, count - 1))) for i in range(count)]
        picks = sorted(set(picks))
        out_dir = tempfile.mkdtemp(prefix="purelapse_preview_")
        width = p['width']
        calc_height = int(width * 9 / 16)
        results = []
        if p['format'] == 'raw':
            missing = [files[i] for i in picks if not os.path.exists(sidecar(files[i]))]
            if missing:
                raise RuntimeError(self._t(
                    f"Fuer die Vorschau fehlen die {eng('ext')}-Profile.\n\n"
                    "Bitte zuerst Pass 1 laufen lassen - die Vorschau zeigt, was die "
                    "Engine mit den dort berechneten Werten und deinen Keyframes macht.",
                    f"The preview needs the {eng('ext')} profiles.\n\n"
                    "Please run pass 1 first - the preview shows what the engine "
                    "makes of the values computed there and of your keyframes."))
            sel = [files[i] for i in picks]
            self.log.emit(self._t(f"> Vorschau: entwickle {len(sel)} Bilder mit {eng('label')}...",
                f"> Preview: developing {len(sel)} images with {eng('label')}..."))
            self._render_with_engine(sel, out_dir, "Vorschau", quality=92)
            for idx, f in zip(picks, sel):
                stem = os.path.splitext(os.path.basename(f))[0]
                for ext in (".jpg", ".JPG"):
                    q = os.path.join(out_dir, stem + ext)
                    if os.path.exists(q):
                        results.append((idx, q))
                        break
        else:
            lum = np.asarray(p.get('luma_curve') or [], dtype=np.float64)
            gains = None
            if lum.size == len(files):
                lum = np.maximum(lum, 1e-3)
                tgt = two_pass_smooth(lum, p['scene_int'], p['smooth_val']) * (2 ** p['ev_val'])
                gains = np.clip(tgt / lum, 0.125, 8.0)
            self.log.emit(self._t(f"> Vorschau: bereite {len(picks)} Bilder auf...",
                f"> Preview: preparing {len(picks)} images..."))
            for k, idx in enumerate(picks):
                self._check_abort()
                img = load_preview_image(files[idx])
                if img is None:
                    continue
                if gains is not None:
                    img = np.clip(img.astype(np.float32) * float(gains[idx]),
                                  0, 255).astype(np.uint8)
                q = os.path.join(out_dir, f"prev_{idx:05d}.jpg")
                cv2.imwrite(q, img)
                results.append((idx, q))
                self.progress.emit(k + 1, len(picks))
        if not results:
            raise RuntimeError(self._t("Es konnte kein Vorschaubild erzeugt werden.",
                                       "No preview image could be created."))
        final = []
        total = len(files)
        for idx, q in results:
            img = cv2.imread(q, cv2.IMREAD_COLOR)
            if img is None:
                continue
            img = self._apply_camera_move(img, idx, total, width, calc_height)
            img = self._fade(img, idx, total)
            out = os.path.join(out_dir, f"final_{idx:05d}.jpg")
            cv2.imwrite(out, img, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            final.append(f"{idx}|{out}")
        self.finished_ok.emit("PREVIEW::" + ";;".join(final))

    def _run_plain(self):
        """Erzeugt den Zeitraffer ohne Deflicker, ohne Keyframes, ohne Effekte."""
        p = self.p
        files = p['files']
        width = p['width']
        calc_height = int(width * 9 / 16)
        self.log.emit(self._t(f"> Rohfassung ohne Bearbeitung ({len(files)} Bilder).",
                f"> Untouched version without processing ({len(files)} images)."))
        self.log.emit(self._t("> Deflicker, Keyframes, Motion Blur, Denoise und "
                      "Stabilisierung sind ausgeschaltet.",
                "> Deflicker, keyframes, motion blur, denoise and stabilisation are switched off."))
        out_video = self._get_output_video_path()
        ffmpeg_cmd = self._build_ffmpeg_cmd(width, calc_height, out_video)
        self.log.emit(self._t("\n> STARTE FFMPEG ENCODER:",
                "\n> STARTING FFMPEG ENCODER:"))
        self.log.emit(" ".join(ffmpeg_cmd) + "\n")
        ffmpeg_proc = self._start_encoder(ffmpeg_cmd)
        total = len(files)
        start_time = time.time()
        written = 0
        for step, f in enumerate(files):
            self._check_abort()
            img = self._load_frame_plain(f, width)
            if img is None:
                continue
            orig_h, orig_w = img.shape[:2]
            target_ratio = width / calc_height
            if orig_w / orig_h > target_ratio:
                new_h, new_w = orig_h, int(orig_h * target_ratio)
            else:
                new_w, new_h = orig_w, int(orig_w / target_ratio)
            sx, sy = (orig_w - new_w) // 2, (orig_h - new_h) // 2
            frame = cv2.resize(img[sy:sy + new_h, sx:sx + new_w],
                               (width, calc_height), interpolation=cv2.INTER_AREA)
            try:
                frame = self._fade(frame, step, total)
                ffmpeg_proc.stdin.write(frame.tobytes())
                written += 1
            except BrokenPipeError:
                err = self._encoder_error()
                raise RuntimeError(self._t("Der Video-Encoder (FFmpeg) ist abgestuerzt!\n"
                                           f"Ursache: {err.strip()}",
                                           "The video encoder (FFmpeg) crashed!\n"
                                           f"Reason: {err.strip()}"))
            self._fortschritt("Rohfassung", step + 1, total, start_time,
                              zusatz=os.path.basename(f))
        self._finish_encoder(ffmpeg_proc)
        if written == 0:
            raise RuntimeError(self._t("Kein einziges Bild konnte gelesen werden.",
                                       "Not a single image could be read."))
        self.finished_ok.emit(self._t(f"Rohfassung fertig ({written} Bilder):\n{out_video}",
                                      f"Plain version done ({written} frames):\n{out_video}"))

    def _run_schnell(self):
        """
        Schnellvorschau: ein grobes Video in Minuten statt Stunden.

        Grundlage sind die eingebetteten Vorschaubilder der Kamera (bei
        JPG verkleinert gelesene Bilder). Die Helligkeit wird mit derselben
        Glaettung wie im Diagramm ausgeglichen, Bildausschnitt und
        Kamerafahrt gelten. Keine Engine, keine Keyframes, keine
        Schnelleinstellungen, keine Effekte - nur zum ersten Eindruck.
        """
        p = self.p
        files = p['files']
        width = int(min(int(p['width']), SCHNELL_BREITE_MAX))
        width -= width % 2
        calc_height = int(width * 9 / 16)
        calc_height -= calc_height % 2
        self.log.emit(self._t(f"> Schnellvorschau: {len(files)} Bilder, {width}x{calc_height}. "
                      "Nur zur Beurteilung - ohne Engine, Keyframes und Effekte.",
                f"> Quick preview: {len(files)} images, {width}x{calc_height}. For judging only - without engine, keyframes and effects."))
        start = time.time()
        threads = mess_threads(p.get('cores', 1))
        erg = parallel_messen(
            schnell_bild_laden, [(f, width, p.get('roi_rel')) for f in files],
            threads, self._check_abort,
            lambda fertig, anzahl: self._fortschritt(
                "Schnellvorschau lesen", fertig, anzahl, start))
        bilder = [(b, l) for b, l in erg if b is not None and l and l > 0]
        if len(bilder) < 3:
            raise RuntimeError(self._t("Zu wenige Bilder fuer eine Schnellvorschau lesbar.",
                                       "Too few readable images for a quick preview."))
        self._schritt_fertig("Vorschaubilder gelesen", len(bilder), start)
        luma = np.asarray([l for _b, l in bilder], dtype=np.float64)
        ziel = two_pass_smooth(luma, p['scene_int'], p['smooth_val'])
        ziel = ziel * (2 ** p['ev_val'])
        faktoren = np.clip(ziel / np.maximum(luma, 1e-6), 0.125, 8.0)
        p['name_suffix'] = '_Schnellvorschau'
        p['versioning'] = False
        out_video = os.path.splitext(self._get_output_video_path())[0] + ".mp4"
        cmd = [FFMPEG_BIN, "-y", "-loglevel", "error",
               "-f", "rawvideo", "-vcodec", "rawvideo",
               "-s", f"{width}x{calc_height}", "-pix_fmt", "bgr24",
               "-r", str(p['fps']), "-i", "-",
               "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
               "-pix_fmt", "yuv420p", out_video]
        self.log.emit(" ".join(cmd))
        proc = self._start_encoder(cmd)
        reihe = list(zip(bilder, faktoren))
        if p.get('reverse_play'):
            reihe.reverse()
        gesamt = len(reihe)
        start = time.time()
        for i, ((daten, _l), faktor) in enumerate(reihe):
            self._check_abort()
            img = cv2.imdecode(np.frombuffer(daten, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            img = cv2.LUT(img, helligkeit_lut(faktor))
            frame = self._apply_camera_move(img, i, gesamt, width, calc_height)
            try:
                proc.stdin.write(np.ascontiguousarray(frame).tobytes())
            except BrokenPipeError:
                raise RuntimeError(self._t("Der Video-Encoder (FFmpeg) ist abgestuerzt:\n",
                                           "The video encoder (FFmpeg) crashed:\n")
                                   + self._encoder_error().strip())
            self._fortschritt("Schnellvorschau Video", i + 1, gesamt, start)
        self._finish_encoder(proc)
        self.finished_ok.emit("SCHNELL::" + out_video)

    def _run_compare(self):
        """Stellt zwei fertige Videos gegenueber."""
        p = self.p
        left, right = p['video_a'], p['video_b']
        out_video = p['compare_out']
        style = p.get('compare_style', 'side')
        if style == 'split':
            fc = ("[0:v]crop=iw/2:ih:0:0[a];"
                  "[1:v]crop=iw/2:ih:iw/2:0[b];"
                  "[a][b]hstack=inputs=2[v]")
        else:
            fc = ("[0:v]scale=-2:720[a];[1:v]scale=-2:720[b];"
                  "[a][b]hstack=inputs=2[v]")
        cmd = [FFMPEG_BIN, "-y", "-loglevel", "error", "-i", left, "-i", right,
               "-filter_complex", fc, "-map", "[v]",
               "-c:v", "libx264", "-preset", "fast", "-crf", "18",
               "-pix_fmt", "yuv420p", out_video]
        self.output_ready.emit(os.path.dirname(out_video))
        self.log.emit(self._t("> Erzeuge Vergleichsvideo:",
                "> Creating comparison video:"))
        self.log.emit(" ".join(cmd) + "\n")
        self.status.emit("Vergleichsvideo wird erstellt...")
        self.progress.emit(0, 1)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(self._t("FFmpeg konnte die Videos nicht zusammenfuegen.\n",
                                       "FFmpeg could not combine the videos.\n")
                               + err.decode('utf-8', errors='ignore').strip()[:600])
        self.progress.emit(1, 1)
        self.finished_ok.emit(self._t(f"Vergleichsvideo fertig:\n{out_video}",
                                      f"Comparison video done:\n{out_video}"))

    def _run_jpg(self):
        p = self.p
        abs_target_dir = p['target_dir']
        files = p['files']
        roi = p.get('roi_rel')
        self.log.emit(self._t(f"> Starte JPG-Deflicker Workflow ({len(files)} Bilder).",
                f"> Starting JPG deflicker workflow ({len(files)} images)."))
        luma_vals, b_vals, g_vals, r_vals, valid_files = [], [], [], [], []
        start_time = time.time()
        for i, f in enumerate(files):
            self._check_abort()
            res = get_brightness_jpg(f, roi)
            if res:
                luma_vals.append(res[0])
                b_vals.append(res[1])
                g_vals.append(res[2])
                r_vals.append(res[3])
                valid_files.append(f)
            self._fortschritt("Lese Daten", i + 1, len(files), start_time,
                              zusatz=os.path.basename(f))
        if len(valid_files) < 3:
            raise RuntimeError(self._t("Zu wenige lesbare JPG-Dateien für die Analyse.",
                                       "Too few readable JPG files for the analysis."))
        a_luma = np.maximum(np.asarray(luma_vals, dtype=np.float64), 1e-3)
        t_luma = two_pass_smooth(a_luma, p['scene_int'], p['smooth_val'])
        t_luma = t_luma * (2 ** p['ev_val'])

        def _channel_gain(values):
            a_c = np.maximum(np.asarray(values, dtype=np.float64), 1e-3)
            ratio = two_pass_smooth(a_c / a_luma, 0, p['smooth_val'])
            return np.clip((t_luma * ratio) / a_c, 0.125, 8.0)

        fac_b = _channel_gain(b_vals)
        fac_g = _channel_gain(g_vals)
        fac_r = _channel_gain(r_vals)
        hot_idx = None
        if p.get('hotpixel'):
            self.log.emit(self._t("> Suche defekte Sensorpixel ueber die gesamte Sequenz...",
                "> Searching for defective sensor pixels across the whole sequence..."))
            hot_idx = build_hotpixel_map(valid_files, self.status, self._check_abort)
            if hot_idx is None:
                self.log.emit(self._t("> Keine dauerhaft auffaelligen Pixel gefunden.",
                "> No permanently conspicuous pixels found."))
            else:
                self.log.emit(self._t(f"> {hot_idx[0].size} defekte Bildpunkte werden korrigiert.",
                f"> {hot_idx[0].size} defective pixels are corrected."))
        stab_diffs = None
        if p['make_video'] and p['stabilize']:
            self.log.emit(self._t("> Führe Optische Stabilisierung durch...",
                "> Running optical stabilisation..."))
            stab_diffs = calculate_stabilization(valid_files, self.status, self.progress, self._check_abort)
        out_dir = zwischen_ordner(abs_target_dir)
        os.makedirs(out_dir, exist_ok=True)
        ffmpeg_proc, out_video = None, None
        render_sequence = list(valid_files)
        if p['reverse_play']:
            render_sequence.reverse()
        verstaerkung = {f: (fb, fg, fr) for f, fb, fg, fr
                        in zip(valid_files, fac_b, fac_g, fac_r)}
        width = p['width']
        calc_height = int(width * 9 / 16)
        if p['make_video']:
            out_video = self._get_output_video_path()
            ffmpeg_cmd = self._build_ffmpeg_cmd(width, calc_height, out_video)
            self.log.emit(self._t("\n> STARTE FFMPEG ENCODER:",
                "\n> STARTING FFMPEG ENCODER:"))
            self.log.emit(" ".join(ffmpeg_cmd) + "\n")
            ffmpeg_proc = self._start_encoder(ffmpeg_cmd)

        def laden(f):
            roh = cv2.imdecode(np.fromfile(f, dtype=np.uint8), cv2.IMREAD_COLOR)
            if roh is None:
                return None
            fb, fg, fr = verstaerkung[f]
            gain = np.array([fb, fg, fr], dtype=np.float32)
            img = np.clip(roh.astype(np.float32) * gain + 0.5, 0, 255).astype(np.uint8)
            if hot_idx is not None:
                img = apply_hotpixel_fix(img, hot_idx)
            return img

        def speichern(bild, f):
            ziel = os.path.join(out_dir, os.path.basename(f))
            ok, daten = cv2.imencode(".jpg", bild, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if not ok:
                raise RuntimeError(self._t(f"{os.path.basename(f)} liess sich nicht kodieren.",
                                           f"{os.path.basename(f)} could not be encoded."))
            datei_atomar(ziel, daten.tobytes())

        start_time = time.time()
        anzahl = self._video_bauen(render_sequence, laden, lambda f: f, ffmpeg_proc,
                                   stab_diffs, width, calc_height, speichern=speichern,
                                   entrauschen=True)
        self._schritt_fertig("Video", anzahl, start_time)
        if p['make_video'] and ffmpeg_proc:
            self._finish_encoder(ffmpeg_proc)
            self.finished_ok.emit(self._t(f"Video fertig:\n{out_video}",
                                          f"Video done:\n{out_video}"))
        else:
            self.finished_ok.emit(self._t(f"Entflackerte JPGs liegen in:\n{out_dir}",
                                          f"Deflickered JPGs are in:\n{out_dir}"))

    def _check_white_balance(self, meas):
        """Warnt, wenn der Kamera-Weissabgleich innerhalb der Sequenz schwankt."""
        rg = np.array([m.get('wb_rg', 0.0) for m in meas], dtype=np.float64)
        bg = np.array([m.get('wb_bg', 0.0) for m in meas], dtype=np.float64)
        if rg.size < 5 or not np.all(rg > 0) or not np.all(bg > 0):
            return

        def zappeln(v):
            ev = np.log2(v)
            m = ev.size
            h = np.array([ev[i] - np.median(ev[max(0, i - 4):min(m, i + 5)])
                          for i in range(m)])
            return float(h.std()), float(np.log2(v.max() / v.min()))

        r_hf, r_span = zappeln(rg)
        b_hf, b_span = zappeln(bg)
        hf = max(r_hf, b_hf)
        span = max(r_span, b_span)
        if hf < 0.004 and span < 0.02:
            self.log.emit(self._t("> Weissabgleich: konstant ueber die ganze Sequenz.",
                "> White balance: constant across the whole sequence."))
            return
        self.log.emit(self._t(f"> Weissabgleich schwankt: Zappeln {hf:.3f} EV, "
                      f"Gesamtspanne {span:.2f} EV (Rot/Gruen und Blau/Gruen).",
                f"> White balance varies: jitter {hf:.3f} EV, total span {span:.2f} EV (red/green and blue/green)."))
        if hf >= 0.004:
            self.log.emit(
                self._t("> WARNUNG: Die Kamera stand offenbar auf automatischem "
                "Weissabgleich. Der Deflicker korrigiert nur die Helligkeit - "
                "das Farbflackern bleibt im Video sichtbar.",
                "> WARNING: The camera apparently used automatic white balance. The deflicker only corrects brightness - the colour flicker stays visible in the video."))
            self.log.emit(
                self._t("> Abhilfe: im RAW-Programm das erste und das letzte Bild als "
                "Keyframe markieren und beiden denselben festen Weissabgleich "
                "geben. Purelapse schreibt ihn dann in alle Bilder dazwischen.",
                "> Remedy: mark the first and the last image as keyframes in the RAW program and give both the same fixed white balance. Purelapse then writes it into all images in between."))

    def _pruefe_darktable_xmp(self, files):
        """
        Darktable: Purelapse traegt die Belichtung in die XMP-Dateien ein,
        die Darktable beim Import anlegt - es erzeugt sie nicht selbst.
        Fehlen sie, scheiterte Pass 1 bisher erst nach der ganzen Messung
        an der ersten Datei. Jetzt wird vorher geprueft und erklaert.
        """
        fehlend = []
        for f in files:
            ok, grund = dt_sidecar_bereit(sidecar(f))
            if not ok:
                fehlend.append((os.path.basename(f), grund))
        if not fehlend:
            return
        en = self.p.get('lang') == 'en'
        gruende_en = {"fehlt": "missing", "nicht lesbar": "not readable",
                      "ohne Darktable-Bearbeitungsliste": "no darktable history"}
        beispiele = "\n".join(f"  {n}: {gruende_en.get(g, g) if en else g}"
                               for n, g in fehlend[:5])
        if len(fehlend) > 5:
            beispiele += (f"\n  ... and {len(fehlend) - 5} more" if en
                          else f"\n  ... und {len(fehlend) - 5} weitere")
        if en:
            raise RuntimeError(
                f"{len(fehlend)} of {len(files)} images have no darktable "
                "sidecar (.xmp) that Purelapse could write the correction into:\n"
                f"{beispiele}\n\n"
                "With darktable, Purelapse writes into the XMP files that "
                "darktable itself creates on import.\n\n"
                "Remedy - either of these:\n"
                "A) Import the folder once in darktable (lighttable → import → "
                "add to library). In darktable's preferences → storage, "
                "\u201cwrite sidecar file for each image\u201d must be set to "
                "\u201con import\u201d. Then start pass 1 again.\n"
                "B) In Purelapse's settings choose ART or RawTherapee as the "
                "engine - they create their profiles themselves.")
        raise RuntimeError(
            f"Fuer {len(fehlend)} von {len(files)} Bildern gibt es keine "
            "Darktable-Begleitdatei (.xmp), in die Purelapse die Korrektur "
            "eintragen koennte:\n"
            f"{beispiele}\n\n"
            "Purelapse schreibt bei Darktable in die XMP-Dateien, die Darktable "
            "selbst beim Import anlegt.\n\n"
            "Abhilfe - eines von beiden:\n"
            "A) Den Ordner einmal in Darktable importieren (Leuchttisch → "
            "Importieren → Ordner hinzufuegen). In Darktable unter Einstellungen "
            "→ Speicherung muss \u201eXMP-Dateien schreiben\u201c auf "
            "\u201ebeim Import\u201c stehen. Danach Pass 1 erneut starten.\n"
            "B) In Purelapse unter Einstellungen als Engine ART oder RawTherapee "
            "waehlen - die legen ihre Profile selbst an.")

    def _run_raw_pass1(self):
        p = self.p
        abs_target_dir = p['target_dir']
        files = p['files']
        roi = p.get('roi_rel')
        luma_vals, valid_files, meas = [], [], []
        self.log.emit(self._t("> Starte RAW Pass 1 (Analyse)...",
                "> Starting RAW pass 1 (analysis)..."))
        if eng('kind') == 'darktable':
            self._pruefe_darktable_xmp(files)
        start_time = time.time()
        threads = mess_threads(p.get('cores', 1))
        if threads > 1:
            self.log.emit(self._t(f"> Vermesse {threads} Bilder gleichzeitig.",
                f"> Measuring {threads} images at once."))
        gemessen = parallel_messen(
            measure_nef, [(f, roi) for f in files], threads, self._check_abort,
            lambda fertig, gesamt: self._fortschritt(
                "Analysiere RAWs", fertig, gesamt, start_time,
                zusatz=os.path.basename(files[fertig - 1])))
        for f, m in zip(files, gemessen):
            if m is not None and m['luma'] > 0:
                luma_vals.append(m['luma'])
                valid_files.append(f)
                meas.append(m)
        self._schritt_fertig("Analyse der RAWs", len(files), start_time)
        # Ausgefressene Lichter aus den Sensordaten - belastbarer als die
        # vorlaeufige Angabe aus den Vorschaubildern beim Einlesen.
        c_anzahl, c_gesamt, c_schlimmste = lichter_auswerten(
            [m['clip'] for m in meas], CLIP_SCHWELLE_RAW)
        self.clip_report.emit(c_anzahl, c_gesamt, list(c_schlimmste))
        if len(valid_files) < 3:
            raise RuntimeError(self._t("Zu wenige lesbare RAW-Dateien für die Analyse.",
                                       "Too few readable RAW files for the analysis."))
        template, tpl_src = find_arp_template(abs_target_dir, files)
        if template is None and p.get('art_cli_path'):
            self.log.emit(self._t(f"> Kein {eng('label')}-Basisprofil vorhanden. "
                          f"Lasse {eng('label')} einmalig eines erzeugen...",
                f"> No {eng('label')} base profile available. Letting {eng('label')} create one once..."))
            self.status.emit("Erzeuge einmalig ein Basisprofil...")
            template, tpl_src = bootstrap_arp_template(p['art_cli_path'], valid_files[0])
            if template is not None:
                self.log.emit(self._t("> Basisprofil erzeugt und dauerhaft gespeichert. "
                              "Dieser Schritt entfällt künftig.",
                "> Base profile created and stored permanently. This step is not needed again."))
        if template is None:
            if self.p.get('lang') == 'en':
                raise RuntimeError(
                    f"No valid {eng('label')} base profile found.\n\n"
                    "Purelapse must not create a sidecar file from nothing: a "
                    "profile consisting only of [Exposure] is discarded by some "
                    "engines, and the deflicker correction would have no effect.\n\n"
                    "Two ways, each needed only once:\n\n"
                    f"A) Enter a valid path to {eng('bin')} in the settings. "
                    "Purelapse then has the default profile created on the next "
                    "pass 1.\n\n"
                    f"B) Open an image in {eng('label')}, choose 'save profile' "
                    "and select that file as the base profile in the settings.")
            raise RuntimeError(
                f"Kein gueltiges {eng('label')}-Basisprofil gefunden.\n\n"
                "Purelapse darf keine Sidecar-Datei aus dem Nichts erzeugen: ein Profil, "
                "das nur aus [Exposure] besteht, wird von manchen Engines verworfen und "
                "die Deflicker-Korrektur bleibt wirkungslos.\n\n"
                "Zwei Wege, beide nur ein einziges Mal nötig:\n\n"
                f"A) In den Einstellungen einen gueltigen Pfad zu {eng('bin')} eintragen. "
                "Purelapse laesst sich das Standardprofil dann beim naechsten Pass 1 "
                "selbst erzeugen.\n\n"
                f"B) In {eng('label')} ein Bild oeffnen, 'Profil speichern' waehlen und "
                "die Datei in den Einstellungen als Basisprofil auswaehlen."
            )
        self.log.emit(self._t(f"> Basisprofil: {tpl_src}",
                f"> Base profile: {tpl_src}"))
        self.log.emit(self._t("> Berechne geglättete Luma-Zielkurve und schreibe Sidecar-Dateien.",
                "> Computing the smoothed luma target curve and writing sidecar files."))
        a_luma = np.array(luma_vals)
        target_luma = two_pass_smooth(a_luma, p['scene_int'], p['smooth_val'])
        target_luma = target_luma * (2 ** p['ev_val'])
        mev = np.log2(np.maximum(a_luma, 1e-6))
        hf = np.array([mev[i] - np.median(mev[max(0, i - 4):min(len(mev), i + 5)])
                       for i in range(len(mev))])
        need = np.log2(np.maximum(target_luma, 1e-6)) - mev - p['ev_val']
        self.log.emit(self._t(f"> Gemessenes Flackern: {hf.std():.3f} EV | "
                      f"verlangte Korrektur: {need.std():.3f} EV "
                      f"({need.min():+.2f} bis {need.max():+.2f})",
                f"> Measured flicker: {hf.std():.3f} EV | required correction: {need.std():.3f} EV ({need.min():+.2f} to {need.max():+.2f})"))
        self._check_white_balance(meas)
        if need.std() > max(0.15, 3.0 * hf.std()):
            mild = np.log2(two_pass_smooth(a_luma, 0, 25)) - mev
            grund, grund_en = [], []
            if p['smooth_val'] >= 85:
                grund.append(f"Deflicker-Staerke {p['smooth_val']}% (Richtung Gerade)")
                grund_en.append(f"deflicker strength {p['smooth_val']}% (towards a straight line)")
            elif p['smooth_val'] >= 60:
                grund.append(f"hohe Deflicker-Staerke {p['smooth_val']}%")
                grund_en.append(f"high deflicker strength {p['smooth_val']}%")
            if p['scene_int'] in (1, 2):
                grund.append("Szenario '" + ("Sunrise" if p['scene_int'] == 1 else "Sunset")
                             + "' (erzwingt monotonen Verlauf)")
                grund_en.append("scenario '" + ("Sunrise" if p['scene_int'] == 1 else "Sunset")
                                + "' (forces a monotonic course)")
            self.log.emit(
                self._t(f"> HINWEIS: Die Korrektur ({need.std():.2f} EV) ist deutlich groesser "
                f"als das gemessene Flackern ({hf.std():.3f} EV). Der Deflicker formt "
                "damit den Lichtverlauf um, nicht nur das Flackern."
                + (" Ursache: " + " und ".join(grund) + "." if grund else "")
                + " Zum Vergleich: bei Staerke 25 und Szenario 'Constant' waeren es "
                  f"{mild.std():.2f} EV. Ist die Umformung gewollt, kann der Hinweis "
                  "ignoriert werden.",
                f"> NOTE: The correction ({need.std():.2f} EV) is much larger than the measured flicker ({hf.std():.3f} EV). The deflicker therefore reshapes the course of the light, not just the flicker." + (" Cause: " + " and ".join(grund_en) + "." if grund_en else "") + f" For comparison: with strength 25 and scenario 'Constant' it would be {mild.std():.2f} EV. If the reshaping is intended, this note can be ignored."))
        old_base = load_base_ev(abs_target_dir)
        new_base = {}
        report = []
        for i, f in enumerate(valid_files):
            self._check_abort()
            name = os.path.basename(f)
            arp_path = sidecar(f)
            ev_offset = math.log2(max(float(target_luma[i]), 1e-6) / max(luma_vals[i], 1e-6))
            delta = 0.0
            if name in old_base and check_is_keyframe(arp_path):
                try:
                    current = float(read_arp_dict(arp_path).get('Exposure', {}).get('Compensation', 0.0))
                    delta = current - float(old_base[name])
                except (TypeError, ValueError):
                    delta = 0.0
            write_arp_file(f, ev_offset + delta, template,
                           hotpixel=p.get('hotpixel', False))
            new_base[name] = round(float(ev_offset), 4)
            check = read_arp_dict(arp_path)
            try:
                written = float(check.get('Exposure', {}).get('Compensation', 'nan'))
            except ValueError:
                written = float('nan')
            report.append({
                'idx': i, 'file': name,
                'measured_luma': round(luma_vals[i], 4),
                'target_luma': round(float(target_luma[i]), 4),
                'ev_offset': round(float(ev_offset), 4),
                'delta': round(delta, 4),
                'written_comp': written,
                'arp_sections': len(check),
                'exposure_enabled': check.get('Exposure', {}).get('Enabled', ''),
                'clip_frac': round(meas[i]['clip'], 5),
                'black_frac': round(meas[i]['black'], 5),
                'wb_rg': round(meas[i].get('wb_rg', 0.0), 5),
                'wb_bg': round(meas[i].get('wb_bg', 0.0), 5),
            })
            self.status.emit(f"Schreibe Sidecar: {name}")
            self.progress.emit(i + 1, len(valid_files))
        save_base_ev(abs_target_dir, new_base)
        # Die Nachkalibrierung von Pass 2 korrigiert die Abweichung zu DIESEN
        # Basiswerten. Nach einer neuen Messung gelten die alten Korrekturen
        # nicht mehr - sie wuerden sonst in jeden weiteren Lauf eingerechnet.
        try:
            os.remove(pl_datei(abs_target_dir, CALIB_DB))
            self.log.emit(self._t("> Alte Nachkalibrierung verworfen - sie gehoerte zur vorigen Messung.",
                                  "> Old recalibration discarded - it belonged to the previous measurement."))
        except OSError:
            pass
        self._save_report("purelapse_pass1.csv", report)
        self._validate_profiles(valid_files, template, "nach Pass 1")
        clipped = sum(1 for r in report if r['clip_frac'] > 0.01)
        if clipped:
            self.log.emit(self._t(f"> HINWEIS: {clipped} von {len(report)} Bildern haben ausgefressene "
                          "Lichter. Die Messung laesst diese Stellen aus, der Deflicker "
                          "bleibt davon unberuehrt. Die Lichter selbst sind verloren - "
                          "wird die Sonne rosa, hilft 'Lichter rekonstruieren' in einem Keyframe.",
                f"> NOTE: {clipped} of {len(report)} images have blown highlights. The measurement leaves these areas out, the deflicker is not affected. The highlights themselves are lost - if the sun turns pink, 'reconstruct highlights' in a keyframe helps."))
        self.finished_ok.emit(self._t(
            "Pass 1 abgeschlossen - die Helligkeit ist vermessen, die "
            "Korrektur steht in den Profilen.\n\n"
            "Weiter mit Pass 2 (Video rendern).\n\n"
            "Wer den Bildern vorher einen Look geben will: ein Bild als "
            "Keyframe markieren und ueber \"Keyframe einstellen\" oder in "
            + eng('label') + " bearbeiten. Das ist freiwillig.",
            "Pass 1 complete - the brightness has been measured and the "
            "correction is in the profiles.\n\n"
            "Next: pass 2 (render video).\n\n"
            "To give the frames a look first: mark a frame as a keyframe "
            "and edit it with \"Edit keyframe\" or in "
            + eng('label') + ". This is optional."
        ))

    def _automatik_einfrieren(self, files):
        """
        Stellt in allen Profilen ab, was die Engine fuer jedes Bild neu
        berechnen wuerde (auto-angepasste Tonkurve, Log-Automatik).

        Solche Funktionen geben jedem Bild eine eigene Tonkurve. Die
        Belichtung kann Purelapse nachregeln, eine von Bild zu Bild andere
        Kurve nicht - das Video flackert dann trotz sauberer Messwerte.
        """
        if eng('kind') != 'ini':
            return
        zaehler = {}
        for f in files:
            self._check_abort()
            pfad = sidecar(f)
            if not os.path.exists(pfad):
                continue
            d = read_arp_dict(pfad)
            geaendert = automatik_einfrieren(d)
            if geaendert:
                write_arp_dict(pfad, d)
                for art in geaendert:
                    zaehler[art] = zaehler.get(art, 0) + 1
        if zaehler.get('tonkurve'):
            self.log.emit(
                self._t(f"> Auto-angepasste Tonkurve in {zaehler['tonkurve']} Profilen "
                f"abgeschaltet. {eng('label')} haette sonst fuer jedes Bild eine "
                "eigene Tonkurve berechnet - das flackert. Alle Bilder bekommen "
                "jetzt dieselbe feste Kurve (Standard-Filmkurve, sofern das "
                "Profil keine eigene hat).",
                f"> Auto-matched tone curve switched off in {zaehler['tonkurve']} profiles. Otherwise {eng('label')} would have computed its own tone curve for every image - that flickers. All images now get the same fixed curve (standard film curve unless the profile has its own)."))
        if zaehler.get('tonkurve_fest'):
            self.log.emit(
                self._t(f"> {zaehler['tonkurve_fest']} Profile: Tonkurve unveraendert "
                "uebernommen, aber aus dem Auto-Modus geloest - in diesem Modus "
                f"ignoriert {eng('label')} Helligkeit und Kontrast.",
                f"> {zaehler['tonkurve_fest']} profiles: tone curve kept, but released from auto mode - in that mode {eng('label')} ignores brightness and contrast."))
        if zaehler.get('log'):
            self.log.emit(
                self._t(f"> Log-Tone-Mapping: Automatik in {zaehler['log']} Profilen "
                "abgeschaltet, die eingetragenen Werte gelten jetzt fuer alle "
                "Bilder.",
                f"> Log tone mapping: automatic switched off in {zaehler['log']} profiles, the entered values now apply to all images."))

    def _prepare_keyframe_profiles(self, files):
        """Verteilt die im RAW-Programm bearbeiteten Keyframe-Profile auf alle Bilder."""
        arp_files = [sidecar(f) for f in files]
        base_map = load_base_ev(self.p['target_dir'])
        calib_map = load_calib(self.p['target_dir'])

        def _calib(idx):
            try:
                return float(calib_map.get(os.path.basename(files[idx]), 0.0))
            except (TypeError, ValueError):
                return 0.0

        def _base_ev(idx):
            value = base_map.get(os.path.basename(files[idx]))
            if value is None:
                try:
                    value = float(read_arp_dict(arp_files[idx]).get('Exposure', {}).get('Compensation', 0.0))
                except (TypeError, ValueError):
                    value = 0.0
            return float(value)

        def _kf_delta(idx):
            belichtung = read_arp_dict(arp_files[idx]).get('Exposure', {})
            if 'Compensation' not in belichtung:
                # Kein Belichtungswert im Keyframe (Darktable ohne
                # Belichtungsmodul): dann hat der Nutzer daran auch nichts
                # geaendert. 0 als Gesamtwert ergaebe sonst minus Pass 1.
                return 0.0
            try:
                total = float(belichtung.get('Compensation', 0.0))
            except (TypeError, ValueError):
                total = 0.0
            return total - _base_ev(idx) - _calib(idx)

        kf_idx = [i for i in range(len(files)) if check_is_keyframe(arp_files[i])]
        if not kf_idx:
            self.log.emit(self._t("> WARNUNG: Keine Keyframes gefunden. "
                          f"{eng('label')} entwickelt mit den unveränderten Pass-1-Profilen.",
                f"> WARNING: No keyframes found. {eng('label')} develops with the unchanged pass 1 profiles."))
            return
        if not base_map:
            self.log.emit(self._t(f"> HINWEIS: Keine Pass-1-Basiswerte gefunden ({DEFLICKER_DB}). "
                          "Für exakte Übergänge bitte Pass 1 erneut laufen lassen.",
                f"> NOTE: No pass 1 base values found ({DEFLICKER_DB}). For exact transitions please run pass 1 again."))
        self.log.emit(self._t(f"> {len(kf_idx)} Keyframes gefunden. Berechne weiche Übergänge...",
                f"> {len(kf_idx)} keyframes found. Computing smooth transitions..."))
        first, last = kf_idx[0], kf_idx[-1]
        first_arp = strip_rank(read_arp_dict(arp_files[first]))
        last_arp = strip_rank(read_arp_dict(arp_files[last]))
        d_first, d_last = _kf_delta(first), _kf_delta(last)
        if eng('kind') == 'darktable':
            self._dt_stapel_melden([strip_rank(read_arp_dict(arp_files[i])) for i in kf_idx])
            if self.p.get('hotpixel'):
                for i in kf_idx:
                    d = read_arp_dict(arp_files[i])
                    if d and 'dt:hotpixels#0' not in d:
                        set_raw_hotpixel(d, True)
                        write_arp_dict(arp_files[i], d)
                first_arp = strip_rank(read_arp_dict(arp_files[first]))
                last_arp = strip_rank(read_arp_dict(arp_files[last]))
        for i in range(0, first):
            self._check_abort()
            new_arp = {sec: dict(params) for sec, params in first_arp.items()}
            set_exposure(new_arp, _base_ev(i) + d_first + _calib(i))
            set_raw_hotpixel(new_arp, self.p.get('hotpixel', False))
            write_arp_dict(arp_files[i], new_arp)
        for a in range(len(kf_idx) - 1):
            s_i, e_i = kf_idx[a], kf_idx[a + 1]
            s_arp = strip_rank(read_arp_dict(arp_files[s_i]))
            e_arp = strip_rank(read_arp_dict(arp_files[e_i]))
            d_s, d_e = _kf_delta(s_i), _kf_delta(e_i)
            harte = nicht_ueberblendbar(s_arp, e_arp)
            if harte and e_i - s_i > 1:
                self.log.emit(
                    self._t("> ACHTUNG: Zwischen den Keyframes "
                    f"{os.path.basename(files[s_i])} und "
                    f"{os.path.basename(files[e_i])} lassen sich "
                    f"{len(harte)} Einstellungen nicht weich ueberblenden, "
                    "sie springen in der Mitte um: "
                    + ", ".join(f"[{sec}] {k}" for sec, k in harte[:4])
                    + (" ..." if len(harte) > 4 else "")
                    + ". Fuer einen weichen Verlauf diese Einstellung in "
                    "beiden Keyframes gleich waehlen.",
                f"> WARNING: Between the keyframes {os.path.basename(files[s_i])} and {os.path.basename(files[e_i])} {len(harte)} settings cannot be blended smoothly, they switch over in the middle: " + ", ".join(f"[{sec}] {k}" for sec, k in harte[:4]) + (" ..." if len(harte) > 4 else "") + ". For a smooth transition choose the same setting in both keyframes."))
            for i in range(s_i + 1, e_i):
                self._check_abort()
                ratio = (i - s_i) / (e_i - s_i)
                new_arp = interpolate_arp_dicts(s_arp, e_arp, ratio)
                set_exposure(new_arp, _base_ev(i) + d_s + (d_e - d_s) * ratio + _calib(i))
                set_raw_hotpixel(new_arp, self.p.get('hotpixel', False))
                write_arp_dict(arp_files[i], new_arp)
        for i in range(last + 1, len(files)):
            self._check_abort()
            new_arp = {sec: dict(params) for sec, params in last_arp.items()}
            set_exposure(new_arp, _base_ev(i) + d_last + _calib(i))
            set_raw_hotpixel(new_arp, self.p.get('hotpixel', False))
            write_arp_dict(arp_files[i], new_arp)
        prof = []
        for i, f in enumerate(files):
            d = read_arp_dict(arp_files[i])
            wb = d.get('White Balance', {})
            prof.append({
                'idx': i, 'file': os.path.basename(f),
                'keyframe': 1 if i in kf_idx else 0,
                'exposure': d.get('Exposure', {}).get('Compensation', ''),
                'wb_setting': wb.get('Setting', ''),
                'wb_temp': wb.get('Temperature', ''),
                'wb_green': wb.get('Green', ''),
                'wb_mult': wb.get('Multipliers', ''),
                'sections': len(d),
            })
        self._save_report("purelapse_profiles.csv", prof)
        self._validate_profiles(files, first_arp, "nach der Keyframe-Verteilung")

    def _dt_stapel_melden(self, keyframes):
        """Sagt vor dem Verteilen, was aus den Darktable-Keyframes in die
        Bilder dazwischen geht - und was davon weich ueberblendet wird."""
        alle, weich = dt_stapel_uebersicht(keyframes)
        if not alle:
            self.log.emit(self._t(
                "> Darktable: In den Keyframes ist ausser der Belichtung nichts "
                "eingestellt - es wird nur die Belichtung verteilt.",
                "> darktable: apart from exposure nothing is set in the "
                "keyframes - only exposure is distributed."))
            return
        self.log.emit(self._t(
            f"> Darktable: {len(alle)} Module aus den Keyframes gehen in alle "
            f"Bilder: {', '.join(alle)}.",
            f"> darktable: {len(alle)} modules from the keyframes go into all "
            f"frames: {', '.join(alle)}."))
        if weich:
            self.log.emit(self._t(
                "> In den Keyframes verschieden eingestellt und weich "
                f"ueberblendet: {', '.join(weich)}.",
                "> Set differently in the keyframes and blended smoothly: "
                f"{', '.join(weich)}."))

    def _diag(self):
        return bool(self.p.get('diag'))

    def _save_report(self, filename, rows):
        """Protokolldateien nur im Diagnose-Modus anlegen."""
        if self._diag():
            save_report(self.p['target_dir'], filename, rows)
            self.log.emit(self._t(f"> Diagnose: {filename} geschrieben",
                f"> Diagnostics: {filename} written"))

    def _validate_profiles(self, files, reference, label):
        """Prueft alle geschriebenen Sidecars gegen die Referenz."""
        if not reference:
            return
        issues, checked = [], 0
        for f in files:
            arp = sidecar(f)
            if not os.path.exists(arp):
                issues.append(self._t(f"{os.path.basename(f)}: Sidecar fehlt",
                                      f"{os.path.basename(f)}: sidecar missing"))
                continue
            checked += 1
            issues.extend(validate_arp(read_arp_dict(arp), reference, os.path.basename(f),
                                       lang=self.p.get('lang', 'de')))
        if self._diag():
            write_check_log(self.p['target_dir'], "purelapse_arp_check.log",
                            f"Purelapse {VERSION} - Formatpruefung der Sidecars ({label})",
                            issues, checked)
        if issues:
            self.log.emit(self._t(f"> ACHTUNG: {len(issues)} Formatabweichungen in den Profilen. "
                          f"{eng('label')} verwirft solche Profile stillschweigend."
                          + (" Details in purelapse_arp_check.log"
                             if self._diag() else
                             " Fuer die vollstaendige Liste den Diagnose-Modus einschalten."),
                f"> WARNING: {len(issues)} format deviations in the profiles. {eng('label')} silently discards such profiles." + (" Details in purelapse_arp_check.log" if self._diag() else " Switch on diagnostic mode for the full list.")))
            for line in issues[:3]:
                self.log.emit("    " + line)
        elif self._diag():
            self.log.emit(self._t(f"> Profilpruefung: {checked} Sidecars formal in Ordnung.",
                f"> Profile check: {checked} sidecars formally OK."))

    def _fortschritt(self, label, fertig, gesamt, start_zeit, zusatz=""):
        """Statuszeile und Fortschrittsbalken in einem Aufruf."""
        self.status.emit(fortschritt_text(label, fertig, gesamt, start_zeit,
                                          zusatz, lang=self.p.get('lang', 'de')))
        if gesamt:
            self.progress.emit(fertig, gesamt)

    def _l(self, label):
        """Name eines Arbeitsschritts fuers Protokoll. Intern bleibt er
        deutsch - daran erkennt die Ablaufanzeige die Phase (PHASEN)."""
        if self.p.get('lang') != 'en':
            return label
        for praefix, _k, _de, en in PHASEN:
            if str(label).startswith(praefix):
                return en + str(label)[len(praefix):]
        return label

    def _schritt_fertig(self, label, anzahl, start_zeit, einheit="Bilder"):
        """Meldet die tatsaechliche Dauer eines abgeschlossenen Schrittes."""
        dauer = max(0.0, time.time() - start_zeit)
        en = self.p.get('lang') == 'en'
        if en and einheit == "Bilder":
            einheit = "images"
        text = f"> {self._l(label)}: {anzahl} {einheit} in {dauer_text(dauer)}"
        if anzahl > 0 and dauer > 0:
            je = dauer / anzahl
            if en:
                text += (f" ({je:.2f} s per image)" if je >= 0.05
                         else f" ({anzahl / dauer:.0f} images per second)")
            else:
                text += (f" ({je:.2f} s je Bild)" if je >= 0.05
                         else f" ({anzahl / dauer:.0f} Bilder je Sekunde)")
        self.log.emit(text)

    def _count_rendered(self, out_dir, expected_stems):
        """Wie viele der erwarteten Zwischenbilder liegen schon im Ausgabeordner?"""
        tief = getattr(self, '_zw_render_tief', False)
        if expected_stems is None:
            return len({p for ext in zw_endungen(tief)
                        for p in glob.glob(os.path.join(out_dir, "*" + ext))})
        return sum(1 for st in expected_stems if zw_datei(out_dir, st, tief) is not None)

    def _platz_pruefen(self, todo, out_dir):
        """16-Bit-TIFFs sind gross: vor dem Entwickeln pruefen, ob sie Platz haben."""
        try:
            with rawpy.imread(todo[0]) as raw:
                breite, hoehe = raw.sizes.width, raw.sizes.height
        except Exception:
            breite, hoehe = 6000, 4000
        je_bild = breite * hoehe * 6 * 0.85          # 16 Bit x 3 Kanaele, leicht gepackt
        noetig = je_bild * len(todo) * 1.05
        try:
            frei = shutil.disk_usage(out_dir).free
        except OSError:
            return
        gb = lambda b: f"{b / 1024 ** 3:.0f} GB"
        self.log.emit(self._t(
            f"> 16-Bit-Zwischenbilder: etwa {gb(je_bild * len(todo))} fuer {len(todo)} Bilder, "
            f"frei {gb(frei)}.",
            f"> 16-bit intermediate images: about {gb(je_bild * len(todo))} for {len(todo)} "
            f"images, {gb(frei)} free."))
        if frei < noetig:
            raise RuntimeError(self._t(
                "Fuer die 16-Bit-Zwischenbilder reicht der Platz nicht: noetig etwa "
                f"{gb(noetig)}, frei {gb(frei)}.\n\nBitte Platz schaffen oder in den "
                "Einstellungen die 16-Bit-Zwischenbilder ausschalten.",
                "Not enough disk space for the 16-bit intermediate images: about "
                f"{gb(noetig)} needed, {gb(frei)} free.\n\nPlease free some space or switch "
                "off 16-bit intermediate images in the settings."))

    def _engine_warnungen_melden(self, logs, label):
        """
        Durchsucht die Ausgabe der Engine nach Hinweisen auf verworfene
        Profile und meldet sie ins Protokollfenster.

        Diese Zeilen sind der einzige Ort, an dem ART und RawTherapee
        sagen, dass sie ein Profil nicht laden konnten. Bisher gingen sie
        im Diagnose-Modus in eine Datei und sonst ins Leere.
        """
        # Nur echte Stoerungen. Das Wort "sidecar" allein taugt nicht als
        # Suchbegriff: die Engines schreiben bei JEDEM erfolgreich
        # geladenen Profil "Merging sidecar procparams." - damit schlug
        # die Warnung genau dann an, wenn alles in Ordnung war.
        schluessel = ("not found", "error", "warning", "cannot", "failed")
        treffer = []
        for lf in logs:
            if lf is None:
                continue
            try:
                lf.flush()
                lf.seek(0)
                text = lf.read().decode("utf-8", errors="ignore")
            except (OSError, ValueError):
                continue
            for zeile in text.splitlines():
                z = zeile.strip()
                if z and any(k in z.lower() for k in schluessel):
                    treffer.append(z)
        if not treffer:
            return
        # Gleiche Meldung nicht hundertmal wiederholen.
        gezaehlt = {}
        for z in treffer:
            gezaehlt[z] = gezaehlt.get(z, 0) + 1
        self.log.emit(self._t(f"> {eng('label')} meldet bei {label}:",
                f"> {eng('label')} reports for {self._l(label)}:"))
        for z, n in sorted(gezaehlt.items(), key=lambda t: -t[1])[:6]:
            self.log.emit(f"    {z}" + (f"   ({n}x)" if n > 1 else ""))
        # Je Bild schreibt die Engine bis zu zwei Zeilen (eine Warnung und,
        # mit -S, einen Fehler). Gezaehlt wird deshalb die groessere der
        # beiden Arten, nicht ihre Summe.
        gewarnt = sum(n for z, n in gezaehlt.items()
                      if "sidecar file requested but not found" in z.lower())
        verweigert = sum(n for z, n in gezaehlt.items()
                         if "no sidecar procparams" in z.lower())
        nicht_geladen = max(gewarnt, verweigert)
        if nicht_geladen:
            self.log.emit(
                self._t(f"> ACHTUNG: {nicht_geladen} Profil(e) konnte "
                f"{eng('label')} nicht laden. Diese Bilder wurden nicht "
                "entwickelt.",
                f"> WARNING: {eng('label')} could not load {nicht_geladen} profile(s). These images were not developed."))

    def _write_engine_log(self, cmds, procs, logs, label):
        """
        Haengt die Ausgaben aller Prozesse geordnet an purelapse_art.log.

        Jeder Prozess schreibt zunaechst in eine eigene temporaere Datei.
        Wuerden alle in dieselbe Datei schreiben, waere das Protokoll
        ineinander verschachtelt und nicht mehr lesbar.
        """
        # Mitgelesen wird immer (siehe _run_engine_cli), geschrieben nur
        # im Diagnose-Modus - im Normalbetrieb entstehen keine Dateien.
        if not self._diag() or not any(lf is not None for lf in logs):
            return
        pfad = pl_datei(self.p['target_dir'], "purelapse_art.log", anlegen=True)
        try:
            with open(pfad, "a", encoding="utf-8") as ziel:
                ziel.write(f"\n===== {label} - {time.strftime('%Y-%m-%d %H:%M:%S')}"
                           f" - {len(cmds)} Prozess(e) =====\n")
                for i, lf in enumerate(logs):
                    rc = procs[i].returncode if i < len(procs) else None
                    ziel.write(f"\n--- Prozess {i + 1}/{len(cmds)} "
                               f"(Rueckgabewert {rc}) ---\n")
                    ziel.write(" ".join(cmds[i]) + "\n")
                    if lf is None:
                        continue
                    try:
                        lf.flush()
                        lf.seek(0)
                        ziel.write(lf.read().decode("utf-8", errors="ignore"))
                    except (OSError, ValueError):
                        pass
        except OSError:
            pass
        for lf in logs:
            try:
                if lf is not None:
                    lf.close()
            except OSError:
                pass

    def _run_engine_cli(self, cmds, art_env, out_dir, total_dev, label,
                        expected_stems=None):
        """
        Startet einen oder mehrere ART-/RawTherapee-CLI-Prozesse und wartet
        mit Fortschrittsanzeige, bis alle fertig sind.
        NUR fuer die Engines vom Typ 'ini' (ART/RawTherapee).

        Der Fortschritt wird nicht aus der Ausgabe der Prozesse gelesen,
        sondern an den fertigen JPGs im Ausgabeordner gezaehlt. Das ist
        unabhaengig davon, wie viele Prozesse laufen.
        """
        logs, procs = [], []
        try:
            for cmd in cmds:
                # Immer mitlesen, nicht nur im Diagnose-Modus: ART und
                # RawTherapee melden ein nicht ladbares Profil nur hier,
                # und ohne diese Zeilen entwickeln sie stillschweigend mit
                # Standardwerten weiter.
                try:
                    lf = tempfile.TemporaryFile()
                except OSError:
                    lf = None
                logs.append(lf)
                procs.append(subprocess.Popen(
                    cmd, env=art_env,
                    stdout=lf or subprocess.DEVNULL,
                    stderr=subprocess.STDOUT if lf else subprocess.DEVNULL))

            start_time = time.time()
            while any(pr.poll() is None for pr in procs):
                if self._abort:
                    for pr in procs:
                        if pr.poll() is None:
                            pr.terminate()
                    for pr in procs:
                        try:
                            pr.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pr.kill()
                    raise RuntimeError(self._t("Vom Benutzer abgebrochen.",
                                               "Cancelled by user."))
                done = self._count_rendered(out_dir, expected_stems)
                self._fortschritt(label, done, total_dev, start_time)
                time.sleep(1.0)
            fertig = self._count_rendered(out_dir, expected_stems)
            self.progress.emit(fertig, total_dev)
            self._schritt_fertig(label, fertig, start_time)
        finally:
            self._write_engine_log(cmds, procs, logs, label)

        self._engine_warnungen_melden(logs, label)
        fehler = [(i + 1, pr.returncode) for i, pr in enumerate(procs)
                  if pr.returncode not in (0, None)]
        if fehler:
            hinweis = (" - Details in purelapse_art.log" if self._diag()
                       else " - fuer Details den Diagnose-Modus einschalten")
            wo = ", ".join(f"Prozess {n}: {rc}" for n, rc in fehler)
            self.log.emit(self._t(f"> ACHTUNG: {eng('label')} endete mit Fehlercode "
                          f"({wo}){hinweis}",
                f"> WARNING: {eng('label')} ended with an error code ({wo}){hinweis}"))

    def _run_darktable_cli(self, files, out_dir, label, quality=100, tief=False):
        """
        Rendert mit darktable-cli, das je Aufruf nur ein Bild entwickelt.

        Mehrere Prozesse laufen gleichzeitig, jeder mit eigenem
        Konfigurationsordner (siehe dt_konfig_slots). Jeder Prozess hat ein
        Zeitlimit, und ein Abbruch beendet die laufenden Prozesse sofort -
        bisher wartete Purelapse auf das gerade laufende Bild, und ein
        haengendes darktable-cli hielt den ganzen Lauf an.
        """
        dt_cli = self.p['art_cli_path']
        total = len(files)
        if not total:
            return
        start_time = time.time()
        kerne = max(1, int(self.p.get('cores', 1)))
        jobs = prozess_anzahl(total, kerne, self.p.get('procs', 0))
        frei = freier_speicher_gb()
        if frei:
            jobs = min(jobs, max(1, int(frei // DT_GB_PRO_PROZESS)))
        jobs = max(1, min(jobs, DT_MAX_PROZESSE))
        try:
            slots, quelle = dt_konfig_slots(jobs, os.path.join(cache_ordner(), "darktable"))
        except OSError as e:
            raise RuntimeError(self._t(
                f"Arbeitsordner fuer darktable-cli nicht anlegbar: {e}",
                f"Could not create working folders for darktable-cli: {e}"))
        if quelle is None:
            self.log.emit(self._t(
                "> HINWEIS: darktable-Einstellungen nicht gefunden - darktable-cli "
                "arbeitet mit seinen Grundeinstellungen.",
                "> NOTE: darktable settings not found - darktable-cli uses its "
                "defaults."))
        if jobs > 1:
            self.log.emit(self._t(f"> darktable-cli: {jobs} Prozesse gleichzeitig.",
                                  f"> darktable-cli: {jobs} processes at once."))
        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = str(max(1, kerne // jobs))
        log_path = pl_datei(self.p['target_dir'], "purelapse_art.log")
        dt_log = None
        if self._diag():
            try:
                dt_log = open(log_path, "a", encoding="utf-8")
                dt_log.write(f"\n===== {label} (darktable-cli, {jobs} Prozesse) - "
                             f"{time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            except OSError:
                dt_log = None
        offen = list(files)
        laufend = []           # [proc, bild, ziel, start, slot, ausgabe-datei]
        frei_slots = list(slots)
        fertig = fehler = zeitueber = 0
        fehlerbilder = []

        def beenden(eintrag):
            proc, slot = eintrag[0], eintrag[4]
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            # Ein hart beendetes darktable-cli raeumt seine Sperren nicht weg.
            for sperre in ('data.db.lock', 'library.db.lock'):
                try:
                    os.remove(os.path.join(slot, sperre))
                except OSError:
                    pass

        def abschliessen(eintrag):
            proc, bild, ziel, _t0, slot, ausgabe = eintrag
            if ausgabe is not None:
                try:
                    ausgabe.seek(0)
                    text = ausgabe.read().decode("utf-8", errors="ignore")
                    ausgabe.close()
                    if dt_log and text.strip():
                        dt_log.write(text if text.endswith("\n") else text + "\n")
                except (OSError, ValueError):
                    pass
            frei_slots.append(slot)

        try:
            while offen or laufend:
                if self._abort:
                    for eintrag in laufend:
                        beenden(eintrag)
                        abschliessen(eintrag)
                    laufend = []
                    self._check_abort()
                while offen and frei_slots:
                    bild = offen.pop(0)
                    slot = frei_slots.pop(0)
                    stem = os.path.splitext(os.path.basename(bild))[0]
                    ziel = os.path.join(out_dir, stem + (".tif" if tief else ".jpg"))
                    cmd = dt_build_cli_cmd(dt_cli, bild, sidecar(bild), ziel,
                                           quality=quality, configdir=slot, tief=tief)
                    ausgabe = tempfile.TemporaryFile() if dt_log else None
                    if dt_log:
                        dt_log.write(" ".join(cmd) + "\n")
                    try:
                        proc = subprocess.Popen(
                            cmd, env=env, stdin=subprocess.DEVNULL,
                            stdout=(ausgabe or subprocess.DEVNULL),
                            stderr=subprocess.STDOUT if ausgabe else subprocess.DEVNULL)
                    except OSError as e:
                        frei_slots.append(slot)
                        raise RuntimeError(self._t(
                            f"darktable-cli liess sich nicht starten: {e}",
                            f"darktable-cli could not be started: {e}"))
                    laufend.append([proc, bild, ziel, time.time(), slot, ausgabe])
                time.sleep(0.1)
                noch = []
                for eintrag in laufend:
                    proc, bild, ziel, t0 = eintrag[:4]
                    rc = proc.poll()
                    if rc is None:
                        if time.time() - t0 > DT_ZEITLIMIT_S:
                            beenden(eintrag)
                            zeitueber += 1
                            fehlerbilder.append(os.path.basename(bild))
                            try:
                                os.remove(ziel)
                            except OSError:
                                pass
                            abschliessen(eintrag)
                            fertig += 1
                        else:
                            noch.append(eintrag)
                        continue
                    if rc != 0 or not os.path.exists(ziel):
                        fehler += 1
                        fehlerbilder.append(os.path.basename(bild))
                    abschliessen(eintrag)
                    fertig += 1
                    self._fortschritt(label, fertig, total, start_time,
                                      zusatz=os.path.basename(bild))
                laufend = noch
        finally:
            for eintrag in laufend:
                beenden(eintrag)
                abschliessen(eintrag)
            if dt_log:
                try:
                    dt_log.close()
                except OSError:
                    pass
        self._schritt_fertig(label, fertig - fehler - zeitueber, start_time)
        hinweis = self._t(" - Details in purelapse_art.log" if self._diag()
                          else " - fuer Details den Diagnose-Modus einschalten",
                          " - details in purelapse_art.log" if self._diag()
                          else " - switch on diagnostic mode for details")
        if zeitueber:
            self.log.emit(self._t(
                f"> ACHTUNG: darktable-cli brauchte bei {zeitueber} Bildern laenger "
                f"als {DT_ZEITLIMIT_S // 60} Minuten und wurde beendet: "
                f"{', '.join(fehlerbilder[:5])}{hinweis}",
                f"> WARNING: darktable-cli took longer than {DT_ZEITLIMIT_S // 60} "
                f"minutes for {zeitueber} images and was stopped: "
                f"{', '.join(fehlerbilder[:5])}{hinweis}"))
        if fehler:
            self.log.emit(self._t(
                f"> ACHTUNG: darktable-cli meldete bei {fehler} von {total} "
                f"Bildern einen Fehler{hinweis}",
                f"> WARNING: darktable-cli reported an error for {fehler} of "
                f"{total} images{hinweis}"))

    def _sichere_teilstand(self, todo, out_dir):
        """
        Haelt nach einem Abbruch fest, was schon fertig entwickelt ist.

        Ohne das ginge beim Abbruch die ganze bisherige Arbeit verloren:
        der Merker wurde bisher erst nach dem regulaeren Ende der Engine
        geschrieben, also genau dann nicht, wenn man ihn braucht.

        Die juengsten Dateien werden dabei verworfen - je laufendem
        Prozess eine. Die Engine wurde mitten im Schreiben beendet, und
        ein halb geschriebenes JPG laesst sich oft trotzdem oeffnen; im
        Film waere es ein Bild mit grauem Balken.
        """
        vorhanden = []
        for f in todo:
            stamm = os.path.splitext(os.path.basename(f))[0]
            pfad = zw_datei(out_dir, stamm, getattr(self, '_zw_tief', False))
            if pfad is not None:
                try:
                    vorhanden.append((os.path.getmtime(pfad), pfad, f))
                except OSError:
                    pass
        vorhanden.sort()
        unsicher = max(1, int(getattr(self, '_prozesse_zuletzt', 1)))
        for _zeit, pfad, _f in vorhanden[-unsicher:]:
            try:
                os.remove(pfad)
            except OSError:
                pass
        sicher = [f for _zeit, _pfad, f in vorhanden[:-unsicher]]
        if sicher:
            mark_developed(sicher, out_dir, getattr(self, '_zw_tief', False))
            self.log.emit(self._t(f"> Abbruch: {len(sicher)} fertig entwickelte Bilder "
                          "bleiben erhalten, der naechste Lauf setzt dort auf.",
                f"> Cancelled: {len(sicher)} fully developed images are kept, the next run continues from there."))

    def _entwickelte(self, files, out_dir):
        """
        Das entwickelte JPG zu jedem Bild, in Bildreihenfolge.

        Bewusst NICHT einfach alle JPGs des Ausgabeordners: dort koennen
        Reste eines frueheren Laufs liegen, und die gehoeren nicht in den
        Film. Umgekehrt faellt so auf, wenn ein erwartetes Bild fehlt.

        Rueckgabe: (Liste der JPG-Pfade, Namen der fehlenden Bilder)
        """
        gefunden, fehlend = [], []
        tief = getattr(self, '_zw_tief', False)
        for f in files:
            stamm = os.path.splitext(os.path.basename(f))[0]
            pfad = zw_datei(out_dir, stamm, tief)
            if pfad is not None:
                gefunden.append(pfad)
            else:
                fehlend.append(os.path.basename(f))
        return gefunden, fehlend

    def _alle_entwickelt(self, files, out_dir):
        """Wie _entwickelte, bricht aber ab, wenn etwas fehlt."""
        gefunden, fehlend = self._entwickelte(files, out_dir)
        if not gefunden:
            raise RuntimeError(self._t("Keine entwickelten JPGs gefunden.",
                                       "No developed JPGs found."))
        if fehlend:
            namen = ", ".join(fehlend[:6]) + (" ..." if len(fehlend) > 6 else "")
            if self.p.get('lang') == 'en':
                raise RuntimeError(
                    f"{len(fehlend)} of {len(files)} images were not "
                    f"developed: {namen}\n\n"
                    f"{eng('label')} did not load the profile of these images "
                    "or could not read the file - the reason is in the log "
                    "above.\n\n"
                    "A video with missing frames would jump at these points, "
                    "so it stops here. The frames already developed are kept; "
                    "after the fix, pass 2 resumes from there.")
            raise RuntimeError(
                f"{len(fehlend)} von {len(files)} Bildern wurden nicht "
                f"entwickelt: {namen}\n\n"
                f"{eng('label')} hat das Profil dieser Bilder nicht geladen "
                "oder die Datei nicht lesen koennen - der Grund steht im "
                "Protokoll darueber.\n\n"
                "Ein Video mit fehlenden Bildern wuerde an diesen Stellen "
                "springen, deshalb wird hier angehalten. Die bereits "
                "entwickelten Bilder bleiben erhalten; nach der Korrektur "
                "setzt Pass 2 dort wieder auf.")
        return gefunden

    def _pruefe_sidecars(self, files):
        """
        Stellt vor dem Entwickeln sicher, dass die Profile da sind und
        etwas enthalten.

        Der haeufigste Fall, in dem ein Zeitraffer unentflackert aus dem
        Rechner kommt: Pass 1 lief mit einer anderen Engine. Die Profile
        liegen dann als .arp oder .xmp im Ordner, die eingestellte Engine
        sucht aber ihre eigene Endung, findet nichts - und entwickelt
        ohne jede Korrektur.
        """
        if eng('kind') != 'ini':
            return
        vorhanden, fehlend = [], []
        for f in files:
            (vorhanden if os.path.exists(sidecar(f)) else fehlend).append(f)

        if not vorhanden:
            fremd = []
            # Nicht ueber die globale ENGINE vergleichen: die steht in
            # diesem Modul als Kopie vom Importzeitpunkt und wechselt bei
            # set_engine() nicht mit. Die Endung ist eindeutig.
            for _key, cfg in ENGINES.items():
                if cfg['ext'] == eng('ext'):
                    continue
                treffer = [f for f in files[:50]
                           if os.path.exists(f + cfg['ext'])]
                if treffer:
                    fremd.append(cfg['label'])
            hinweis = ""
            if fremd:
                hinweis = ("\n\nIm Ordner liegen aber Profile von "
                           f"{' und '.join(fremd)}. Dieser Ordner wurde "
                           "offenbar damit vorbereitet, eingestellt ist "
                           f"aber {eng('label')}.\n"
                           "Entweder die Engine zurueckstellen oder Pass 1 "
                           f"mit {eng('label')} erneut laufen lassen.")
            if not hinweis:
                hinweis = ("\n\nBitte zuerst Pass 1 laufen lassen - der "
                           "misst die Bilder und legt die Profile an.")
            if self.p.get('lang') == 'en':
                hinweis_en = (
                    "\n\nThe folder does contain profiles from "
                    f"{' and '.join(fremd)}. It was evidently prepared with "
                    f"that, but {eng('label')} is selected.\n"
                    "Either switch the engine back or run pass 1 again "
                    f"with {eng('label')}." if fremd else
                    "\n\nPlease run pass 1 first - it measures the images "
                    "and creates the profiles.")
                raise RuntimeError(
                    f"No {eng('ext')} profiles found in the folder.\n\n"
                    f"{eng('label')} would develop every image with its "
                    "default values - the result would be a timelapse "
                    "without any deflicker." + hinweis_en)
            raise RuntimeError(
                f"Keine {eng('ext')}-Profile im Ordner gefunden.\n\n"
                f"{eng('label')} wuerde jedes Bild mit seinen "
                "Standardwerten entwickeln - das Ergebnis waere ein "
                "Zeitraffer ganz ohne Entflackerung." + hinweis)

        if fehlend:
            namen = ", ".join(os.path.basename(f) for f in fehlend[:5])
            if self.p.get('lang') == 'en':
                raise RuntimeError(
                    f"{len(fehlend)} of {len(files)} images have no "
                    f"{eng('ext')} profile, for example {namen}.\n\n"
                    "These images would be developed without correction and "
                    "stand out as a jump in the video.\n"
                    "Please run pass 1 again.")
            raise RuntimeError(
                f"{len(fehlend)} von {len(files)} Bildern haben kein "
                f"{eng('ext')}-Profil, zum Beispiel {namen}.\n\n"
                "Diese Bilder wuerden ohne Korrektur entwickelt und im "
                "Video als Sprung auffallen.\n"
                "Bitte Pass 1 erneut laufen lassen.")

        # Steht ueberhaupt eine Entflackerung drin?
        werte = []
        for f in vorhanden:
            try:
                v = read_arp_dict(sidecar(f)).get('Exposure', {}).get('Compensation')
                werte.append(float(v))
            except (TypeError, ValueError):
                pass
        if len(werte) >= 3:
            spanne = max(werte) - min(werte)
            if spanne < 0.002:
                self.log.emit(
                    self._t("> WARNUNG: Die Belichtungskorrektur ist in allen "
                    f"{len(werte)} Profilen gleich ({werte[0]:+.3f} EV). "
                    "Das Video wird genauso flackern wie das Rohmaterial.",
                f"> WARNING: The exposure correction is the same in all {len(werte)} profiles ({werte[0]:+.3f} EV). The video will flicker just like the raw material."))
                self.log.emit(
                    self._t("> Ursache ist fast immer: Pass 1 lief nicht, lief mit "
                    "einer anderen Engine, oder die Profile wurden "
                    "zwischendurch zurueckgesetzt.",
                "> The cause is almost always: pass 1 did not run, ran with a different engine, or the profiles were reset in between."))
            elif not getattr(self, '_profile_berichtet', False):
                self.log.emit(self._t(f"> Profile geprueft: {len(werte)} Bilder, "
                              f"Korrektur spannt {spanne:.2f} EV.",
                f"> Profiles checked: {len(werte)} images, correction spans {spanne:.2f} EV."))
            self._profile_berichtet = True

    def _render_with_engine(self, files, out_dir, label, quality=100, tief=False):
        """
        Gemeinsamer Verteiler fuer Pass 2 und Vorschau.
        ART/RT rendern eine Liste von Dateien in einem CLI-Lauf,
        Darktable rendert Datei fuer Datei (siehe _run_darktable_cli).
        """
        self._zw_render_tief = tief
        if eng('kind') == 'darktable':
            self._run_darktable_cli(files, out_dir, label, quality=quality, tief=tief)
            return
        self._pruefe_sidecars(files)
        kerne = max(1, int(self.p.get('cores', 1)))
        jobs = prozess_anzahl(len(files), kerne, self.p.get('procs', 0))
        teile = bilder_aufteilen(files, jobs)
        self._prozesse_zuletzt = len(teile)
        threads = max(1, kerne // len(teile))
        art_env = os.environ.copy()
        art_env["OMP_NUM_THREADS"] = str(threads)
        # "-S" statt "-s": ohne Sidecar bricht die Engine ab. Mit "-s"
        # wuerde sie mit ihrem Standardprofil weiterentwickeln, und das
        # Ergebnis waere ein unentflackertes Video ohne jede Fehlermeldung.
        grund = [self.p['art_cli_path'], "-S", "-Y", "-o", out_dir]
        # 16 Bit: gepacktes TIFF; sonst JPG in der gewuenschten Qualitaet
        grund += ["-tz", "-b16"] if tief else [f"-j{quality}"]
        cmds = [grund + eng('extra') + ["-c"] + teil for teil in teile]
        stems = [os.path.splitext(os.path.basename(f))[0] for f in files]
        self.log.emit(self._t(f"\n> {eng('label').upper()}-CLI ENGINE - {label}: {len(files)} Bilder",
                f"\n> {eng('label').upper()}-CLI ENGINE - {self._l(label)}: {len(files)} images"))
        if len(cmds) > 1:
            self.log.emit(self._t(f"> {len(cmds)} Prozesse parallel, je {threads} Threads "
                          f"({', '.join(str(len(t)) + ' Bilder' for t in teile)})",
                f"> {len(cmds)} processes in parallel, {threads} threads each ({', '.join(str(len(t)) + ' images' for t in teile)})"))
            self.log.emit(" ".join(grund + eng('extra') + ["-c"]) + " <Bilderliste>\n")
        else:
            self.log.emit(" ".join(cmds[0]) + "\n")
        self._run_engine_cli(cmds, art_env, out_dir, len(files), label,
                             expected_stems=stems)

    def _measure_and_correct(self, jpgs, files, apply_correction=True):
        """Misst das Rendering-Ergebnis und schreibt die Restabweichung in die Sidecars."""
        p = self.p
        arp_by_stem = {os.path.splitext(os.path.basename(f))[0]: f for f in files}
        calib_map = load_calib(p['target_dir'])
        lin, valid = [], []
        roi = p.get('roi_rel')
        # Messwerte merken: in den Runden der Nachkalibrierung werden nur
        # die geaenderten Bilder neu entwickelt. Alle anderen JPGs sind
        # dieselben Dateien wie zuvor (gleiche Aenderungszeit und Groesse),
        # ihre Messung kaeme auf dieselbe Zahl.
        merker = self.__dict__.setdefault('_mess_merker', {})

        def _schluessel(pfad):
            try:
                st = os.stat(pfad)
                return (pfad, st.st_mtime_ns, st.st_size,
                        tuple(roi) if roi else None)
            except OSError:
                return None

        schluessel = [_schluessel(jf) for jf in jpgs]
        offen = [jf for jf, k in zip(jpgs, schluessel)
                 if k is None or k not in merker]
        start_mess = time.time()
        threads = mess_threads(p.get('cores', 1))
        neu = parallel_messen(
            jpg_bloecke, [(jf, roi) for jf in offen], threads,
            self._check_abort,
            lambda fertig, gesamt: self._fortschritt(
                "Messe Ergebnis", fertig, gesamt, start_mess))
        frisch = dict(zip(offen, neu))
        bloecke = []
        for jf, k in zip(jpgs, schluessel):
            if jf in frisch:
                b = frisch[jf]
                if k is not None:
                    merker[k] = b
            else:
                b = merker[k]
            bloecke.append(b)
        for jf, v in zip(jpgs, sequenz_helligkeit(bloecke)):
            if v is not None and v > 0:
                lin.append(v)
                valid.append(jf)
        uebernommen = len(jpgs) - len(offen)
        if offen:
            dauer = max(0.0, time.time() - start_mess)
            self.log.emit(
                self._t(f"> Messung: {len(offen)} Bilder in {dauer_text(dauer)}"
                + (f", {threads} gleichzeitig" if threads > 1 else "")
                + (f"; {uebernommen} unveraenderte uebernommen"
                   if uebernommen else ""),
                f"> Measurement: {len(offen)} images in {dauer_text(dauer)}" + (f", {threads} at once" if threads > 1 else "") + (f"; {uebernommen} unchanged reused" if uebernommen else "")))
        if len(lin) < 3:
            return None, [], []
        a = np.asarray(lin, dtype=np.float64)
        calib_smooth = min(int(p['smooth_val']), 15)
        target = two_pass_smooth(a, 0, calib_smooth)
        resid = np.log2(np.maximum(target, 1e-9) / np.maximum(a, 1e-9))
        resid = resid - float(np.median(resid))
        sigma = float(np.std(resid))
        if sigma < RESTFLACKERN_ZIEL:
            # Ziel erreicht: der Lauf endet hier. Eine jetzt noch
            # geschriebene Korrektur wuerde nicht mehr entwickelt - die
            # Profile waeren den Bildern voraus, und der naechste Lauf
            # entwickelte grundlos einen Teil der Bilder neu.
            apply_correction = False
        CALIB_LIMIT = 0.5
        rows = []
        clipped = 0
        changed = []
        STEP_MIN = 0.005
        for i, jf in enumerate(valid):
            stem = os.path.splitext(os.path.basename(jf))[0]
            nef = arp_by_stem.get(stem)
            arp_path = sidecar(nef) if nef else None
            comp = float('nan')
            secs = 0
            if arp_path and os.path.exists(arp_path):
                d = read_arp_dict(arp_path)
                secs = len(d)
                try:
                    comp = float(d.get('Exposure', {}).get('Compensation', 'nan'))
                except ValueError:
                    comp = float('nan')
                if apply_correction and not math.isnan(comp):
                    key = os.path.basename(nef)
                    total = float(calib_map.get(key, 0.0)) + float(resid[i])
                    if abs(total) > CALIB_LIMIT:
                        total = math.copysign(CALIB_LIMIT, total)
                        clipped += 1
                    step = total - float(calib_map.get(key, 0.0))
                    if abs(step) >= STEP_MIN:
                        set_exposure(d, comp + step)
                        write_arp_dict(arp_path, d)
                        calib_map[key] = round(total, 4)
                        changed.append(nef)
            rows.append({
                'idx': i, 'file': os.path.basename(jf),
                'jpg_luma_linear': round(lin[i], 6),
                'target_linear': round(float(target[i]), 6),
                'residual_ev': round(float(resid[i]), 4),
                'arp_comp': comp, 'arp_sections': secs,
            })
        save_residuals(p['target_dir'],
                       {r['file']: r['residual_ev'] for r in rows})
        if apply_correction:
            save_calib(p['target_dir'], calib_map)
            self.log.emit(self._t("> Nachkalibrierung geschrieben, groesste Anpassung "
                          f"{np.abs(resid).max():.3f} EV",
                f"> Recalibration written, largest adjustment {np.abs(resid).max():.3f} EV"))
            if clipped:
                self.log.emit(self._t(f"> WARNUNG: Bei {clipped} Bildern wurde die Kalibrierung "
                              f"auf {CALIB_LIMIT} EV begrenzt. Die Zielkurve aus Pass 1 "
                              "ist so nicht erreichbar - bitte Szenario und "
                              "Deflicker-Staerke pruefen.",
                f"> WARNING: For {clipped} images the calibration was limited to {CALIB_LIMIT} EV. The target curve from pass 1 cannot be reached this way - please check the scenario and the deflicker strength."))
        return sigma, rows, changed

    def _run_raw_pass2(self):
        p = self.p
        abs_target_dir = p['target_dir']
        files = p['files']
        max_blur, min_blur = p['max_blur'], p['min_blur']
        self.log.emit(self._t("> Starte RAW Pass 2 (Rendern)...",
                "> Starting RAW pass 2 (rendering)..."))
        # Zuerst: sind die Profile ueberhaupt da, und gehoeren sie zur
        # eingestellten Engine? Die Pruefung auf Vollstaendigkeit darunter
        # hielt fehlende Profile bisher fuer "unvollstaendig" und riet zu
        # einem Basisprofil - das fuehrt in die falsche Richtung, wenn in
        # Wahrheit Pass 1 fehlt oder mit einer anderen Engine lief.
        self._pruefe_sidecars(files)
        thin = sum(1 for f in files if not profile_is_complete(read_arp_dict(sidecar(f))))
        if thin:
            self.log.emit(self._t(f"> ACHTUNG: {thin} von {len(files)} Sidecar-Dateien enthalten kein "
                          f"vollständiges {eng('label')}-Profil. {eng('label')} verwirft solche "
                          "Sidecars, die Deflicker-Korrektur bliebe wirkungslos.",
                f"> WARNING: {thin} of {len(files)} sidecar files contain no complete {eng('label')} profile. {eng('label')} discards such sidecars, the deflicker correction would have no effect."))
            if thin == len(files) and eng('kind') != 'darktable':
                if p.get('lang') == 'en':
                    raise RuntimeError(
                        f"All {len(files)} sidecar files are incomplete (only "
                        "[Exposure], no [Version] block).\n\n"
                        f"{eng('label')} would ignore them and develop the RAWs "
                        "with the default profile - the video would keep "
                        "flickering.\n\n"
                        f"Please set a {eng('label')} base profile in the "
                        "settings and run pass 1 again.")
                raise RuntimeError(
                    f"Alle {len(files)} Sidecar-Dateien sind unvollständig (nur [Exposure], "
                    "kein [Version]-Block).\n\n"
                    f"{eng('label')} würde sie ignorieren und die RAWs mit dem "
                    "Standardprofil entwickeln - das Video flackert dann unverändert weiter.\n\n"
                    f"Bitte ein {eng('label')}-Basisprofil unter Punkt 4 hinterlegen und "
                    "Pass 1 erneut laufen lassen."
                )
        self._automatik_einfrieren(files)
        self._prepare_keyframe_profiles(files)
        out_dir = zwischen_ordner(abs_target_dir)
        os.makedirs(out_dir, exist_ok=True)
        tief = bool(p.get('tiff16'))
        self._zw_tief = tief
        max_rounds = 1 + max(0, int(p.get('calib_rounds', 2)))
        processed_jpgs = []
        report_rows = []
        todo = pending_development(files, out_dir, tief)
        if tief and todo:
            self._platz_pruefen(todo, out_dir)
        uebersprungen = len(files) - len(todo)
        if uebersprungen:
            self.log.emit(self._t(f"> Fortsetzung: {uebersprungen} von {len(files)} Bildern "
                          "liegen bereits passend entwickelt vor.",
                f"> Resuming: {uebersprungen} of {len(files)} images are already developed and up to date."))
        if not todo:
            self.log.emit(self._t(f"> Alle Bilder sind aktuell, {eng('label')} wird uebersprungen.",
                f"> All images are up to date, {eng('label')} is skipped."))
        for rnd in range(max_rounds):
            self._check_abort()
            stems = [os.path.splitext(os.path.basename(f))[0] for f in todo]
            for s in stems:
                for ext in ZW_JPG + ZW_TIF:
                    try:
                        os.remove(os.path.join(out_dir, s + ext))
                    except OSError:
                        pass
            if not todo:
                processed_jpgs = self._alle_entwickelt(files, out_dir)
                residual, report_rows, _ = self._measure_and_correct(
                    processed_jpgs, files, apply_correction=False)
                break
            label = "Entwicklung" if rnd == 0 else f"Nachkalibrierung {rnd}"
            try:
                self._render_with_engine(todo, out_dir, label, quality=100, tief=tief)
            except BaseException:
                self._sichere_teilstand(todo, out_dir)
                raise
            mark_developed(todo, out_dir, tief)
            processed_jpgs = self._alle_entwickelt(files, out_dir)
            residual, rows, changed = self._measure_and_correct(
                processed_jpgs, files, apply_correction=(rnd < max_rounds - 1))
            report_rows = rows
            if residual is None:
                break
            self.log.emit(self._t(f"> Restflackern nach {label}: {residual:.4f} EV (Sigma)",
                f"> Residual flicker after {self._l(label)}: {residual:.4f} EV (sigma)"))
            if residual < RESTFLACKERN_ZIEL:
                self.log.emit(self._t("> Ziel erreicht, keine weitere Nachkalibrierung noetig.",
                "> Target reached, no further recalibration needed."))
                break
            if rnd < max_rounds - 1:
                if not changed:
                    self.log.emit(self._t("> Keine nennenswerte Anpassung mehr noetig.",
                "> No significant adjustment needed any more."))
                    break
                todo = changed
        self._save_report("purelapse_pass2.csv", report_rows)
        file_list_for_video = processed_jpgs
        stab_diffs = None
        if p['make_video'] and p['stabilize']:
            self.log.emit(self._t("\n> Führe Optische Stabilisierung durch...",
                "\n> Running optical stabilisation..."))
            stab_diffs = calculate_stabilization(file_list_for_video, self.status, self.progress, self._check_abort)
        width = p['width']
        calc_height = int(width * 9 / 16)
        render_sequence = list(file_list_for_video)
        if p['reverse_play']:
            render_sequence = render_sequence[::-1]
        ffmpeg_proc = None
        out_video = None
        if p['make_video']:
            out_video = self._get_output_video_path()
            ffmpeg_cmd = self._build_ffmpeg_cmd(width, calc_height, out_video, tief=tief)
            self.log.emit(self._t("\n> STARTE FFMPEG ENCODER:",
                "\n> STARTING FFMPEG ENCODER:"))
            self.log.emit(" ".join(ffmpeg_cmd) + "\n")
            ffmpeg_proc = self._start_encoder(ffmpeg_cmd)
        start_time = time.time()

        def laden(f):
            img = bild_lesen(f)
            if img is not None and tief and img.dtype != np.uint16:
                img = img.astype(np.uint16) * 257
            return img

        def exif_von(f):
            return find_original_raw(abs_target_dir, os.path.splitext(os.path.basename(f))[0])

        anzahl = self._video_bauen(render_sequence, laden, exif_von, ffmpeg_proc,
                                   stab_diffs, width, calc_height)
        self._schritt_fertig("Video", anzahl, start_time)
        if p['make_video'] and ffmpeg_proc:
            self._finish_encoder(ffmpeg_proc)
            self.finished_ok.emit(self._t(f"Fertiges Video:\n{out_video}",
                                          f"Finished video:\n{out_video}"))
        else:
            self.finished_ok.emit(self._t(f"Entflackerte JPGs liegen in:\n{out_dir}",
                                          f"Deflickered JPGs are in:\n{out_dir}"))

# ==========================================================================
#  HAUPTFENSTER
# ==========================================================================
def zustand_setzen(widget, wert, name='zustand'):
    """Setzt eine Eigenschaft, nach der das Stylesheet unterscheidet, und
    laesst das Aussehen neu berechnen - von allein merkt Qt das nicht."""
    if widget.property(name) == wert:
        return
    widget.setProperty(name, wert)
    try:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
    except Exception:
        pass


class AblaufLeiste(QtWidgets.QFrame):
    """
    Die Schritte eines Laufs nebeneinander: erledigt, laufend, ausstehend,
    jeweils mit Zeitangabe. Was drinsteht, bestimmt ein Ablauf-Objekt;
    diese Klasse zeichnet nur.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zeile = QtWidgets.QHBoxLayout(self)
        self._zeile.setContentsMargins(0, 0, 0, 0)
        self._zeile.setSpacing(6)
        self._karten = []          # [(rahmen, strich, name, zeit)]
        self._schluessel = []
        # Durchsichtig: sonst malte die Leiste die Fensterfarbe zwischen
        # die Karten.
        self.setObjectName("ablauf")
        self.setVisible(False)

    def _aufbauen(self, schluessel):
        for rahmen, _strich, _name, _zeit in self._karten:
            self._zeile.removeWidget(rahmen)
            rahmen.setParent(None)
            rahmen.deleteLater()
        self._karten = []
        for _key in schluessel:
            rahmen = QtWidgets.QFrame(self)
            rahmen.setObjectName("phase")
            rahmen.setMinimumWidth(60)
            v = QtWidgets.QVBoxLayout(rahmen)
            v.setContentsMargins(10, 0, 10, 7)
            v.setSpacing(2)
            strich = QtWidgets.QFrame(rahmen)
            strich.setObjectName("phasenstrich")
            name = QtWidgets.QLabel("", rahmen)
            name.setObjectName("phasename")
            zeit = QtWidgets.QLabel("", rahmen)
            zeit.setObjectName("phasezeit")
            for lbl in (name, zeit):
                # Die Karten teilen sich die Breite gleichmaessig; ein
                # langer Text darf das Fenster nicht breiter machen.
                lbl.setSizePolicy(QtWidgets.QSizePolicy.Ignored,
                                  QtWidgets.QSizePolicy.Preferred)
            v.addWidget(strich)
            v.addWidget(name)
            v.addWidget(zeit)
            self._zeile.addWidget(rahmen, 1)
            self._karten.append((rahmen, strich, name, zeit))
        self._schluessel = list(schluessel)

    def zeige(self, ablauf, lang='de', jetzt=None):
        """Bringt die Anzeige auf den Stand des Ablaufs."""
        if ablauf is None or not ablauf.schritte:
            self.setVisible(False)
            return
        schluessel = [s['key'] for s in ablauf.schritte]
        if schluessel != self._schluessel:
            self._aufbauen(schluessel)
        for s, (rahmen, strich, name, zeit) in zip(ablauf.schritte, self._karten):
            titel, zeittext, tip = ablauf_texte(ablauf, s, lang, jetzt)
            if name.text() != titel:
                name.setText(titel)
            if zeit.text() != zeittext:
                zeit.setText(zeittext)
            rahmen.setToolTip(tip)
            for w in (rahmen, strich, name, zeit):
                zustand_setzen(w, s['zustand'])
        self.setVisible(True)

    def texte(self):
        """Was gerade zu lesen ist: [(Titel, Zeit, Zustand)] - fuer Tests."""
        return [(name.text(), zeit.text(), rahmen.property('zustand'))
                for rahmen, _strich, name, zeit in self._karten]


# ==========================================================================
#  TELEGRAM-BENACHRICHTIGUNG
#
#  Nach einem langen Lauf eine Nachricht aufs Handy: fertig oder Fehler,
#  mit Dauer, Restflackern und Dateiname. Gesendet wird ueber die Bot-API
#  von Telegram (eine einfache HTTPS-Anfrage, keine zusaetzliche
#  Bibliothek). Bot-Token und Chat-ID liegen in einer eigenen Datei, die
#  nur der Benutzer lesen darf.
# ==========================================================================
TELEGRAM_API = "https://api.telegram.org/bot{token}/{methode}"


def telegram_laden():
    d = konfig_lesen('telegram', standard={})
    if isinstance(d, dict):
        return {'an': bool(d.get('an')), 'token': str(d.get('token', "")).strip(),
                'chat': str(d.get('chat', "")).strip()}
    return {'an': False, 'token': "", 'chat': ""}


def telegram_speichern(an, token, chat):
    # Die Konfigurationsdatei ist nur fuer den Benutzer lesbar (0600).
    konfig_setzen('telegram', {'an': bool(an), 'token': token.strip(), 'chat': chat.strip()})


def telegram_anfrage(token, methode, daten=None, timeout=15, lang='de'):
    """
    Eine Anfrage an die Bot-API. Rueckgabe: (True, Antwort-Dict) oder
    (False, Fehlertext). Der Token erscheint nie in einer Fehlermeldung.
    Die eigenen Fehlertexte folgen der Sprache der Oberflaeche; was die
    Bot-API selbst meldet ('description'), kommt von Telegram auf Englisch.
    """
    en = (lang == 'en')
    import urllib.request
    import urllib.parse
    import urllib.error
    if not token:
        return False, ("No bot token entered." if en else "Kein Bot-Token eingetragen.")
    url = TELEGRAM_API.format(token=token, methode=methode)
    rumpf = urllib.parse.urlencode(daten or {}).encode("utf-8")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=rumpf),
                                    timeout=timeout) as antwort:
            d = json.loads(antwort.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read().decode("utf-8", "ignore"))
            return False, str(d.get('description') or f"HTTP {e.code}")
        except Exception:
            return False, f"HTTP {e.code}"
    except Exception as e:
        text = str(getattr(e, 'reason', e)).replace(token, "***")
        return False, (f"No connection to Telegram ({text})" if en
                       else f"Keine Verbindung zu Telegram ({text})")
    if not d.get('ok'):
        return False, str(d.get('description') or ("Telegram rejected the message." if en
                                                   else "Telegram hat die Nachricht abgelehnt."))
    return True, d


def telegram_senden(token, chat, text, timeout=15, lang='de'):
    """Schickt eine Textnachricht. Rueckgabe wie telegram_anfrage()."""
    if not chat:
        return False, ("No chat ID entered." if lang == 'en' else "Keine Chat-ID eingetragen.")
    return telegram_anfrage(token, "sendMessage",
                            {'chat_id': chat, 'text': text[:4000],
                             'disable_web_page_preview': 'true'}, timeout, lang)


def telegram_chat_finden(token, lang='de'):
    """
    Liest die Chat-ID aus der letzten Nachricht, die an den Bot ging.
    Rueckgabe: (Chat-ID, Name) oder (None, Fehlertext).
    """
    ok, d = telegram_anfrage(token, "getUpdates", lang=lang)
    if not ok:
        return None, d
    for eintrag in reversed(d.get('result', [])):
        nachricht = eintrag.get('message') or eintrag.get('channel_post') or {}
        chat = nachricht.get('chat') or {}
        if 'id' in chat:
            name = chat.get('first_name') or chat.get('title') or chat.get('username') or ""
            return str(chat['id']), name
    if lang == 'en':
        return None, ("No message to the bot found yet. Please send the bot any "
                      "message in Telegram first.")
    return None, ("Noch keine Nachricht an den Bot gefunden. Bitte dem Bot in "
                  "Telegram zuerst eine beliebige Nachricht schicken.")


def telegram_bericht(erfolg, ordner, art, ablauf, meldung, restflackern=None, lang='de'):
    """Der Text der Benachrichtigung."""
    en = (lang == 'en')
    kopf = (("\u2705 Purelapse: finished" if en else "\u2705 Purelapse: fertig") if erfolg
            else ("\u274c Purelapse: error" if en else "\u274c Purelapse: Fehler"))
    zeilen = [kopf, ""]
    zeilen.append(("Folder: " if en else "Ordner: ") + (os.path.basename(ordner or "") or "-"))
    if art:
        zeilen.append(("Task: " if en else "Arbeitsgang: ") + art)
    if ablauf is not None:
        zeilen.append(("Time: " if en else "Zeit: ") + ablauf_kopf(ablauf, lang))
        erledigt = [s for s in ablauf.schritte if s['zustand'] in ('fertig', 'fehler')]
        for s_ in erledigt:
            zeichen = "\u2713" if s_['zustand'] == 'fertig' else "\u2715"
            zeilen.append(f"  {zeichen} {phase_titel(s_['key'], lang)}: "
                          f"{dauer_text(ablauf.dauer(s_))}")
    if restflackern:
        zeilen.append(("Residual flicker: " if en else "Restflackern: ") + restflackern)
    text = str(meldung or "").strip()
    if text:
        zeilen += ["", text[:1500]]
    return "\n".join(zeilen)


def workflow_stand(ordner, lang='de'):
    """
    Kurzbeschreibung eines Arbeitsordners fuer den Startdialog: wie viele
    Bilder, wie weit der Arbeitsgang ist, wann zuletzt daran gearbeitet
    wurde. Liest nur Dateinamen, keine Bilder - der Dialog soll sofort da
    sein.
    """
    en = (lang == 'en')
    try:
        namen = os.listdir(ordner)
    except OSError:
        return None
    raw = [n for n in namen if is_raw_file(n)]
    jpg = [n for n in namen if n.lower().endswith((".jpg", ".jpeg"))]
    teile = []
    if raw:
        teile.append(f"{len(raw)} RAW")
    if jpg:
        teile.append(f"{len(jpg)} JPG")
    if not teile:
        teile.append("no images" if en else "keine Bilder")
    schritte = []
    # Neue Ablage im Purelapse-Ordner, aeltere Ordner noch lose daneben
    try:
        im_pl = os.listdir(pl_ordner(ordner))
    except OSError:
        im_pl = []
    if (os.path.exists(pl_datei(ordner, DEFLICKER_DB))
            or os.path.exists(os.path.join(ordner, DEFLICKER_DB))):
        schritte.append("pass 1 done" if en else "Pass 1 erledigt")
    if (os.path.isdir(zwischen_ordner(ordner))
            or os.path.isdir(os.path.join(ordner, ZWISCHEN_ORDNER))):
        schritte.append("frames developed" if en else "Bilder entwickelt")
    videos = [n for n in namen + im_pl if ist_purelapse_video(n)]
    if videos:
        schritte.append((f"{len(videos)} video(s)" if en else f"{len(videos)} Video(s)"))
    try:
        zuletzt = max(os.path.getmtime(os.path.join(ordner, n)) for n in namen) if namen \
            else os.path.getmtime(ordner)
        wann = datetime.datetime.fromtimestamp(zuletzt).strftime("%d.%m.%Y %H:%M")
    except (OSError, ValueError):
        wann = ""
    zeile = " \u00b7 ".join(teile + schritte)
    if wann:
        zeile += (f"  \u00b7  last changed {wann}" if en else f"  \u00b7  zuletzt geaendert {wann}")
    return zeile


class StartDialog(QtWidgets.QDialog):
    """Beim Programmstart: den letzten Arbeitsgang fortsetzen oder neu beginnen."""

    def __init__(self, parent, letzter, lang='de'):
        super().__init__(parent)
        self.wahl = None            # 'weiter', 'neu' oder None
        de = (lang != 'en')
        t = (lambda a, b: a if de else b)
        self.setWindowTitle("Purelapse")
        self.setMinimumWidth(560)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 18)
        v.setSpacing(12)
        titel = QtWidgets.QLabel(t("Willkommen bei Purelapse", "Welcome to Purelapse"))
        titel.setObjectName("statustitel")
        v.addWidget(titel)
        if letzter:
            karte = QtWidgets.QFrame()
            karte.setObjectName("statuscard")
            vk = QtWidgets.QVBoxLayout(karte)
            vk.setContentsMargins(14, 12, 14, 12)
            vk.setSpacing(4)
            kopf = QtWidgets.QLabel(t("Letzter Arbeitsgang", "Last workflow"))
            kopf.setObjectName("hint")
            vk.addWidget(kopf)
            name = QtWidgets.QLabel(os.path.basename(letzter) or letzter)
            name.setStyleSheet("font-size: 14px; font-weight: bold;")
            vk.addWidget(name)
            pfad = QtWidgets.QLabel(letzter)
            pfad.setObjectName("hint")
            pfad.setWordWrap(True)
            vk.addWidget(pfad)
            stand = QtWidgets.QLabel(workflow_stand(letzter, lang) or "")
            stand.setWordWrap(True)
            vk.addWidget(stand)
            v.addWidget(karte)
        zeile = QtWidgets.QHBoxLayout()
        zeile.setSpacing(8)
        if letzter:
            self.btn_weiter = QtWidgets.QPushButton(t(" Letzten Arbeitsgang laden", " Load last workflow"))
            self.btn_weiter.setObjectName("primary")
            self.btn_weiter.clicked.connect(lambda _=False: self._waehle('weiter'))
            zeile.addWidget(self.btn_weiter, 2)
        self.btn_neu = QtWidgets.QPushButton(t(" Neuen Arbeitsgang beginnen\u2026", " Start new workflow\u2026"))
        if not letzter:
            self.btn_neu.setObjectName("primary")
        self.btn_neu.clicked.connect(lambda _=False: self._waehle('neu'))
        zeile.addWidget(self.btn_neu, 2)
        self.btn_leer = QtWidgets.QPushButton(t(" Ohne Ordner", " No folder"))
        self.btn_leer.clicked.connect(lambda _=False: self._waehle(None))
        zeile.addWidget(self.btn_leer, 1)
        v.addLayout(zeile)

    def _waehle(self, wahl):
        self.wahl = wahl
        self.accept()


class LadeSchirm(QtWidgets.QWidget):
    """
    Liegt waehrend des Einlesens ueber dem Hauptfenster: Ordner, Zaehler,
    Fortschritt. Die Oberflaeche darunter ist gesperrt, bis alle Bilder da
    sind - es sei denn, man laesst im Hintergrund weiterladen.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ladeschirm")
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        aussen = QtWidgets.QVBoxLayout(self)
        aussen.addStretch()
        zeile = QtWidgets.QHBoxLayout()
        zeile.addStretch()
        self.karte = QtWidgets.QFrame()
        self.karte.setObjectName("statuscard")
        self.karte.setFixedWidth(460)
        vk = QtWidgets.QVBoxLayout(self.karte)
        vk.setContentsMargins(22, 18, 22, 18)
        vk.setSpacing(10)
        self.lbl_titel = QtWidgets.QLabel("Bilder werden geladen \u2026")
        self.lbl_titel.setObjectName("statustitel")
        vk.addWidget(self.lbl_titel)
        self.lbl_ordner = QtWidgets.QLabel("")
        self.lbl_ordner.setObjectName("hint")
        self.lbl_ordner.setWordWrap(True)
        vk.addWidget(self.lbl_ordner)
        self.balken = QtWidgets.QProgressBar()
        self.balken.setTextVisible(False)
        self.balken.setRange(0, 0)          # laeuft, bis die Anzahl bekannt ist
        vk.addWidget(self.balken)
        self.lbl_stand = QtWidgets.QLabel("")
        vk.addWidget(self.lbl_stand)
        zeile.addWidget(self.karte)
        zeile.addStretch()
        aussen.addLayout(zeile)
        aussen.addStretch()
        self.hide()

    def zeige(self, ordner, lang='de'):
        self._lang = lang
        en = (lang == 'en')
        self.lbl_titel.setText("Loading images \u2026" if en else "Bilder werden geladen \u2026")
        self.lbl_ordner.setText(ordner)
        self.lbl_stand.setText("")
        self.balken.setRange(0, 0)
        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def stand(self, fertig, gesamt, text=""):
        if gesamt > 0:
            self.balken.setRange(0, gesamt)
            self.balken.setValue(fertig)
        if text:
            lang = getattr(self, '_lang', 'de')
            self.lbl_stand.setText(status_kurz(text, lang) if " | " in text
                                   else status_sprache(text, lang))


class Schleier(QtWidgets.QWidget):
    """Halbdurchsichtige Flaeche ueber dem Hauptfenster. Zeichnet sich
    selbst, damit sich die Deckkraft weich einblenden laesst."""

    def __init__(self, parent):
        super().__init__(parent)
        self.farbe = (0, 0, 0, 140)
        self.anteil = 1.0
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

    def paintEvent(self, event):
        r, g, b, a = self.farbe
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(r, g, b, int(round(a * self.anteil))))
        p.end()


class Abdunkler(QtCore.QObject):
    """
    Dunkelt das Hauptfenster ab, solange ein modales Fenster davor steht:
    Startdialog, Rueckfragen, Einstellungen, Keyframe-Dialog, Meldungen.
    Der Blick geht so zum Dialog, und man sieht sofort, dass das Fenster
    dahinter gerade nicht bedienbar ist.

    Ein Ereignisfilter der Anwendung zaehlt die sichtbaren modalen
    Fenster. Verschwindet das letzte, geht der Schleier wieder weg.
    Native Dateidialoge erscheinen nicht als Qt-Fenster - um sie herum
    haelt halten() den Schleier von Hand.
    """

    def __init__(self, fenster, schon_dunkel=None):
        super().__init__(fenster)
        self.fenster = fenster
        self._schon_dunkel = schon_dunkel or (lambda: False)
        self._offen = []
        self._halten = 0
        self.schleier = Schleier(fenster)
        self.schleier.setObjectName("abdunkler")
        self._einblenden = QtCore.QVariantAnimation(self)
        self._einblenden.setDuration(140)
        self._einblenden.setStartValue(0.0)
        self._einblenden.setEndValue(1.0)
        self._einblenden.valueChanged.connect(self._anteil_setzen)
        self.schleier.hide()

    def farbe_setzen(self, farbe):
        self.schleier.farbe = tuple(farbe)
        self.schleier.update()

    def _anteil_setzen(self, wert):
        try:
            self.schleier.anteil = max(0.0, min(1.0, float(wert)))
        except (TypeError, ValueError):
            self.schleier.anteil = 1.0
        self.schleier.update()

    def _ist_modal(self, w):
        if w is self.fenster or w is self.schleier or not isinstance(w, QtWidgets.QWidget):
            return False
        try:
            return bool(w.isWindow() and (w.isModal()
                                          or w.windowModality() != QtCore.Qt.NonModal))
        except RuntimeError:
            # Das Qt-Objekt ist schon abgebaut
            return False

    def eventFilter(self, obj, event):
        try:
            typ = event.type()
        except (AttributeError, RuntimeError):
            return False
        if typ == QtCore.QEvent.Show:
            if not any(o is obj for o in self._offen) and self._ist_modal(obj):
                self._offen.append(obj)
                self.aktualisieren()
        elif typ == QtCore.QEvent.Hide:
            if any(o is obj for o in self._offen):
                self._offen = [o for o in self._offen if o is not obj]
                self.aktualisieren()
        return False

    @contextlib.contextmanager
    def halten(self):
        """Schleier fuer die Dauer eines Blocks, etwa um einen nativen
        Dateidialog, den der Ereignisfilter nicht zu sehen bekommt."""
        self._halten += 1
        self.aktualisieren()
        try:
            yield
        finally:
            self._halten -= 1
            self.aktualisieren()

    def aktiv(self):
        return bool(self._offen or self._halten > 0)

    def aktualisieren(self):
        # Ueber dem Ladeschirm liegt schon ein Schleier - nicht doppelt.
        soll = self.aktiv() and self.fenster.isVisible() and not self._schon_dunkel()
        if soll:
            self.schleier.setGeometry(self.fenster.rect())
            self.schleier.raise_()
            if not self.schleier.isVisible():
                self.schleier.anteil = 0.0
                self.schleier.show()
                self._einblenden.start()
        elif self.schleier.isVisible():
            self._einblenden.stop()
            self.schleier.hide()


class MainWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Purelapse v{VERSION}")
        self.setMinimumSize(900, 560)
        self.resize(1150, 850)
        self.lang = get_lang()
        self.theme = get_theme()
        self._last_gaps = None
        self._last_clip = None
        self._busy = False
        self._sel_row = -1
        self._hl_werte = []
        self.last_output_dir = ""
        self.queue = load_queue()
        self.batch_running = False
        self.batch_index = -1
        self.worker = None
        self.gallery_worker = None
        self.target_dir = ""
        self.custom_out_dir = ""
        self.roi_rel = None
        self.cam_keyframes = None  # Speichert den 16:9 Start/End-Crop
        self._jpg_files = []
        self._nef_files = []
        self.luma_history = []
        self.frames_x = []
        self.tiles = []
        self._tile_last = 0
        self.curves = {'wb': [], 'clip': [], 'ev': [], 'interval': [], 'residual': [], 'sun': []}
        self._exif_times = []
        self.sun_marker = []
        self.sun_h_marker = []
        self._sun_crossings = []
        self.res_map = {0: (1280, "720p"), 1: (1920, "1080p"), 2: (2560, "1440p"), 3: (3840, "4K"), 4: (7680, "8K")}
        self.blur_options = [
            ("Aus (1 Bild)", 1, 1), ("3 Bilder", 3, 2), ("4 Bilder", 4, 2), ("5 Bilder", 5, 3),
            ("6 Bilder", 6, 3), ("7 Bilder", 7, 4), ("8 Bilder", 8, 4), ("9 Bilder", 9, 5),
            ("10 Bilder", 10, 5), ("12 Bilder", 12, 6), ("15 Bilder", 15, 7), ("18 Bilder", 18, 9),
            ("20 Bilder", 20, 10), ("25 Bilder", 25, 12)
        ]
        self._build_ui()
        self.lade_schirm = LadeSchirm(self)
        # Abdunkeln bei Dialogen; der Filter sitzt an der Anwendung, damit
        # er jedes modale Fenster sieht, auch QMessageBox und Dateidialoge.
        self.abdunkler = Abdunkler(self, lambda: self.lade_schirm.isVisible())
        self.abdunkler.farbe_setzen(THEMES[self.theme].get('schleier', (0, 0, 0, 140)))
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self.abdunkler)
        # Ob der letzte Ordner geladen wird, entscheidet der Startdialog
        # (_startauswahl), sobald das Fenster steht.

    def _startauswahl(self):
        """Beim Start fragen: letzten Arbeitsgang laden oder neu beginnen."""
        letzter = get_last_path()
        if not (letzter and os.path.isdir(letzter)):
            letzter = None
        dlg = StartDialog(self, letzter, self.lang)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        if dlg.wahl == 'weiter' and letzter:
            self._set_folder(letzter)
        elif dlg.wahl == 'neu':
            self._browse()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        schirm = getattr(self, 'lade_schirm', None)
        if schirm is not None and schirm.isVisible():
            schirm.setGeometry(self.rect())
        dunkel = getattr(self, 'abdunkler', None)
        if dunkel is not None and dunkel.schleier.isVisible():
            dunkel.schleier.setGeometry(self.rect())

    # Workflow-Schritte der Schrittleiste. 'load' und 'keys' sind reine
    # Hinweis-Seiten; 'smooth' und 'render' entsprechen bei RAW Pass 1 bzw.
    # Pass 2 (cmb_rawmode). Bei JPG entfaellt 'keys'.
    STEPS = ('load', 'smooth', 'keys', 'render')

    def _build_ui(self):
        self.step = 'load'
        self._kf_count = 0
        self._last_run = None
        self._auto_step = False
        # Ergebnis des Encoder-Selbsttests je Codec-Index: True/False.
        # Einmal pro Programmlauf getestet, damit die Warteschlange nicht
        # vor jedem Auftrag erneut FFmpeg startet.
        self._codec_probe = {}
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(6)

        # --------------------------------------------------------------
        # Zeitraffer-Ordner
        # --------------------------------------------------------------
        # Ohne Gruppentitel: das Pfadfeld sagt selbst, was es ist, und der
        # Titel kostete eine ganze Zeile Hoehe.
        box_folder = QtWidgets.QFrame()
        box_folder.setObjectName("statuscard")
        vf = QtWidgets.QVBoxLayout(box_folder)
        vf.setContentsMargins(10, 8, 10, 8)
        vf.setSpacing(6)
        row_folder = QtWidgets.QHBoxLayout()
        self.lbl_path = QtWidgets.QLineEdit()
        self.lbl_path.setReadOnly(True)
        self.lbl_path.setPlaceholderText("Bitte Zeitraffer-Ordner wählen…")
        row_folder.addWidget(self.lbl_path, stretch=5)
        # Symbolknoepfe: das Bild kommt aus dem Stylesheet (_ikon_regeln),
        # der Name steht im Hinweis beim Darueberfahren.
        def ikon_knopf(name, aktion):
            k = QtWidgets.QPushButton()
            k.setObjectName(name)
            k.setProperty("ikon", True)
            k.setCursor(QtCore.Qt.PointingHandCursor)
            k.clicked.connect(aktion)
            row_folder.addWidget(k)
            return k
        btn_browse = ikon_knopf("ikon_ordner", self._browse)
        btn_refresh = ikon_knopf("ikon_neu", self._refresh_preview)
        self.btn_reset = ikon_knopf("ikon_reset", self._open_reset_dialog)
        self.btn_settings = ikon_knopf("ikon_einst", self._open_settings)
        vf.addLayout(row_folder)
        self.btn_browse = btn_browse
        self.btn_refresh = btn_refresh
        row_info = QtWidgets.QHBoxLayout()
        self.lbl_count = QtWidgets.QLabel("Kein Ordner gewählt.")
        row_info.addWidget(self.lbl_count)
        self.lbl_gaps = QtWidgets.QLabel()
        self.lbl_gaps.setVisible(False)
        row_info.addWidget(self.lbl_gaps)
        self.lbl_clip = QtWidgets.QLabel()
        self.lbl_clip.setVisible(False)
        row_info.addWidget(self.lbl_clip)
        self.lbl_farbstich = QtWidgets.QLabel()
        self.lbl_farbstich.setVisible(False)
        row_info.addWidget(self.lbl_farbstich)
        row_info.addStretch()
        # Die eingestellte Engine steht immer sichtbar rechts in der
        # Infozeile - vorher nur in den Einstellungen und in der
        # Zusammenfassung ueber den Knoepfen. Ein Klick oeffnet die
        # Einstellungen.
        self.btn_engine = QtWidgets.QPushButton()
        self.btn_engine.setObjectName("enginechip")
        self.btn_engine.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_engine.clicked.connect(self._open_settings)
        row_info.addWidget(self.btn_engine)
        vf.addLayout(row_info)
        main_layout.addWidget(box_folder)

        # --------------------------------------------------------------
        # Schrittleiste: zeigt den Arbeitsablauf und schaltet die Seiten um
        # --------------------------------------------------------------
        row_steps = QtWidgets.QHBoxLayout()
        row_steps.setSpacing(4)
        self.step_group = QtWidgets.QButtonGroup(self)
        self.step_group.setExclusive(True)
        self.step_buttons = {}
        self.step_arrows = {}
        for i, key in enumerate(self.STEPS):
            if i:
                pfeil = QtWidgets.QLabel("›")
                pfeil.setObjectName("steparrow")
                row_steps.addWidget(pfeil)
                self.step_arrows[key] = pfeil
            b = QtWidgets.QPushButton()
            b.setObjectName("step")
            b.setProperty("schritt", key)     # fuer die Farbe je Schritt
            b.setCheckable(True)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self._go_step(k))
            self.step_group.addButton(b)
            row_steps.addWidget(b, stretch=1)
            self.step_buttons[key] = b
        main_layout.addLayout(row_steps)
        # Durchgehender Streifen in der Farbe des aktiven Schritts.
        self.step_line = QtWidgets.QFrame()
        self.step_line.setObjectName("stepline")
        self.step_line.setFixedHeight(3)
        main_layout.addWidget(self.step_line)

        # SPLITTER (Galerie links, Kurve + Schritt-Seite rechts)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setViewMode(QtWidgets.QListView.IconMode)
        self.list_widget.setResizeMode(QtWidgets.QListView.Adjust)
        self.list_widget.setMovement(QtWidgets.QListView.Static)
        self.list_widget.setSpacing(4)
        self.list_widget.viewport().installEventFilter(self)
        self.list_widget.currentRowChanged.connect(self._on_tile_selected)
        self._tile_timer = QtCore.QTimer(self)
        self._tile_timer.setSingleShot(True)
        self._tile_timer.timeout.connect(self._relayout_gallery)
        self.list_widget.setMinimumWidth(160)
        # Bildleiste bekommt eine eigene Knopfzeile; der Splitter nimmt
        # deshalb den Behaelter statt der Liste selbst.
        left_container = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        row_gal = QtWidgets.QHBoxLayout()
        row_gal.setSpacing(4)
        self.btn_kf_filter = QtWidgets.QPushButton("★ nur Keyframes")
        self.btn_kf_filter.setCheckable(True)
        self.btn_kf_filter.toggled.connect(self._on_filter_keyframes)
        row_gal.addWidget(self.btn_kf_filter)
        self.btn_kf_edit = QtWidgets.QPushButton("Keyframe einstellen…")
        self.btn_kf_edit.clicked.connect(self._open_quick_dialog)
        self.btn_kf_edit.setEnabled(False)
        row_gal.addWidget(self.btn_kf_edit)
        self.btn_erstes = QtWidgets.QPushButton("\u23ee")
        self.btn_letztes = QtWidgets.QPushButton("\u23ed")
        for knopf, ziel in ((self.btn_erstes, 0), (self.btn_letztes, -1)):
            knopf.setObjectName("mini")
            knopf.setFixedWidth(34)
            knopf.clicked.connect(lambda _=False, z=ziel: self._springe_zu(z))
            row_gal.addWidget(knopf)
        left_layout.addLayout(row_gal)
        # Startbild / Endbild: grenzt den Arbeitsgang auf einen Teil der
        # Bilder ein.
        row_ber = QtWidgets.QHBoxLayout()
        row_ber.setSpacing(4)
        self.btn_start_hier = QtWidgets.QPushButton("\u21e4 Startbild")
        self.btn_start_hier.clicked.connect(lambda _=False: self._setze_bereich('start'))
        row_ber.addWidget(self.btn_start_hier)
        self.btn_ende_hier = QtWidgets.QPushButton("Endbild \u21e5")
        self.btn_ende_hier.clicked.connect(lambda _=False: self._setze_bereich('ende'))
        row_ber.addWidget(self.btn_ende_hier)
        left_layout.addLayout(row_ber)
        self.lbl_bereich = QtWidgets.QLabel("")
        self.lbl_bereich.setObjectName("hint")
        self.lbl_bereich.setVisible(False)
        left_layout.addWidget(self.lbl_bereich)
        self._bereich = (None, None)
        left_layout.addWidget(self.list_widget)
        self.splitter.addWidget(left_container)
        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.graph = pg.PlotWidget(title='<span style="color: #ffaa00;">Live-Deflicker-Graph ● (Warte auf Ordner)</span>')
        self.graph.showGrid(x=True, y=True, alpha=0.3)
        # Ohne Rand liegt eine Marke bei Bild 0 genau auf der Achse und
        # wird von ihr verdeckt.
        try:
            self.graph.getViewBox().setDefaultPadding(0.02)
        except (AttributeError, TypeError):
            pass
        self.graph.setMaximumHeight(190)
        self.graph.setMinimumHeight(100)
        self.plot_raw = self.graph.plot(pen=stift('#555', 2), symbol='o',
                                        symbolSize=6, symbolBrush='#777',
                                        name="Original")
        self.plot_raw.sigPointsClicked.connect(self._on_graph_clicked)
        self.plot_smooth = self.graph.plot(pen=stift('#ffaa00', 3),
                                           name="Zielkurve")
        # Bei langen Sequenzen nur noch jeden sichtbaren Pixel zeichnen.
        # 'peak' behaelt dabei die Ausschlaege - ein einzelner Ausreisser
        # darf beim Ausduennen nicht verschwinden, der ist ja der
        # interessante Teil.
        for kurve in (self.plot_raw, self.plot_smooth):
            try:
                kurve.setDownsampling(auto=True, method='peak')
                kurve.setClipToView(True)
            except (AttributeError, TypeError):
                pass
        self.plot_wb = None
        self.extra_plots = {}
        try:
            p1 = self.graph.plotItem
            self.vb_wb = pg.ViewBox()
            p1.showAxis('right')
            p1.scene().addItem(self.vb_wb)
            p1.getAxis('right').linkToView(self.vb_wb)
            p1.getAxis('right').setLabel('EV / Anteil', color='#aaaaaa')
            self.vb_wb.setXLink(p1)
            self.plot_wb = pg.PlotCurveItem(pen=stift('#00d0ff', 2))
            self.vb_wb.addItem(self.plot_wb)
            for name in ('ev', 'interval', 'clip', 'residual', 'sun'):
                k = pg.PlotCurveItem(pen=stift('#888888', 2))
                self.vb_wb.addItem(k)
                self.extra_plots[name] = k
            self.extra_plots['wb'] = self.plot_wb

            def _sync_wb():
                self.vb_wb.setGeometry(p1.vb.sceneBoundingRect())
                self.vb_wb.linkedViewChanged(p1.vb, self.vb_wb.XAxis)
            p1.vb.sigResized.connect(_sync_wb)
            _sync_wb()
        except Exception:
            self.plot_wb = None
            self.vb_wb = None
        self.kf_marker = []
        # Senkrechte Linie am in der Bildleiste gewaehlten Bild
        self.sel_marker = pg.InfiniteLine(pos=0, angle=90, pen=stift('#4a9eff', 2))
        self.sel_marker.setZValue(5)
        self.sel_marker.setVisible(False)
        self.graph.addItem(self.sel_marker)
        # Aufgehellter Streifen ueber den Bildern, die links in der
        # Bildleiste gerade zu sehen sind. Er wandert beim Rollen mit.
        self.sicht_band = None
        try:
            self.sicht_band = pg.LinearRegionItem(values=(0, 1), movable=False)
            self.sicht_band.setZValue(-20)        # hinter allen Kurven
            self.sicht_band.setVisible(False)
            # ignoreBounds: der Streifen darf die Achsen nicht verschieben
            self.graph.addItem(self.sicht_band, ignoreBounds=True)
        except Exception:
            self.sicht_band = None
        self._band_timer = QtCore.QTimer(self)
        self._band_timer.setSingleShot(True)
        self._band_timer.setInterval(30)
        self._band_timer.timeout.connect(self._update_sicht_band)
        try:
            self.list_widget.verticalScrollBar().valueChanged.connect(
                self._gallerie_einrasten)
            self.list_widget.verticalScrollBar().valueChanged.connect(
                lambda _v=0: self._band_timer.start())
        except Exception:
            pass
        # Klick irgendwo ins Diagramm waehlt das Bild an dieser Stelle.
        # Bisher hing das an den Punktsymbolen der Messkurve - und die
        # gibt es bei langen Sequenzen nicht mehr.
        try:
            self.graph.scene().sigMouseClicked.connect(self._on_graph_scene_clicked)
        except Exception:
            pass
        right_layout.addWidget(self.graph)
        row_curves = QtWidgets.QHBoxLayout()
        row_curves.setContentsMargins(4, 0, 4, 0)
        # Legende der drei festen Kurven; Farben setzt _apply_theme()
        self.lbl_legend = QtWidgets.QLabel()
        self.lbl_legend.setTextFormat(QtCore.Qt.RichText)
        row_curves.addWidget(self.lbl_legend)
        row_curves.addSpacing(14)
        self.lbl_more_curves = QtWidgets.QLabel("Weitere Kurven:")
        self.lbl_more_curves.setObjectName("hint")
        row_curves.addWidget(self.lbl_more_curves)
        self.curve_toggles = {}
        for name, text, an in (('wb', "Weißabgleich", True),
                               ('ev', "Belichtung (EXIF)", False),
                               ('interval', "Intervall", False),
                               ('clip', "Clipping", False),
                               ('residual', "Restflackern", False),
                               ('sun', "Sonnenstand", False)):
            cb = QtWidgets.QCheckBox(text)
            cb.setChecked(an)
            cb.toggled.connect(self._draw_extra_curves)
            row_curves.addWidget(cb)
            self.curve_toggles[name] = cb
        row_curves.addStretch()
        right_layout.addLayout(row_curves)

        # Eine Seite je Workflow-Schritt
        self.pages = QtWidgets.QStackedWidget()
        self.step_hints = {}

        def _seite(key):
            host = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(host)
            lay.setContentsMargins(6, 6, 6, 6)
            hinweis = QtWidgets.QLabel()
            hinweis.setObjectName("hint")
            hinweis.setWordWrap(True)
            lay.addWidget(hinweis)
            self.step_hints[key] = hinweis
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
            scroll.setWidget(host)
            self.pages.addWidget(scroll)
            return lay

        load_col = _seite('load')
        smooth_col = _seite('smooth')
        keys_col = _seite('keys')
        render_col = _seite('render')

        # --------------------------------------------------------------
        # Schritt "Bilder laden": Format und Aufnahmeort
        # --------------------------------------------------------------
        box_fmt = QtWidgets.QGroupBox("Format")
        gf = QtWidgets.QGridLayout(box_fmt)
        self.rb_jpg = QtWidgets.QRadioButton("JPG (Direkt-Workflow)")
        self.rb_raw = QtWidgets.QRadioButton("NEF / RAW (RAW-Workflow)")
        self.rb_jpg.setChecked(True)
        self.rb_jpg.toggled.connect(self._on_format_changed)
        gf.addWidget(self.rb_jpg, 0, 0, 1, 2)
        gf.addWidget(self.rb_raw, 1, 0, 1, 2)
        load_col.addWidget(box_fmt)
        # Pass 1 / Pass 2 waehlt jetzt die Schrittleiste. Die Auswahlliste
        # bleibt unsichtbar bestehen, weil Einstellungen, Warteschlange und
        # _collect_params() weiterhin ihren Index lesen.
        self.cmb_rawmode = QtWidgets.QComboBox(self)
        self.cmb_rawmode.addItems(["Pass 1 – Anti-Flacker", "Pass 2 – Rendern"])
        self.cmb_rawmode.currentIndexChanged.connect(self._update_visibility)
        self.cmb_rawmode.hide()

        self.box_sun = QtWidgets.QGroupBox("Aufnahmeort für die Sonnenstand-Kurve (optional)")
        gs = QtWidgets.QGridLayout(self.box_sun)
        gs.addWidget(QtWidgets.QLabel("Breitengrad:"), 0, 0)
        self.txt_lat = QtWidgets.QLineEdit()
        self.txt_lat.setPlaceholderText("52.5")
        self.txt_lat.setMaximumWidth(140)
        gs.addWidget(self.txt_lat, 0, 1)
        gs.addWidget(QtWidgets.QLabel("Längengrad:"), 0, 2)
        self.txt_lon = QtWidgets.QLineEdit()
        self.txt_lon.setPlaceholderText("13.4")
        self.txt_lon.setMaximumWidth(140)
        gs.addWidget(self.txt_lon, 0, 3)
        gs.addWidget(QtWidgets.QLabel("Zeitzone (UTC+):"), 0, 4)
        self.txt_utc = QtWidgets.QLineEdit("0")
        self.txt_utc.setPlaceholderText("2")
        self.txt_utc.setMaximumWidth(70)
        gs.addWidget(self.txt_utc, 0, 5)
        self.btn_gps_from_exif = QtWidgets.QPushButton("GPS aus Bild")
        self.btn_gps_from_exif.clicked.connect(lambda: self._gps_from_exif())
        gs.addWidget(self.btn_gps_from_exif, 0, 6)
        gs.setColumnStretch(7, 1)
        for w in (self.txt_lat, self.txt_lon, self.txt_utc):
            w.editingFinished.connect(self._recompute_sun_curve)
        load_col.addWidget(self.box_sun)
        load_col.addStretch()

        # --------------------------------------------------------------
        # Schritt "Helligkeit glaetten": Deflicker
        # --------------------------------------------------------------
        self.box_deflicker = QtWidgets.QGroupBox("Helligkeit und Deflicker")
        gd = QtWidgets.QGridLayout(self.box_deflicker)
        gd.addWidget(QtWidgets.QLabel("Lichtverlauf:"), 0, 0)
        self.cmb_scene = QtWidgets.QComboBox()
        self.cmb_scene.addItems(["Sonnenaufgang (heller werdend)", "Sonnenuntergang (dunkler werdend)", "Gleichbleibend"])
        self.cmb_scene.setCurrentIndex(2)
        self.cmb_scene.currentIndexChanged.connect(self._redraw_graph)
        gd.addWidget(self.cmb_scene, 0, 1, 1, 2)
        gd.addWidget(QtWidgets.QLabel("Deflicker-Stärke:"), 1, 0)
        self.slider_smooth = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_smooth.setRange(1, 100)
        self.slider_smooth.setValue(50)
        self.lbl_smooth_val = QtWidgets.QLabel("50%")
        self.lbl_smooth_val.setMinimumWidth(150)
        self.slider_smooth.valueChanged.connect(self._on_smooth_changed)
        gd.addWidget(self.slider_smooth, 1, 1)
        gd.addWidget(self.lbl_smooth_val, 1, 2)
        gd.addWidget(QtWidgets.QLabel("Belichtung (EV):"), 2, 0)
        self.slider_ev = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_ev.setRange(-30, 30)
        self.slider_ev.setValue(0)
        self.lbl_ev_val = QtWidgets.QLabel("0.0 EV")
        self.slider_ev.valueChanged.connect(self._on_ev_changed)
        gd.addWidget(self.slider_ev, 2, 1)
        gd.addWidget(self.lbl_ev_val, 2, 2)
        self.btn_roi = QtWidgets.QPushButton(" [+] Messbereich (ROI) festlegen")
        self.btn_roi.clicked.connect(self._select_roi)
        gd.addWidget(self.btn_roi, 3, 0, 1, 3)
        smooth_col.addWidget(self.box_deflicker)
        smooth_col.addStretch()

        # --------------------------------------------------------------
        # Schritt "Keyframes bearbeiten" (nur RAW): Hinweis und Zaehler
        # --------------------------------------------------------------
        self.box_keys = QtWidgets.QGroupBox("Keyframes")
        gk = QtWidgets.QVBoxLayout(self.box_keys)
        self.lbl_keys_status = QtWidgets.QLabel()
        self.lbl_keys_status.setWordWrap(True)
        gk.addWidget(self.lbl_keys_status)
        row_keys = QtWidgets.QHBoxLayout()
        self.btn_keys_refresh = QtWidgets.QPushButton(" Bilder neu einlesen")
        self.btn_keys_refresh.clicked.connect(self._refresh_preview)
        row_keys.addWidget(self.btn_keys_refresh)
        row_keys.addStretch()
        gk.addLayout(row_keys)
        keys_col.addWidget(self.box_keys)
        keys_col.addStretch()

        # --------------------------------------------------------------
        # Schritt "Video rendern": Video, Bild und Effekte, Speicherort
        # --------------------------------------------------------------
        row_out = QtWidgets.QHBoxLayout()
        self.box_video = QtWidgets.QGroupBox("Video")
        gv = QtWidgets.QGridLayout(self.box_video)
        self.chk_video = QtWidgets.QCheckBox("Video erstellen")
        self.chk_video.setChecked(True)
        self.chk_video.toggled.connect(self._update_visibility)
        gv.addWidget(self.chk_video, 0, 0, 1, 2)
        gv.addWidget(QtWidgets.QLabel("Framerate (fps):"), 1, 0)
        self.cmb_fps = QtWidgets.QComboBox()
        self.cmb_fps.addItems(["23.976", "24", "25", "29.97", "30", "50", "59.94", "60", "120"])
        self.cmb_fps.setCurrentText("25")
        self.cmb_fps.currentIndexChanged.connect(self._update_filesize_estimate)
        gv.addWidget(self.cmb_fps, 1, 1)
        gv.addWidget(QtWidgets.QLabel("16:9-Auflösung:"), 2, 0)
        self.cmb_res = QtWidgets.QComboBox()
        self.cmb_res.addItems(["720p (HD Ready)", "1080p (FHD)", "1440p (2.5K)", "2160p (4K)", "4320p (8K)"])
        self.cmb_res.setCurrentIndex(3)
        self.cmb_res.currentIndexChanged.connect(self._update_filesize_estimate)
        gv.addWidget(self.cmb_res, 2, 1)
        gv.addWidget(QtWidgets.QLabel("Video-Codec:"), 3, 0)
        self.cmb_codec = QtWidgets.QComboBox()
        self.cmb_codec.addItems([c['label'] for c in VIDEO_CODECS])
        self.cmb_codec.currentIndexChanged.connect(self._update_filesize_estimate)
        self.cmb_codec.currentIndexChanged.connect(self._on_codec_changed)
        gv.addWidget(self.cmb_codec, 3, 1)
        gv.addWidget(QtWidgets.QLabel("Render-Qualität:"), 4, 0)
        self.cmb_quality = QtWidgets.QComboBox()
        self.cmb_quality.addItems(["Visuell Verlustfrei (CRF 16)", "Hoch (CRF 20)", "Standard (CRF 23)", "Niedrig (CRF 28)"])
        self.cmb_quality.setCurrentIndex(1)
        self.cmb_quality.currentIndexChanged.connect(self._update_filesize_estimate)
        gv.addWidget(self.cmb_quality, 4, 1)
        gv.addWidget(QtWidgets.QLabel("Ein-/Ausblenden:"), 5, 0)
        self.cmb_fade = QtWidgets.QComboBox()
        self.cmb_fade.addItems(["Aus", "0,5 Sekunden", "1 Sekunde", "2 Sekunden", "3 Sekunden"])
        gv.addWidget(self.cmb_fade, 5, 1)
        self.lbl_size_est = QtWidgets.QLabel("Geschätzte Dateigröße: -- MB")
        gv.addWidget(self.lbl_size_est, 6, 0, 1, 2)
        gv.setRowStretch(7, 1)
        # Beide Gruppen dieser Zeile im selben Raster: Beschriftung links
        # in fester Breite, das Bedienelement fuellt den Rest.
        for gitter in (gv,):
            gitter.setColumnMinimumWidth(0, 130)
            gitter.setColumnStretch(1, 1)
            gitter.setHorizontalSpacing(12)
            gitter.setVerticalSpacing(8)
        row_out.addWidget(self.box_video, stretch=1)
        self.box_effects = QtWidgets.QGroupBox("Bild und Effekte")
        ge = QtWidgets.QGridLayout(self.box_effects)
        ge.setColumnMinimumWidth(0, 130)
        ge.setColumnStretch(1, 1)
        ge.setHorizontalSpacing(12)
        ge.setVerticalSpacing(8)
        # Oben die beiden Einstellungen mit Beschriftung, wie in der
        # Gruppe "Video" daneben ...
        ge.addWidget(QtWidgets.QLabel("Motion Blur:"), 0, 0)
        self.cmb_blur = QtWidgets.QComboBox()
        self.cmb_blur.addItems([b[0] for b in self.blur_options])
        ge.addWidget(self.cmb_blur, 0, 1)
        ge.addWidget(QtWidgets.QLabel("Bildausschnitt:"), 1, 0)
        zeile_cam = QtWidgets.QHBoxLayout()
        zeile_cam.setSpacing(10)
        self.btn_cam_path = QtWidgets.QPushButton(" 16:9 Kamerafahrt / Crop \u2026")
        self.btn_cam_path.clicked.connect(self._open_camera_path_dialog)
        zeile_cam.addWidget(self.btn_cam_path, 1)
        # Der Zustand als kleines Schild neben dem Knopf statt als lose
        # farbige Schrift.
        self.lbl_cam_status = QtWidgets.QLabel("Standard (Mitte)")
        self.lbl_cam_status.setObjectName("badge")
        self.lbl_cam_status.setFixedHeight(20)
        zeile_cam.addWidget(self.lbl_cam_status, 0, QtCore.Qt.AlignVCenter)
        ge.addLayout(zeile_cam, 1, 1)
        trenner = QtWidgets.QFrame()
        trenner.setObjectName("trenner")
        ge.addWidget(trenner, 2, 0, 1, 2)
        # ... darunter die Schalter in zwei gleich breiten Spalten. Links,
        # was das Bild veraendert, rechts, was den Ablauf betrifft.
        # "Denoise" gibt es nur fuer JPG und steht deshalb zuletzt: ist es
        # ausgeblendet, bleibt keine Luecke.
        g_schalter = QtWidgets.QGridLayout()
        g_schalter.setHorizontalSpacing(12)
        g_schalter.setVerticalSpacing(8)
        g_schalter.setColumnStretch(0, 1)
        g_schalter.setColumnStretch(1, 1)
        self.chk_stab = QtWidgets.QCheckBox("Optische Stabilisierung")
        g_schalter.addWidget(self.chk_stab, 0, 0)
        self.chk_reverse = QtWidgets.QCheckBox("Rückwärts rendern")
        g_schalter.addWidget(self.chk_reverse, 0, 1)
        self.chk_hotpix = QtWidgets.QCheckBox("Tote / heiße Pixel entfernen")
        g_schalter.addWidget(self.chk_hotpix, 1, 0)
        self.chk_astro = QtWidgets.QCheckBox("Astro-Clean (Satelliten entfernen)")
        g_schalter.addWidget(self.chk_astro, 1, 1)
        self.chk_tel = QtWidgets.QCheckBox("Telemetrie-Overlay")
        g_schalter.addWidget(self.chk_tel, 2, 0)
        self.chk_denoise = QtWidgets.QCheckBox("Denoise")
        self.chk_denoise.setChecked(True)
        g_schalter.addWidget(self.chk_denoise, 2, 1)
        ge.addLayout(g_schalter, 3, 0, 1, 2)
        ge.setRowStretch(4, 1)
        self.spalte_rechts = QtWidgets.QVBoxLayout()
        self.spalte_rechts.setSpacing(row_out.spacing() if row_out.spacing() >= 0 else 6)
        self.spalte_rechts.addWidget(self.box_effects, stretch=1)
        row_out.addLayout(self.spalte_rechts, stretch=1)
        render_col.addLayout(row_out)

        self.box_export = QtWidgets.QGroupBox("Speicherort und Dateinamen")
        gexp = QtWidgets.QGridLayout(self.box_export)
        gexp.addWidget(QtWidgets.QLabel("Speichern in:"), 0, 0)
        self.cmb_export_dir = QtWidgets.QComboBox()
        self.cmb_export_dir.addItems(["1. Purelapse-Ordner im Bilderordner (empfohlen)", "2. Übergeordneter Ordner", "3. Programmverzeichnis (purelapse)", "4. Eigener Ordner wählen..."])
        self.cmb_export_dir.currentIndexChanged.connect(self._on_export_dir_changed)
        gexp.addWidget(self.cmb_export_dir, 0, 1)
        self.btn_custom_dir = QtWidgets.QPushButton("...")
        self.btn_custom_dir.setVisible(False)
        self.btn_custom_dir.setMaximumWidth(40)
        self.btn_custom_dir.clicked.connect(self._choose_custom_dir)
        gexp.addWidget(self.btn_custom_dir, 0, 2)
        gexp.addWidget(QtWidgets.QLabel("Wenn Datei existiert:"), 1, 0)
        self.cmb_versioning = QtWidgets.QComboBox()
        self.cmb_versioning.addItems(["Neue Version anlegen (_v1, _v2)", "Datei überschreiben"])
        gexp.addWidget(self.cmb_versioning, 1, 1, 1, 2)
        gexp.setColumnMinimumWidth(0, 130)
        gexp.setColumnStretch(1, 1)
        gexp.setHorizontalSpacing(12)
        gexp.setVerticalSpacing(8)
        # Rechte Spalte: "Bild und Effekte" ist kuerzer als "Video"
        # daneben; der Speicherort fuellt die Luecke darunter. Bisher stand
        # er in einer eigenen Zeile, und auf einem Bildschirm mit 1080
        # Zeilen musste man zum Ende der Seite rollen.
        self.spalte_rechts.addWidget(self.box_export)
        render_col.addStretch()

        right_layout.addWidget(self.pages)
        self.splitter.addWidget(right_container)
        self.splitter.setSizes([250, 900])
        main_layout.addWidget(self.splitter)

        # --------------------------------------------------------------
        # Einstellungen (eigenes Fenster): Darstellung, Engine und Leistung
        # --------------------------------------------------------------
        self.dlg_settings = QtWidgets.QDialog(self)
        self.dlg_settings.setMinimumWidth(620)
        vset = QtWidgets.QVBoxLayout(self.dlg_settings)
        self.box_look = QtWidgets.QGroupBox("Darstellung")
        gl = QtWidgets.QGridLayout(self.box_look)
        self.lbl_theme = QtWidgets.QLabel("Design:")
        gl.addWidget(self.lbl_theme, 0, 0)
        self.cmb_theme = QtWidgets.QComboBox()
        self.cmb_theme.addItems(["Dunkel", "Hell"])
        self.cmb_theme.currentIndexChanged.connect(self._on_theme_changed)
        gl.addWidget(self.cmb_theme, 0, 1)
        self.lbl_lang = QtWidgets.QLabel("Sprache:")
        gl.addWidget(self.lbl_lang, 0, 2)
        self.cmb_lang = QtWidgets.QComboBox()
        self.cmb_lang.addItems(["Deutsch", "English"])
        self.cmb_lang.currentIndexChanged.connect(self._on_lang_changed)
        gl.addWidget(self.cmb_lang, 0, 3)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(3, 1)
        vset.addWidget(self.box_look)

        self.box_perf = QtWidgets.QGroupBox("Engine und Leistung")
        gperf = QtWidgets.QGridLayout(self.box_perf)
        gperf.addWidget(QtWidgets.QLabel("Entwicklungs-Engine:"), 0, 0)
        self.cmb_engine = QtWidgets.QComboBox()
        # Reihenfolge = 'art', 'rt', 'dt' - siehe _on_engine_changed() und
        # _collect_params() (Block 7).
        self.cmb_engine.addItems([ENGINES['art']['label'],
                                  ENGINES['rt']['label'],
                                  ENGINES['dt']['label']])
        self.cmb_engine.currentIndexChanged.connect(self._on_engine_changed)
        gperf.addWidget(self.cmb_engine, 0, 1, 1, 2)
        self.lbl_art_path = QtWidgets.QLabel("ART-Programm:")
        gperf.addWidget(self.lbl_art_path, 1, 0)
        self.txt_art_path = QtWidgets.QLineEdit()
        self.txt_art_path.setReadOnly(True)
        self.txt_art_path.setText(get_art_path())
        gperf.addWidget(self.txt_art_path, 1, 1)
        self.btn_art_browse = QtWidgets.QPushButton("...")
        self.btn_art_browse.setMaximumWidth(40)
        self.btn_art_browse.clicked.connect(self._browse_art_cli)
        gperf.addWidget(self.btn_art_browse, 1, 2)
        # Basisprofil-Zeile - bei Darktable nicht relevant, wird von
        # _on_engine_changed() ein-/ausgeblendet (siehe Block 7).
        self.lbl_arp_tpl = QtWidgets.QLabel("ART-Basisprofil:")
        gperf.addWidget(self.lbl_arp_tpl, 2, 0)
        self.txt_arp_template = QtWidgets.QLineEdit()
        self.txt_arp_template.setReadOnly(True)
        self.txt_arp_template.setText(get_arp_template_path())
        self.txt_arp_template.setPlaceholderText("wird im Bilderordner gesucht")
        gperf.addWidget(self.txt_arp_template, 2, 1)
        self.btn_arp_browse = QtWidgets.QPushButton("...")
        self.btn_arp_browse.setMaximumWidth(40)
        self.btn_arp_browse.clicked.connect(self._browse_arp_template)
        gperf.addWidget(self.btn_arp_browse, 2, 2)
        # Hinweiszeile, die nur bei Darktable sichtbar ist.
        self.lbl_dt_note = QtWidgets.QLabel(
            "Darktable braucht kein Basisprofil: Purelapse arbeitet mit den "
            "vorhandenen .xmp-Dateien. Es schreibt die Belichtung und überträgt "
            "die Module der Keyframes in die Bilder dazwischen.")
        self.lbl_dt_note.setWordWrap(True)
        self.lbl_dt_note.setVisible(False)
        gperf.addWidget(self.lbl_dt_note, 2, 0, 1, 3)
        gperf.addWidget(QtWidgets.QLabel("Nachkalibrierung:"), 3, 0)
        self.cmb_calib = QtWidgets.QComboBox()
        self.cmb_calib.addItems(["Aus (1 Lauf)", "1 Durchgang (2 Läufe)",
                                 "2 Durchgänge (3 Läufe)", "3 Durchgänge (4 Läufe)"])
        self.cmb_calib.setCurrentIndex(2)
        self.cmb_calib.setToolTip(
            "Purelapse misst nach dem Entwickeln das Ergebnis und schreibt die\n"
            "verbleibende Abweichung in die Sidecars zurück, dann wird erneut entwickelt.\n"
            "Das gleicht Unterschiede zwischen der Analyse und dem Rendering aus.\n"
            "Wird abgebrochen, sobald das Restflackern unter 0.008 EV liegt.")
        gperf.addWidget(self.cmb_calib, 3, 1, 1, 2)
        gperf.addWidget(QtWidgets.QLabel("CPU-Kerne:"), 4, 0)
        self.cmb_cores = QtWidgets.QComboBox()
        max_cores = multiprocessing.cpu_count()
        for i in range(1, max_cores + 1):
            self.cmb_cores.addItem(f"{i} Kern{'e' if i>1 else ''}")
        self.cmb_cores.setCurrentIndex(max(0, max_cores - 2))
        gperf.addWidget(self.cmb_cores, 4, 1, 1, 2)
        gperf.addWidget(QtWidgets.QLabel("Parallele Prozesse:"), 5, 0)
        self.cmb_procs = QtWidgets.QComboBox()
        self.cmb_procs.addItems(["Automatisch", "1 (seriell)", "2", "3",
                                 "4", "6", "8"])
        gperf.addWidget(self.cmb_procs, 5, 1, 1, 2)
        self.chk_diag = QtWidgets.QCheckBox("Diagnose-Modus (Protokolldateien schreiben)")
        gperf.addWidget(self.chk_diag, 6, 0, 1, 3)
        self.chk_tiff16 = QtWidgets.QCheckBox(
            "16-Bit-Zwischenbilder (TIFF) für höchste Qualität")
        gperf.addWidget(self.chk_tiff16, 7, 0, 1, 3)
        vset.addWidget(self.box_perf)
        self.box_telegram = QtWidgets.QGroupBox("Benachrichtigung (Telegram)")
        gtg = QtWidgets.QGridLayout(self.box_telegram)
        gtg.setColumnStretch(1, 1)
        self.chk_telegram = QtWidgets.QCheckBox(
            "Nach jedem Lauf eine Nachricht schicken (fertig oder Fehler)")
        gtg.addWidget(self.chk_telegram, 0, 0, 1, 3)
        gtg.addWidget(QtWidgets.QLabel("Bot-Token:"), 1, 0)
        self.txt_tg_token = QtWidgets.QLineEdit()
        self.txt_tg_token.setEchoMode(QtWidgets.QLineEdit.Password)
        self.txt_tg_token.setPlaceholderText("123456789:ABC…  (von @BotFather)")
        gtg.addWidget(self.txt_tg_token, 1, 1, 1, 2)
        gtg.addWidget(QtWidgets.QLabel("Chat-ID:"), 2, 0)
        self.txt_tg_chat = QtWidgets.QLineEdit()
        self.txt_tg_chat.setPlaceholderText("wird mit \u201eChat-ID ermitteln\u201c eingetragen")
        gtg.addWidget(self.txt_tg_chat, 2, 1)
        self.btn_tg_chat = QtWidgets.QPushButton(" Chat-ID ermitteln")
        self.btn_tg_chat.clicked.connect(self._telegram_chat_ermitteln)
        gtg.addWidget(self.btn_tg_chat, 2, 2)
        self.btn_tg_test = QtWidgets.QPushButton(" Testnachricht senden")
        self.btn_tg_test.clicked.connect(self._telegram_test)
        gtg.addWidget(self.btn_tg_test, 3, 2)
        hilfe_tg = QtWidgets.QLabel(
            "So geht es: in Telegram @BotFather anschreiben, /newbot senden und "
            "einen Namen vergeben - er antwortet mit dem Bot-Token. Dann dem "
            "neuen Bot eine beliebige Nachricht schicken und hier "
            "\u201eChat-ID ermitteln\u201c druecken.")
        hilfe_tg.setObjectName("hint")
        hilfe_tg.setWordWrap(True)
        gtg.addWidget(hilfe_tg, 3, 0, 1, 2)
        tg = telegram_laden()
        self.chk_telegram.setChecked(tg['an'])
        self.txt_tg_token.setText(tg['token'])
        self.txt_tg_chat.setText(tg['chat'])
        self.chk_telegram.toggled.connect(lambda *_: self._telegram_merken())
        self.txt_tg_token.editingFinished.connect(self._telegram_merken)
        self.txt_tg_chat.editingFinished.connect(self._telegram_merken)
        vset.addWidget(self.box_telegram)
        vset.addStretch()
        row_set = QtWidgets.QHBoxLayout()
        row_set.addStretch()
        self.btn_settings_close = QtWidgets.QPushButton(" Schließen")
        self.btn_settings_close.clicked.connect(self.dlg_settings.accept)
        row_set.addWidget(self.btn_settings_close)
        vset.addLayout(row_set)

        # --------------------------------------------------------------
        # Warteschlange (eigenes Fenster)
        # --------------------------------------------------------------
        self.dlg_queue = QtWidgets.QDialog(self)
        self.dlg_queue.setMinimumSize(560, 320)
        gq = QtWidgets.QVBoxLayout(self.dlg_queue)
        self.lbl_queue_hint = QtWidgets.QLabel(
            "Jeder Auftrag merkt sich Ordner, Schritt und alle Einstellungen. "
            "Neue Aufträge legst du im Hauptfenster mit „Zur Warteschlange“ an.")
        self.lbl_queue_hint.setObjectName("hint")
        self.lbl_queue_hint.setWordWrap(True)
        gq.addWidget(self.lbl_queue_hint)
        self.list_queue = QtWidgets.QListWidget()
        self.list_queue.setMinimumHeight(120)
        gq.addWidget(self.list_queue, stretch=1)
        rowq = QtWidgets.QHBoxLayout()
        self.btn_q_del = QtWidgets.QPushButton(" Entfernen")
        self.btn_q_del.clicked.connect(self._queue_remove)
        rowq.addWidget(self.btn_q_del)
        self.btn_q_clear = QtWidgets.QPushButton(" Leeren")
        self.btn_q_clear.clicked.connect(self._queue_clear)
        rowq.addWidget(self.btn_q_clear)
        rowq.addStretch()
        self.btn_q_run = QtWidgets.QPushButton(" Stapel abarbeiten")
        self.btn_q_run.setObjectName("primary")
        self.btn_q_run.clicked.connect(self._queue_start)
        rowq.addWidget(self.btn_q_run)
        gq.addLayout(rowq)

        # --------------------------------------------------------------
        # Aktionen: Zusammenfassung + Knoepfe des aktuellen Schritts
        # --------------------------------------------------------------
        box_actions = QtWidgets.QFrame()
        box_actions.setObjectName("statuscard")
        vact = QtWidgets.QVBoxLayout(box_actions)
        vact.setContentsMargins(10, 8, 10, 8)
        vact.setSpacing(6)
        self.lbl_summary = QtWidgets.QLabel("Noch nicht gestartet.")
        self.lbl_summary.setWordWrap(True)
        vact.addWidget(self.lbl_summary)
        row_btn = QtWidgets.QHBoxLayout()
        self.btn_start = QtWidgets.QPushButton(" Start")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self._primary_action)
        row_btn.addWidget(self.btn_start, stretch=3)
        self.btn_preview = QtWidgets.QPushButton(" Vorschau (5 Bilder)")
        self.btn_preview.clicked.connect(self._start_preview)
        row_btn.addWidget(self.btn_preview, stretch=1)
        self.btn_schnell = QtWidgets.QPushButton(" \u26a1 Schnellvorschau")
        self.btn_schnell.clicked.connect(self._start_schnell)
        row_btn.addWidget(self.btn_schnell, stretch=1)
        self.btn_q_add = QtWidgets.QPushButton(" Zur Warteschlange")
        self.btn_q_add.clicked.connect(self._queue_add)
        row_btn.addWidget(self.btn_q_add, stretch=1)
        self.btn_queue_open = QtWidgets.QPushButton(" Warteschlange…")
        self.btn_queue_open.clicked.connect(self._open_queue)
        row_btn.addWidget(self.btn_queue_open, stretch=1)
        # Seltener gebrauchte Werkzeuge liegen im Menue "Weitere". Die Namen
        # btn_plain / btn_compare bleiben, es sind jetzt aber Menue-Eintraege.
        self.btn_more = QtWidgets.QPushButton(" Weitere")
        self.menu_more = QtWidgets.QMenu(self.btn_more)
        self.menu_more.setToolTipsVisible(True)
        self.btn_plain = self.menu_more.addAction(" Rohfassung")
        self.btn_plain.triggered.connect(lambda _=False: self._start_plain())
        self.btn_compare = self.menu_more.addAction(" Vergleich…")
        self.btn_compare.triggered.connect(lambda _=False: self._open_compare_dialog())
        self.btn_more.setMenu(self.menu_more)
        row_btn.addWidget(self.btn_more, stretch=1)
        self.btn_open_dir = QtWidgets.QPushButton(" Ordner öffnen")
        self.btn_open_dir.clicked.connect(self._open_output_dir)
        row_btn.addWidget(self.btn_open_dir, stretch=1)
        self.btn_cancel = QtWidgets.QPushButton(" Abbrechen")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        row_btn.addWidget(self.btn_cancel, stretch=1)
        vact.addLayout(row_btn)
        main_layout.addWidget(box_actions)

        # --------------------------------------------------------------
        # Status: was laeuft gerade, was ist erledigt, was kommt noch
        # --------------------------------------------------------------
        self.status_card = QtWidgets.QFrame()
        self.status_card.setObjectName("statuscard")
        v_status = QtWidgets.QVBoxLayout(self.status_card)
        v_status.setContentsMargins(12, 10, 12, 12)
        v_status.setSpacing(8)
        row_status = QtWidgets.QHBoxLayout()
        row_status.setSpacing(12)
        self.lbl_status = QtWidgets.QLabel("Bereit.")
        self.lbl_status.setObjectName("statustitel")
        self.lbl_status.setWordWrap(True)
        fm = self.lbl_status.fontMetrics()
        self.lbl_status.setMaximumHeight(fm.height() * 2 + 12)
        self.lbl_status.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                      QtWidgets.QSizePolicy.Fixed)
        row_status.addWidget(self.lbl_status, stretch=1)
        # Beginn und Dauer des Laufs, rechts neben dem Status.
        self.lbl_lauf = QtWidgets.QLabel("")
        self.lbl_lauf.setObjectName("statuszeit")
        row_status.addWidget(self.lbl_lauf)
        # Das Protokoll ist eingeklappt, bis man es braucht; bei einem
        # Fehler klappt _on_fail() es von selbst auf.
        self.btn_log = QtWidgets.QPushButton(" Protokoll anzeigen")
        self.btn_log.setObjectName("toggle")
        self.btn_log.setCheckable(True)
        self.btn_log.toggled.connect(self._on_log_toggled)
        row_status.addWidget(self.btn_log)
        v_status.addLayout(row_status)
        self.ablauf_leiste = AblaufLeiste()
        v_status.addWidget(self.ablauf_leiste)
        row_bar = QtWidgets.QHBoxLayout()
        row_bar.setSpacing(10)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setValue(0)
        row_bar.addWidget(self.progress, stretch=1)
        self.lbl_prozent = QtWidgets.QLabel("")
        self.lbl_prozent.setObjectName("prozent")
        self.lbl_prozent.setMinimumWidth(44)
        self.lbl_prozent.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        row_bar.addWidget(self.lbl_prozent)
        self.progress.valueChanged.connect(self._prozent_zeigen)
        v_status.addLayout(row_bar)
        # Status und Protokoll nebeneinander: das eingeblendete Protokoll
        # nimmt die Breite neben dem Status und genau dessen Hoehe. Unter
        # dem Status stehend draengte es die Seiten darueber zusammen, und
        # "Video rendern" brauchte wieder einen Rollbalken.
        self.row_unten = QtWidgets.QHBoxLayout()
        self.row_unten.setSpacing(6)
        self.row_unten.addWidget(self.status_card, 1)
        main_layout.addLayout(self.row_unten)
        self._ablauf = None
        self._ablauf_timer = QtCore.QTimer(self)
        self._ablauf_timer.setInterval(1000)
        self._ablauf_timer.timeout.connect(self._ablauf_zeigen)
        self._log_eintraege = []          # [(Zeitpunkt, Meldung)]
        self.txt_log = QtWidgets.QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMinimumHeight(0)
        self.txt_log.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        # Hoehe bestimmt allein der Status daneben.
        self.txt_log.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                                   QtWidgets.QSizePolicy.Ignored)
        self.txt_log.setVisible(False)
        self.row_unten.addWidget(self.txt_log, 1)
        verwaist = [n for n in ("btn_start", "btn_plain", "btn_compare", "btn_cancel",
                                "btn_reset", "btn_roi", "btn_cam_path", "cmb_lang",
                                "btn_preview", "cmb_fade", "lbl_gaps", "lbl_clip",
                                "list_queue", "btn_q_add", "btn_q_run", "btn_open_dir",
                                "pages", "lbl_summary", "cmb_engine", "box_effects",
                                "cmb_theme", "btn_settings", "btn_queue_open", "btn_log",
                                "chk_hotpix", "chk_diag", "cmb_calib", "progress",
                                "txt_log", "lbl_status", "list_widget", "graph",
                                "btn_kf_filter", "btn_kf_edit", "lbl_clip",
                                "lbl_farbstich",
                                "cmb_procs")
                    if getattr(self, n, None) is not None
                    and getattr(self, n).parentWidget() is None]
        if verwaist:
            print(f"WARNUNG: nicht im Layout verankert: {', '.join(verwaist)}")
        main_layout.setStretchFactor(self.splitter, 1)
        main_layout.setStretchFactor(self.row_unten, 0)
        # Zusammenfassung folgt jeder Aenderung an den Ausgabe-Einstellungen
        for w in (self.cmb_fps, self.cmb_res, self.cmb_codec, self.cmb_quality,
                  self.cmb_blur, self.cmb_fade, self.cmb_export_dir, self.cmb_engine):
            w.currentIndexChanged.connect(lambda *_: self._update_summary())
        for w in (self.chk_stab, self.chk_denoise, self.chk_hotpix, self.chk_reverse,
                  self.chk_tel, self.chk_astro):
            w.toggled.connect(lambda *_: self._update_summary())
        self._update_visibility()
        self._queue_refresh()
        self._load_settings()
        self.cmb_theme.blockSignals(True)
        self.cmb_theme.setCurrentIndex(1 if self.theme == 'light' else 0)
        self.cmb_theme.blockSignals(False)
        self._apply_theme(self.theme)
        self.cmb_lang.blockSignals(True)
        self.cmb_lang.setCurrentIndex(1 if self.lang == 'en' else 0)
        self.cmb_lang.blockSignals(False)
        self._apply_language(self.lang)
        self._go_step('load')
        self.btn_start.setFocus()

    # ------------------------------------------------------------------
    #  Schrittleiste
    # ------------------------------------------------------------------
    def _is_busy(self):
        # Eigener Merker statt worker.isRunning(): das Fertig-Signal kommt an,
        # waehrend der Thread noch auslaeuft.
        return getattr(self, '_busy', False)

    def _on_format_changed(self, *_):
        """JPG <-> RAW: 'Keyframes bearbeiten' gibt es nur im RAW-Workflow."""
        if not self.rb_raw.isChecked() and self.step == 'keys':
            self._go_step('render')
        else:
            self._go_step(self.step)

    def _go_step(self, key):
        """Wechselt die Seite. Bei RAW waehlt der Schritt zugleich Pass 1/2."""
        is_raw = self.rb_raw.isChecked()
        if key == 'keys' and not is_raw:
            key = 'render'
        self.step = key
        if is_raw:
            pass_idx = 0 if key in ('load', 'smooth') else 1
            if self.cmb_rawmode.currentIndex() != pass_idx:
                self.cmb_rawmode.blockSignals(True)
                self.cmb_rawmode.setCurrentIndex(pass_idx)
                self.cmb_rawmode.blockSignals(False)
        self.pages.setCurrentIndex(self.STEPS.index(key))
        self.step_buttons[key].setChecked(True)
        self._update_visibility()
        # Die Oberflaeche in die Farbe des Schritts tauchen - aber nur,
        # wenn sich der Schritt wirklich geaendert hat; das Neusetzen des
        # Stils ist die teuerste Operation der Oberflaeche.
        if (getattr(self, '_thema_bereit', False)
                and getattr(self, '_schritt_gefaerbt', None) != key):
            self._apply_theme(self.theme)

    def _pick_step_for_folder(self):
        """Nach dem Einlesen eines neuen Ordners den naechsten sinnvollen
        Schritt anzeigen. Alle Schritte bleiben frei anklickbar."""
        files = self._nef_files if self.rb_raw.isChecked() else self._jpg_files
        if not files:
            self._go_step('load')
        elif not self.rb_raw.isChecked():
            self._go_step('smooth')
        elif not self._step_done('smooth'):
            self._go_step('smooth')
        elif self._kf_count == 0:
            self._go_step('keys')
        else:
            self._go_step('render')

    def _step_done(self, key):
        is_raw = self.rb_raw.isChecked()
        files = self._nef_files if is_raw else self._jpg_files
        if key == 'load':
            return bool(files)
        if not files or not self.target_dir:
            return False
        if key == 'smooth':
            return is_raw and os.path.exists(pl_datei(self.target_dir, DEFLICKER_DB))
        if key == 'keys':
            return self._kf_count > 0
        return os.path.exists(pl_datei(self.target_dir, RESULT_DB))

    def _update_steps(self):
        """Beschriftet Schrittleiste, Hinweistexte und den Hauptknopf neu."""
        is_raw = self.rb_raw.isChecked()
        files = self._nef_files if is_raw else self._jpg_files
        engine = eng('label')
        titel = {
            'load': self._t("Bilder laden", "Load images"),
            'smooth': (self._t("Helligkeit glätten (Pass 1)", "Smooth brightness (pass 1)")
                       if is_raw else self._t("Helligkeit glätten", "Smooth brightness")),
            'keys': self._t("Keyframes bearbeiten", "Edit keyframes"),
            'render': (self._t("Video rendern (Pass 2)", "Render video (pass 2)")
                       if is_raw else self._t("Video rendern", "Render video")),
        }
        tips = {
            'load': self._t("Ordner wählen und Format festlegen.",
                            "Choose the folder and the format."),
            'smooth': (self._t("Pass 1 misst die Helligkeit und legt die Korrektur in den Begleitdateien ab.",
                               "Pass 1 measures the brightness and stores the correction in the sidecar files.")
                       if is_raw else
                       self._t("Stärke der Glättung und Zielhelligkeit einstellen.",
                               "Set smoothing strength and target brightness.")),
            'keys': self._t(f"Einzelne Bilder in {engine} bearbeiten; Purelapse blendet dazwischen über.",
                            f"Edit individual frames in {engine}; Purelapse blends between them."),
            'render': (self._t(f"Pass 2 lässt {engine} entwickeln, verteilt die Keyframe-Profile und baut das Video.",
                               f"Pass 2 lets {engine} develop, spreads the keyframe profiles and builds the video.")
                       if is_raw else
                       self._t("Video-Format, Effekte und Speicherort festlegen.",
                               "Set video format, effects and location.")),
        }
        nr = 0
        for key in self.STEPS:
            sichtbar = is_raw or key != 'keys'
            self.step_buttons[key].setVisible(sichtbar)
            if key in self.step_arrows:
                self.step_arrows[key].setVisible(sichtbar)
            if not sichtbar:
                continue
            nr += 1
            fertig = self._step_done(key)
            marke = "✔" if fertig else str(nr)
            b = self.step_buttons[key]
            b.setText(f" {marke}   {titel[key]}")
            b.setToolTip(tips[key])
            if b.property("done") != fertig:
                b.setProperty("done", fertig)   # faerbt erledigte Schritte
                b.style().unpolish(b)
                b.style().polish(b)
        hints = {
            'load': self._t(
                "Wähle oben den Ordner mit den Einzelbildern. Purelapse erkennt JPG und RAW "
                "selbst; liegen beide im Ordner, legst du hier fest, womit gearbeitet wird.",
                "Choose the folder with the frames above. Purelapse detects JPG and RAW on its "
                "own; if the folder holds both, you decide here which one to work with."),
            'smooth': (self._t(
                "Pass 1 misst die Helligkeit jedes Bildes und schreibt die Korrektur in die "
                f"{engine}-Begleitdateien. Es entsteht noch kein Video. Die Zielkurve im "
                "Diagramm zeigt das Ergebnis schon jetzt.",
                "Pass 1 measures the brightness of every frame and writes the correction to "
                f"the {engine} sidecar files. No video is created yet. The target curve in "
                "the chart already shows the result.") if is_raw else self._t(
                "Stelle ein, wie stark die Helligkeit geglättet wird. Die Zielkurve im "
                "Diagramm zeigt das Ergebnis schon jetzt.",
                "Set how strongly the brightness is smoothed. The target curve in the chart "
                "already shows the result.")),
            'keys': self._t(
                "Dieser Schritt ist freiwillig. Setze links in der Bildleiste bei den Bildern, "
                f"die du gestalten willst, den Stern ★ und bearbeite sie in {engine}. "
                "Beim Rendern blendet Purelapse zwischen den Keyframes weich über.",
                "This step is optional. In the filmstrip on the left, click the star ★ on the "
                f"frames you want to grade and edit them in {engine}. When rendering, Purelapse "
                "blends smoothly between the keyframes."),
            'render': (self._t(
                f"Pass 2 lässt {engine} alle Bilder entwickeln, verteilt die Keyframe-"
                "Bearbeitungen auf die Bilder dazwischen und erzeugt das Video.",
                f"Pass 2 lets {engine} develop all frames, spreads the keyframe edits across "
                "the frames in between and creates the video.") if is_raw else self._t(
                "Lege Format, Effekte und Speicherort des Videos fest.",
                "Set the format, effects and location of the video.")),
        }
        if eng('kind') == 'darktable':
            hints['keys'] += ("\n\n" + DT_KEYFRAME_HINWEIS['en' if self.lang == 'en' else 'de']
                              + "\n\n" + DT_STERNE_HINWEIS['en' if self.lang == 'en' else 'de'])
        for key, lbl in self.step_hints.items():
            lbl.setText(hints[key])
        if self._kf_count > 0:
            self.lbl_keys_status.setText(self._t(
                f"★ {self._kf_count} Keyframes markiert. Im Diagramm stehen sie als "
                "gestrichelte Linien. Nach dem Bearbeiten in der Engine die Bilder neu einlesen.",
                f"★ {self._kf_count} keyframes marked. The chart shows them as dashed lines. "
                "Re-read the images after editing in the engine."))
        else:
            self.lbl_keys_status.setText(self._t(
                f"Noch keine Keyframes markiert. Ohne Keyframes entwickelt {engine} alle "
                "Bilder mit den Profilen aus Pass 1.",
                f"No keyframes marked yet. Without keyframes {engine} develops all frames "
                "with the profiles from pass 1."))
        # Hauptknopf: sagt, was ein Klick im aktuellen Schritt tut
        if not files:
            text = self._t(" Ordner wählen…", " Choose folder…")
        elif self.step == 'load':
            text = self._t(" Weiter: Helligkeit glätten", " Next: smooth brightness")
        elif self.step == 'keys' or (self.step == 'smooth' and not is_raw):
            text = self._t(" Weiter: Video rendern", " Next: render video")
        elif is_raw and self.step == 'smooth':
            text = self._t(" Pass 1 starten: Helligkeit analysieren",
                           " Start pass 1: analyse brightness")
        elif is_raw:
            text = self._t(" Pass 2 starten: Video rendern", " Start pass 2: render video")
        elif self.chk_video.isChecked():
            text = self._t(" Zeitraffer erstellen", " Create timelapse")
        else:
            text = self._t(" Bilder entflackern (ohne Video)", " Deflicker images (no video)")
        self.btn_start.setText(text)
        self._apply_action_state()

    def _apply_action_state(self):
        """Sperrt Knoepfe, die im aktuellen Schritt nichts tun koennen, und
        nennt im Tooltip den Grund."""
        table = TRANSLATIONS_TT_EN if self.lang == 'en' else TRANSLATIONS
        busy = self._is_busy()
        hat_bilder = bool(self._nef_files if self.rb_raw.isChecked() else self._jpg_files)
        laeuft = self._t("Es läuft gerade ein Arbeitsschritt. Warten oder abbrechen.",
                         "A task is running. Wait or cancel.")
        ohne = self._t("Erst einen Ordner mit Bildern wählen.",
                       "Choose a folder with images first.")
        for btn, key, erlaubt in (
                (self.btn_preview, 'TT_PREVIEW', self.step != 'load'),
                (self.btn_q_add, 'TT_QADD', self.step in ('smooth', 'render')),
                (self.btn_plain, 'TT_PLAIN', True),
                (self.btn_compare, 'TT_COMPARE', None)):
            if busy:
                btn.setEnabled(False)
                btn.setToolTip(laeuft)
            elif erlaubt is None:
                btn.setEnabled(True)
                btn.setToolTip(table.get(key, ""))
            elif not hat_bilder:
                btn.setEnabled(False)
                btn.setToolTip(ohne)
            elif not erlaubt:
                btn.setEnabled(False)
                btn.setToolTip(self._t(
                    "In diesem Schritt nicht verfügbar. Wechsle zu „Helligkeit glätten“ "
                    "oder „Video rendern“.",
                    "Not available in this step. Switch to “Smooth brightness” or "
                    "“Render video”."))
            else:
                btn.setEnabled(True)
                btn.setToolTip(table.get(key, ""))
        self.btn_start.setEnabled(not busy)
        self.btn_start.setToolTip(laeuft if busy else table.get('TT_START', ""))

    def _primary_action(self):
        files = self._nef_files if self.rb_raw.isChecked() else self._jpg_files
        if not files:
            self._browse()
        elif self.step == 'load':
            self._go_step('smooth')
        elif self.step == 'keys':
            self._go_step('render')
        elif self.step == 'smooth' and not self.rb_raw.isChecked():
            # JPG kennt keinen eigenen Pass 1: Glaetten und Rendern sind
            # ein Lauf. Erst zur Seite "Video rendern", damit Format,
            # Effekte und Speicherort eingestellt werden koennen.
            self._go_step('render')
        else:
            self._start()

    def _engine_anzeigen(self):
        """
        Schild rechts in der Infozeile: welche Engine eingestellt ist.
        Bei JPG wird keine gebraucht; fehlt bei RAW das Programm der Engine,
        steht das gleich dort - Pass 2 und die Vorschau braeuchten es.
        """
        k = getattr(self, 'btn_engine', None)
        if k is None:
            return
        t = THEMES[self.theme]
        raw = self.rb_raw.isChecked() if hasattr(self, 'rb_raw') else True
        name = eng('label')
        feld = getattr(self, 'txt_art_path', None)
        cli = (feld.text() if feld is not None else get_art_path()).strip()
        if not raw:
            text = self._t("JPG · ohne Engine", "JPG · no engine")
            tip = self._t(f"JPG-Serien rechnet Purelapse selbst, ohne Engine.\n"
                          f"Fuer RAW eingestellt: {name}.\n\nKlick: Einstellungen",
                          f"Purelapse processes JPG sequences itself, without an engine.\n"
                          f"Set for RAW: {name}.\n\nClick: settings")
            farbe, rand = t['dim'], t['border2']
        elif not (cli and os.path.isfile(cli)):
            text = self._t(f"⚠ Engine: {name} – Programm fehlt",
                           f"⚠ Engine: {name} – program missing")
            tip = self._t(f"Fuer Pass 2 und die Vorschau braucht Purelapse {eng('bin')}.\n\n"
                          "Klick: in den Einstellungen den Pfad eintragen.",
                          f"Pass 2 and the preview need {eng('bin')}.\n\n"
                          "Click: enter its path in the settings.")
            farbe = rand = t['warn']
        else:
            text = f"Engine: {name}"
            tip = self._t(f"RAW-Entwicklung mit {name}\n{cli}\n\nKlick: Einstellungen",
                          f"RAW development with {name}\n{cli}\n\nClick: settings")
            farbe, rand = t['text'], t['border2']
        k.setText(text)
        k.setToolTip(tip)
        k.setStyleSheet(
            f"QPushButton#enginechip {{ color: {farbe}; background: transparent;"
            f" border: 1px solid {rand}; border-radius: 7px; padding: 3px 12px;"
            " min-height: 0px; font-weight: bold; }"
            f" QPushButton#enginechip:hover {{ border-color: {t['accent']}; }}")

    def _update_summary(self):
        """Eine Zeile ueber den Knoepfen: was der naechste Klick bewirkt."""
        self._engine_anzeigen()
        if not hasattr(self, 'lbl_summary') or self._is_busy():
            return
        is_raw = self.rb_raw.isChecked()
        files = self._arbeitsdateien(is_raw)
        n = len(files)
        engine = eng('label')
        if n == 0:
            text = self._t("Noch keine Bilder geladen.", "No images loaded yet.")
        elif self.step == 'load':
            text = self._t(f"{n} {'RAW' if is_raw else 'JPG'}-Bilder geladen.",
                           f"{n} {'RAW' if is_raw else 'JPG'} images loaded.")
        elif is_raw and self.step == 'smooth':
            text = self._t(
                f"Pass 1: {n} Bilder messen, Korrektur in die {engine}-Begleitdateien schreiben. Kein Video.",
                f"Pass 1: measure {n} frames, write the correction to the {engine} sidecars. No video.")
        elif self.step == 'keys':
            text = self._t(f"{self._kf_count} Keyframes markiert.",
                           f"{self._kf_count} keyframes marked.")
        elif not is_raw and self.step == 'smooth':
            text = self._t(f"{n} Bilder. Glättung einstellen, dann weiter zu Format und Effekten.",
                           f"{n} images. Set the smoothing, then continue to format and effects.")
        elif not is_raw and not self.chk_video.isChecked():
            text = self._t(f"{n} Bilder entflackern, kein Video.",
                           f"Deflicker {n} images, no video.")
        else:
            try:
                dauer = n / float(self.cmb_fps.currentText())
            except ValueError:
                dauer = 0.0
            _, res_name = self.res_map[self.cmb_res.currentIndex()]
            teile = [self._t(f"{n} Bilder", f"{n} images")
                     + f" → {res_name} @ {self.cmb_fps.currentText()} fps ({dauer:.0f} s)",
                     self.cmb_codec.currentText(), self.cmb_quality.currentText()]
            if is_raw:
                teile.append(f"Engine: {engine}")
            zeile2 = [self._t("Schnitt: eigene 16:9-Kamerafahrt", "Crop: custom 16:9 camera move")
                      if self.cam_keyframes else self._t("Schnitt: 16:9 Mitte", "Crop: 16:9 centre")]
            if self.cmb_blur.currentIndex() > 0:
                zeile2.append(f"Motion Blur: {self.cmb_blur.currentText()}")
            for chk in (self.chk_stab, self.chk_hotpix, self.chk_reverse, self.chk_tel,
                        self.chk_astro):
                if chk.isChecked():
                    zeile2.append(chk.text())
            if not is_raw and self.chk_denoise.isChecked():
                zeile2.append(self.chk_denoise.text())
            if self.roi_rel:
                zeile2.append(self._t("Messbereich aktiv", "Measuring area active"))
            zeile2.append(self._t("Ziel: ", "To: ") + (self._current_target_label()))
            text = "  ·  ".join(teile) + "\n" + "  ·  ".join(zeile2)
        self.lbl_summary.setText(text)
        self.lbl_summary.setStyleSheet(f"color: {THEMES[self.theme]['dim']};")

    def _current_target_label(self):
        idx = self.cmb_export_dir.currentIndex()
        if idx == 3 and self.custom_out_dir:
            return self.custom_out_dir
        text = self.cmb_export_dir.currentText()
        return text.split(". ", 1)[-1] if ". " in text else text

    def _open_settings(self):
        self.dlg_settings.setWindowTitle(self._t("Einstellungen", "Settings"))
        self.dlg_settings.exec_()
        self._update_steps()
        self._update_summary()

    def _open_queue(self):
        self.dlg_queue.setWindowTitle(self._t("Warteschlange", "Queue"))
        self.dlg_queue.show()
        self.dlg_queue.raise_()
        self.dlg_queue.activateWindow()

    def _on_log_toggled(self, offen):
        self.txt_log.setVisible(offen)
        self.btn_log.setText(self._t(" Protokoll ausblenden", " Hide log") if offen
                             else self._t(" Protokoll anzeigen", " Show log"))
        if offen:
            sb = self.txt_log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_filter_keyframes(self, an):
        """
        Blendet Nicht-Keyframes aus.

        Ausgeblendet, nicht entfernt: Diagramm und Bildleiste sind ueber die
        Zeilennummer gekoppelt (_on_tile_selected liest frames_x[row], ein
        Klick im Diagramm setzt setCurrentRow(index)). Wuerden Zeilen
        verschwinden, zeigte das Diagramm auf das falsche Bild.
        """
        sichtbar = 0
        for t in self.tiles:
            chk = t.get('chk')
            ist_kf = bool(chk.isChecked()) if chk is not None else False
            t['item'].setHidden(an and not ist_kf)
            if not t['item'].isHidden():
                sichtbar += 1
        if an:
            self.btn_kf_filter.setText(self._t(f"★ nur Keyframes ({sichtbar})",
                                               f"★ keyframes only ({sichtbar})"))
            if sichtbar == 0:
                self.lbl_status.setText(self._t(
                    "Kein Keyframe markiert - Filter zeigt nichts an.",
                    "No keyframe marked - the filter shows nothing."))
        else:
            self.btn_kf_filter.setText(self._t("★ nur Keyframes",
                                               "★ keyframes only"))
        self._relayout_gallery()
        self._band_timer.start()

    def _keyframe_zeilen(self):
        """Zeilennummern aller Kacheln, deren Keyframe-Haken gesetzt ist."""
        return [i for i, t in enumerate(self.tiles)
                if t.get('chk') is not None and t['chk'].isChecked()]

    def _ziel_keyframe(self):
        """
        Auf welches Bild wirkt "Keyframe einstellen"?

        Die gewaehlte Kachel, wenn sie ein Keyframe ist - sonst das erste
        Keyframe der Sequenz.

        Der Knopf haengt damit nicht mehr daran, ob die Auswahl in der
        Bildleiste zustande gekommen ist. Die Kacheln liegen als eigene
        Widgets ueber den Listeneintraegen und fangen Mausklicks ab; dass
        die Liste davon erfaehrt, ist nachgeruestet und soll keine
        Voraussetzung fuer eine Funktion sein, die auch ohne sie
        eindeutig ist.
        """
        kfs = self._keyframe_zeilen()
        if not kfs:
            return None
        row = self.list_widget.currentRow()
        return row if row in kfs else kfs[0]

    def _update_kf_buttons(self):
        """Gibt den Einstellknopf frei, sobald es ein Keyframe gibt."""
        ziel = self._ziel_keyframe() if self.tiles else None
        passende_engine = (eng('kind') in ('ini', 'darktable'))
        moeglich = (ziel is not None and passende_engine
                    and not getattr(self, '_busy', False))
        self.btn_kf_edit.setEnabled(moeglich)
        if not passende_engine:
            self.btn_kf_edit.setToolTip(self._t(
                "Schnelleinstellungen gibt es fuer ART, RawTherapee und Darktable.",
                "Quick settings exist for ART, RawTherapee and darktable."))
        elif ziel is None:
            self.btn_kf_edit.setToolTip(self._t(
                "Noch kein Keyframe markiert. Dafuer in der Bildleiste "
                "bei einem Bild den Stern ★ "
                "setzen - von dort werden die Einstellungen auf die "
                "Nachbarbilder weitergetragen.",
                "No keyframe marked yet. Click the star ★ on "
                "an image in the gallery - the settings are carried from "
                "there to the neighbouring frames."))
        else:
            name = self.tiles[ziel].get('name', '?')
            self.btn_kf_edit.setToolTip(self._t(
                f"Stellt {name} ein: Weissabgleich, Helligkeit, Kontrast, "
                "Saettigung, Schaerfe und Entrauschen - ohne die Engine zu "
                "oeffnen.\n\nEin anderes Keyframe: dessen Kachel "
                "anklicken oder doppelklicken.",
                f"Edits {name}: white balance, brightness, contrast, "
                "saturation, sharpening and denoising - without opening "
                "the engine.\n\nFor a different keyframe: click or "
                "double-click its tile."))

    def _open_quick_dialog(self):
        """Schnelleinstellungen fuer das Ziel-Keyframe."""
        ziel = self._ziel_keyframe()
        if ziel is None or not self.target_dir:
            return
        t = self.tiles[ziel]
        # Das bearbeitete Bild sichtbar machen - sonst weiss man hinterher
        # nicht, welches es war.
        if self.list_widget.currentRow() != ziel:
            self.list_widget.setCurrentRow(ziel)
        self.list_widget.scrollToItem(t['item'])
        bild = os.path.join(self.target_dir, t['name'])
        pfad = sidecar(bild)
        profil = read_arp_dict(pfad) if os.path.exists(pfad) else {}
        if not profile_is_complete(profil):
            # Ohne vollstaendiges Profil waere jeder geschriebene Wert ein
            # Schuss ins Leere: die Engine verwirft ein duennes Profil.
            dateien = self._nef_files or self._jpg_files
            vorlage, quelle = find_arp_template(self.target_dir, dateien)
            if vorlage is None:
                QtWidgets.QMessageBox.information(
                    self, self._t("Noch kein Profil", "No profile yet"),
                    self._t(
                        "Fuer dieses Bild gibt es noch kein vollstaendiges "
                        f"{eng('ext')}-Profil, und es ist auch kein "
                        "Basisprofil vorhanden.\n\n"
                        "Einmal Pass 1 laufen lassen - der legt die Profile "
                        "an. Danach stehen die Schnelleinstellungen zur "
                        "Verfuegung.",
                        "There is no complete "
                        f"{eng('ext')} profile for this image yet, and no "
                        "base profile either.\n\nRun pass 1 once - it "
                        "creates the profiles. The quick settings are "
                        "available afterwards."))
                return
            antwort = QtWidgets.QMessageBox.question(
                self, self._t("Profil anlegen", "Create profile"),
                self._t(
                    f"Fuer dieses Bild gibt es noch kein {eng('ext')}-Profil.\n\n"
                    "Soll eines aus dem Basisprofil angelegt werden?\n"
                    f"Quelle: {quelle}\n\n"
                    "Pass 1 ergaenzt darin spaeter nur die Belichtung und "
                    "laesst die uebrigen Werte unangetastet.",
                    f"There is no {eng('ext')} profile for this image yet.\n\n"
                    f"Create one from the base profile?\nSource: {quelle}\n\n"
                    "Pass 1 will later only add the exposure and leave the "
                    "other values untouched."),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes)
            if antwort != QtWidgets.QMessageBox.Yes:
                return
            zusammen = {sec: dict(par) for sec, par in vorlage.items()}
            for sec, par in profil.items():
                zusammen.setdefault(sec, {}).update(par)
            profil = zusammen

        # Die uebrigen Keyframes, damit man deren Einstellungen
        # uebernehmen kann.
        andere = []
        for i in self._keyframe_zeilen():
            if i == ziel:
                continue
            nachbar = self.tiles[i].get('name')
            if not nachbar:
                continue
            sc = sidecar(os.path.join(self.target_dir, nachbar))
            if os.path.exists(sc):
                andere.append((nachbar, sc))
        dlg = QuickLookDialog(self, t['name'], profil, lang=self.lang,
                              bild_pfad=bild, andere=andere,
                              cli_pfad=self.txt_art_path.text().strip())
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        # Derselbe Weg wie in der Vorschau des Dialogs - was dort zu
        # sehen war, steht danach im Profil.
        hl = dlg.hl_wert() if dlg.cmb_hl is not None else None
        profil, geschrieben, eingefroren = schnell_profil(
            profil, dlg.werte(), hl)
        if not geschrieben:
            self._on_log("purelapse@engine:~$ " + self._t(
                "Schnelleinstellungen: nichts angekreuzt, Profil unveraendert.",
                "Quick settings: nothing ticked, profile unchanged."))
            return
        try:
            write_arp_dict(pfad, profil)
        except OSError as e:
            QtWidgets.QMessageBox.critical(
                self, self._t("Fehler", "Error"),
                self._t(f"Das Profil konnte nicht geschrieben werden:\n{e}",
                        f"The profile could not be written:\n{e}"))
            return
        # Nachlesen statt vertrauen: ein stiller Fehlschlag beim Schreiben
        # waere sonst erst Stunden spaeter im Video zu sehen.
        kontrolle = read_arp_dict(pfad)
        fehlgeschlagen = [f"[{sec}] {key}" for sec, key, wert in geschrieben
                          if kontrolle.get(sec, {}).get(key) != wert]
        self._on_log("purelapse@engine:~$ " + self._t(
            f"Schnelleinstellungen in {os.path.basename(pfad)} geschrieben:",
            f"Quick settings written to {os.path.basename(pfad)}:"))
        for sec, key, wert in geschrieben:
            self._on_log(f"    [{sec}] {key} = {wert}")
        if 'tonkurve' in eingefroren or 'tonkurve_fest' in eingefroren:
            self._on_log("> " + self._t(
                "Auto-angepasste Tonkurve abgeschaltet: sie wuerde fuer jedes "
                "Bild neu berechnet und liesse das Video flackern.",
                "Auto-matched tone curve switched off: it would be computed "
                "anew for every frame and make the video flicker."))
        if fehlgeschlagen:
            self._on_log(self._t("> ACHTUNG: ", "> WARNING: ") + self._t(
                "nicht im Profil wiedergefunden: ", "not found in profile: ")
                + ", ".join(fehlgeschlagen))
        else:
            self._on_log("> " + self._t(
                "Nachgelesen und bestaetigt. Pass 2 traegt die Werte auf die "
                "Nachbarbilder weiter.",
                "Read back and confirmed. Pass 2 carries the values to the "
                "neighbouring frames."))
        self.lbl_status.setText(self._t(
            f"{len(geschrieben)} Wert(e) im Keyframe gesetzt.",
            f"{len(geschrieben)} value(s) set in the keyframe."))

    def _on_tile_selected(self, row):
        """Markiert das in der Bildleiste gewaehlte Bild im Diagramm."""
        self._markiere_auswahl(row)
        self._update_kf_buttons()
        if 0 <= row < len(self.frames_x):
            self.sel_marker.setPos(self.frames_x[row])
            self.sel_marker.setVisible(True)
        else:
            self.sel_marker.setVisible(False)

    # ------------------------------------------------------------------
    #  Hinweistexte und Sprache
    # ------------------------------------------------------------------
    def _t(self, de, en):
        return en if self.lang == 'en' else de

    def _tab(self, de):
        """Ein Text aus der Uebersetzungstabelle in der aktuellen Sprache -
        fuer Beschriftungen, die zur Laufzeit neu gesetzt werden."""
        return TRANSLATIONS.get(de, de) if self.lang == 'en' else de

    def _on_theme_changed(self, idx=None):
        self._apply_theme('light' if self.cmb_theme.currentIndex() == 1 else 'dark')

    def _farben(self):
        """Das Farbschema, eingefaerbt nach dem aktiven Arbeitsschritt."""
        return thema_mit_schritt(self.theme, getattr(self, 'step', 'load'))

    def _apply_theme(self, name):
        self.theme = name if name in THEMES else 'dark'
        t = self._farben()
        self._schritt_gefaerbt = getattr(self, 'step', 'load')
        self._thema_bereit = True
        app = QtWidgets.QApplication.instance()
        if app:
            app.setStyleSheet(build_stylesheet(t))
        if getattr(self, 'abdunkler', None) is not None:
            self.abdunkler.farbe_setzen(THEMES[self.theme].get('schleier', (0, 0, 0, 140)))
        self.list_widget.setStyleSheet(
            f"QListWidget {{ background: {t['gallery']}; border: 1px solid {t['border']};"
            f" border-radius: 8px; }}"
            f"QListWidget::item:selected {{ background: {t['sel']}; border-radius: 6px; }}")
        self.list_queue.setStyleSheet(
            f"QListWidget {{ background: {t['gallery']}; border: 1px solid {t['border']};"
            f" border-radius: 6px; }}")
        self.txt_log.setStyleSheet(
            f"QPlainTextEdit {{ background: {t['log_bg']}; color: {t['log_fg']};"
            f" border: 1px solid {t['border']}; border-radius: 8px;"
            " font-family: 'DejaVu Sans Mono', 'Ubuntu Mono', monospace;"
            f" font-size: 11px; padding: 6px; }}")
        # Die Farben stecken in den Zeilen des Protokolls - nach einem
        # Wechsel des Farbschemas werden sie neu geschrieben.
        self._log_neu_zeichnen()
        for feld in (self.txt_art_path, self.txt_arp_template):
            feld.setStyleSheet(f"color: {t['dim']}; font-size: 10px;")
        self.chk_diag.setStyleSheet(f"color: {t['dim']};")
        self._engine_anzeigen()
        self.lbl_size_est.setStyleSheet(f"color: {t['dim']}; font-style: italic;")
        self._style_gaps()
        if not self._is_busy():
            self.lbl_summary.setStyleSheet(f"color: {t['dim']};")
        try:
            self.graph.setBackground(t['graph_bg'])
            for achse in ('left', 'bottom', 'right'):
                ax = self.graph.getAxis(achse)
                ax.setPen(pg.mkPen(t['border']))
                ax.setTextPen(pg.mkPen(t['dim']))
            c = t['curves']
            self.plot_raw.setPen(stift(c['raw'], 2))
            self.plot_raw.setSymbolBrush(c['raw'])
            self.plot_smooth.setPen(stift(c['target'], 3))
            for name, kurve in (self.extra_plots or {}).items():
                kurve.setPen(stift(c.get(name, c['raw']), 2))
            for m in self.kf_marker:
                m.setPen(stift(c['kf'], 2, QtCore.Qt.DashLine))
                try:
                    m.label.setColor(c['kf'])
                except (AttributeError, TypeError):
                    pass
            for name, cb in (self.curve_toggles or {}).items():
                cb.setStyleSheet(f"color: {c.get(name, t['dim'])}; font-size: 11px;")
            self.sel_marker.setPen(stift(t['accent'], 2))
            self._style_sicht_band()
            # Der Diagrammtitel dient nur noch als Ladeanzeige; die Legende
            # steht als eigene Zeile unter dem Diagramm.
            self.graph.setTitle(None)
            self.graph.setLabel('bottom', self._t("Bild-Nr.", "Frame no."),
                                **{'color': t['dim'], 'font-size': '10px'})
            self.graph.setLabel('left', self._t("Helligkeit", "Brightness"),
                                **{'color': t['dim'], 'font-size': '10px'})
            self.lbl_legend.setText(
                f'<span style="color:{c["raw"]};">●━ ' + self._t("Gemessen", "Measured")
                + '</span>&nbsp;&nbsp;&nbsp;'
                f'<span style="color:{c["target"]};">━━ ' + self._t("Zielkurve", "Target curve")
                + '</span>&nbsp;&nbsp;&nbsp;'
                f'<span style="color:{c["kf"]};">┆ ' + self._t("Keyframe", "Keyframe")
                + '</span>')
        except Exception:
            pass
        if hasattr(self, 'curve_toggles'):
            self._update_sun_markers()
        save_theme(self.theme)

    def _apply_tooltips(self):
        mapping = {
            'lbl_path': 'TT_FOLDER', 'btn_browse': 'TT_BROWSE', 'btn_refresh': 'TT_IREFRESH',
            'rb_jpg': 'TT_FORMAT', 'rb_raw': 'TT_FORMAT',
            'btn_settings': 'TT_ISETTINGS', 'btn_queue_open': 'TT_QOPEN',
            'btn_log': 'TT_LOG', 'btn_more': 'TT_MORE',
            'btn_keys_refresh': 'TT_REFRESH', 'btn_gps_from_exif': 'TT_SUN',
            'cmb_scene': 'TT_SCENE', 'slider_smooth': 'TT_SMOOTH', 'slider_ev': 'TT_EV',
            'btn_roi': 'TT_ROI', 'cmb_cores': 'TT_CORES', 'txt_art_path': 'TT_ARTCLI',
            'cmb_procs': 'TT_PROCS',
            'btn_kf_filter': 'TT_KFFILTER',
            'cmb_engine': 'TT_ENGINE', 'cmb_calib': 'TT_CALIB', 'btn_cam_path': 'TT_CAMPATH', 'cmb_blur': 'TT_BLUR',
            'cmb_fade': 'TT_FADE',
            'chk_stab': 'TT_STAB', 'chk_denoise': 'TT_DENOISE', 'chk_reverse': 'TT_REVERSE',
            'chk_tel': 'TT_TEL', 'chk_astro': 'TT_ASTRO', 'btn_reset': 'TT_IRESET',
            'chk_hotpix': 'TT_HOTPIX',
            'cmb_lang': 'TT_LANG', 'btn_start': 'TT_START',
            'btn_plain': 'TT_PLAIN', 'btn_compare': 'TT_COMPARE',
            'btn_preview': 'TT_PREVIEW', 'btn_q_add': 'TT_QADD', 'btn_q_run': 'TT_QRUN',
            'btn_open_dir': 'TT_OPENDIR',
            'txt_lat': 'TT_SUN', 'txt_lon': 'TT_SUN', 'txt_utc': 'TT_SUN',
            'btn_erstes': 'TT_ERSTES', 'btn_letztes': 'TT_LETZTES',
            'btn_start_hier': 'TT_STARTBILD', 'btn_ende_hier': 'TT_ENDBILD',
            'txt_arp_template': 'TT_ARPTPL', 'chk_diag': 'TT_DIAG',
            'chk_tiff16': 'TT_TIFF16', 'btn_schnell': 'TT_SCHNELL',
        }
        table = TRANSLATIONS_TT_EN if self.lang == 'en' else TRANSLATIONS
        for attr, key in mapping.items():
            w = getattr(self, attr, None)
            if w is not None and key in table:
                w.setToolTip(table[key])
        # Symbolknoepfe haben keinen Text: Name fuer Bildschirmleser
        for attr, de, en in (('btn_browse', "Ordner wählen", "Choose folder"),
                             ('btn_refresh', "Aktualisieren", "Refresh"),
                             ('btn_reset', "Zurücksetzen", "Reset"),
                             ('btn_settings', "Einstellungen", "Settings")):
            w = getattr(self, attr, None)
            if w is not None:
                w.setAccessibleName(de if self.lang != 'en' else en)

    def _apply_language(self, lang):
        fwd = {k: v for k, v in TRANSLATIONS.items() if not k.startswith("TT_")}
        table = fwd if lang == 'en' else {v: k for k, v in fwd.items()}
        self.lang = lang
        for w in self.findChildren(QtWidgets.QWidget):
            w.blockSignals(True)
            try:
                for getter, setter in (('text', 'setText'), ('title', 'setTitle'),
                                       ('placeholderText', 'setPlaceholderText')):
                    if hasattr(w, getter) and hasattr(w, setter):
                        try:
                            cur = getattr(w, getter)()
                        except (TypeError, RuntimeError):
                            continue
                        if cur in table:
                            getattr(w, setter)(table[cur])
                if isinstance(w, QtWidgets.QComboBox):
                    for i in range(w.count()):
                        t = w.itemText(i)
                        if t in table:
                            w.setItemText(i, table[t])
            finally:
                w.blockSignals(False)
        for act in self.findChildren(QtWidgets.QAction):
            if act.text() in table:
                act.setText(table[act.text()])
        self._apply_tooltips()
        # Texte, die nicht aus der Tabelle kommen, neu aufbauen
        self._update_steps()
        self._update_summary()
        self._queue_refresh()
        self._on_log_toggled(self.btn_log.isChecked())
        save_lang(lang)
        self._on_smooth_changed(self.slider_smooth.value())
        self._on_ev_changed(self.slider_ev.value())
        self._update_filesize_estimate()
        if self._jpg_files or self._nef_files:
            self._recount_keyframes()
        else:
            self.lbl_count.setText(self._t("Kein Ordner gewählt.", "No folder selected."))
        if getattr(self, '_last_gaps', None):
            self._on_gaps_found(*self._last_gaps)
        if getattr(self, '_last_clip', None):
            self._zeige_lichter(*self._last_clip)
        if getattr(self, '_hl_werte', None):
            self._pruefe_farbstich()
        if getattr(self, 'btn_kf_filter', None) is not None:
            # Die Beschriftung traegt im Filterbetrieb einen Zaehler und
            # steht deshalb nicht in der Uebersetzungstabelle.
            self._on_filter_keyframes(self.btn_kf_filter.isChecked())
        self._update_kf_buttons()
        self._apply_theme(self.theme)

    def _on_lang_changed(self, idx):
        self._apply_language('en' if idx == 1 else 'de')

    def _open_reset_dialog(self):
        if not self.target_dir or not os.path.isdir(self.target_dir):
            QtWidgets.QMessageBox.warning(
                self, "Kein Ordner" if self.lang == 'de' else "No folder",
                "Bitte zuerst einen Zeitraffer-Ordner waehlen."
                if self.lang == 'de' else "Please select a timelapse folder first.")
            return
        dlg = ResetDialog(self.target_dir, self.lang, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self._on_log(self._t(f"purelapse@engine:~$ RESET - {dlg.deleted} Dateien geloescht",
                                 f"purelapse@engine:~$ RESET - {dlg.deleted} files deleted"))
            self.cam_keyframes = None
            self.lbl_cam_status.setText("Standard (Mitte)" if self.lang == 'de'
                                        else "Default (centred)")
            zustand_setzen(self.lbl_cam_status, "", 'art')
            self._refresh_preview()

    def _browse(self):
        start = self.target_dir or get_last_path() or os.path.expanduser("~")
        dlg = OrdnerDialog(self, self._t("Zeitraffer-Ordner wählen", "Choose timelapse folder"),
                           start, self.lang)
        d = dlg.ordner() if dlg.exec_() == QtWidgets.QDialog.Accepted else ""
        if d:
            self._set_folder(d)

    def _alte_ablage_melden(self, verschoben, geblieben):
        """Meldet im Protokoll, was beim Oeffnen umgeraeumt wurde."""
        if verschoben:
            self._on_log(self._t(
                f"purelapse@engine:~$ {len(verschoben)} Dateien aus einer aelteren Version "
                f"in den Ordner {PL_ORDNER} verschoben: " + ", ".join(verschoben[:6])
                + (" ..." if len(verschoben) > 6 else ""),
                f"purelapse@engine:~$ Moved {len(verschoben)} files from an older version "
                f"into the {PL_ORDNER} folder: " + ", ".join(verschoben[:6])
                + (" ..." if len(verschoben) > 6 else "")))
        if geblieben:
            self._on_log(self._t(
                f"> HINWEIS: {len(geblieben)} aeltere Dateien blieben im Bilderordner, weil im "
                f"Ordner {PL_ORDNER} schon gleichnamige liegen: " + ", ".join(geblieben[:6]),
                f"> NOTE: {len(geblieben)} older files stayed in the image folder because the "
                f"{PL_ORDNER} folder already holds files of the same name: " + ", ".join(geblieben[:6])))

    def _set_folder(self, path):
        self.target_dir = os.path.abspath(path)
        self.lbl_path.setText(self.target_dir)
        # Das Video des letzten Laufs gehoert zum alten Ordner - sonst oeffnete
        # "Ordner oeffnen" nach einem Ordnerwechsel weiter den alten.
        self.last_output_dir = ""
        self._alte_ablage_melden(*alte_ablage_umraeumen(self.target_dir))
        save_last_path(self.target_dir)
        b_alt = lade_bereiche().get(self.target_dir) or ["", ""]
        self._bereich = (b_alt[0] or None, (b_alt[1] if len(b_alt) > 1 else "") or None)
        # Der Ablauf des letzten Laufs gehoert zum alten Ordner.
        if not self._is_busy():
            self._ablauf = None
            self._ablauf_zeigen()
        self.roi_rel = None
        self.cam_keyframes = None
        self.lbl_cam_status.setText("Standard (Mitte)")
        zustand_setzen(self.lbl_cam_status, "", 'art')
        self.btn_roi.setText(self._tab(" [+] Messbereich (ROI) festlegen"))
        self.btn_roi.setStyleSheet("")
        # Die Engine nur dann umstellen, wenn die eingestellte in diesem
        # Ordner nichts vorfindet. Vorher wurde gegen eine Modul-globale
        # verglichen, die seit dem Import auf 'art' stand - dadurch
        # wechselte die Engine auch dann, wenn sie schon richtig stand.
        erkannt = detect_engine(self.target_dir)
        aktuell = engine_key()
        eigene = bool(glob.glob(os.path.join(self.target_dir,
                                             "*" + ENGINES[aktuell]['ext']))
                      + glob.glob(os.path.join(self.target_dir,
                                               "*" + ENGINES[aktuell]['ext'].upper())))
        if erkannt and erkannt != aktuell and not eigene:
            idx = {'art': 0, 'rt': 1, 'dt': 2}.get(erkannt, 0)
            self.cmb_engine.setCurrentIndex(idx)
            self._on_log(self._t(
                f"purelapse@engine:~$ Nur {ENGINES[erkannt]['label']}-"
                "Begleitdateien gefunden, Engine von "
                f"{ENGINES[aktuell]['label']} auf "
                f"{ENGINES[erkannt]['label']} umgestellt.",
                f"purelapse@engine:~$ Only {ENGINES[erkannt]['label']} "
                "sidecars found, engine switched from "
                f"{ENGINES[aktuell]['label']} to "
                f"{ENGINES[erkannt]['label']}."))
        jpg = glob.glob(os.path.join(self.target_dir, "*.jpg")) + glob.glob(os.path.join(self.target_dir, "*.JPG"))
        nef = find_raw_files(self.target_dir)
        self.lbl_count.setText(self._t(f"Ordner gewählt: {len(jpg)} JPG(s) und {len(nef)} NEF(s) gefunden.",
                                       f"Folder selected: {len(jpg)} JPG(s) and {len(nef)} NEF(s) found."))
        self._gps_from_exif(files=(nef if nef else jpg), silent=True)
        self._auto_step = True   # nach dem Einlesen den passenden Schritt zeigen
        self._refresh_preview()

    def _on_engine_changed(self, idx=None):
        # 3-Wege-Zuordnung statt vorher nur 2 (art/rt).
        mapping = {0: 'art', 1: 'rt', 2: 'dt'}
        key = mapping.get(self.cmb_engine.currentIndex(), 'art')
        set_engine(key)
        self.txt_art_path.setText(get_art_path())
        self.txt_arp_template.setText(get_arp_template_path())
        self.lbl_art_path.setText(self._t(f"{eng('label')}-Programm:",
                                          f"{eng('label')} program:"))
        self.lbl_arp_tpl.setText(self._t(f"{eng('label')}-Basisprofil:",
                                         f"{eng('label')} base profile:"))
        # Basisprofil-Zeile blendet sich bei Darktable aus, dafuer erscheint
        # der Hinweistext.
        ist_dt = (key == 'dt')
        for w in (self.lbl_arp_tpl, self.txt_arp_template, self.btn_arp_browse):
            w.setVisible(not ist_dt)
        self.lbl_dt_note.setVisible(ist_dt)
        if self.target_dir:
            anders = self._sterne_abgleichen()
            if anders:
                self._on_log("> " + self._t(
                    f"HINWEIS: Mit {eng('label')} gelten {anders} Bilder anders als bisher "
                    "angezeigt als Keyframe - die Sterne in der Bildleiste sind angepasst.",
                    f"NOTE: With {eng('label')}, {anders} images count differently as keyframes "
                    "than shown so far - the stars in the gallery have been updated."))
            self._recount_keyframes()
        if hasattr(self, 'btn_start'):
            self._update_steps()
            self._update_summary()

    def _browse_art_cli(self):
        start_dir = os.path.dirname(self.txt_art_path.text()) if os.path.exists(self.txt_art_path.text()) else os.path.expanduser("~")
        with self.abdunkler.halten():
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, self._t(f"{eng('bin')} ausführbare Datei wählen",
                              f"Choose the {eng('bin')} executable"),
                start_dir)
        if path and os.path.isfile(path):
            self.txt_art_path.setText(path)
            save_art_path(path)
            self._engine_anzeigen()

    def _browse_arp_template(self):
        if eng('kind') == 'darktable':
            return  # Basisprofil-Konzept gibt es bei Darktable nicht
        start_dir = self.target_dir or os.path.expanduser("~")
        with self.abdunkler.halten():
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, self._t("Basisprofil wählen", "Choose base profile"), start_dir,
                self._t(f"{eng('label')}-Profile (*{eng('ext')});;Alle Dateien (*)",
                        f"{eng('label')} profiles (*{eng('ext')});;All files (*)"))
        if not path or not os.path.isfile(path):
            return
        if not profile_is_complete(read_arp_dict(path)):
            QtWidgets.QMessageBox.warning(
                self, self._t("Unbrauchbares Profil", "Unusable profile"),
                self._t("Diese Datei enthält kein vollständiges Profil (kein [Version]-Block).\n\n"
                        f"Bitte in {eng('label')} ein Bild öffnen und über 'Profil speichern' "
                        "eine Vorlage anlegen.",
                        "This file does not contain a complete profile (no [Version] block).\n\n"
                        f"Please open an image in {eng('label')} and create a template via "
                        "'save profile'."))
            return
        self.txt_arp_template.setText(path)
        save_arp_template_path(path)

    def _on_export_dir_changed(self, idx):
        if idx == 3:
            self.btn_custom_dir.setVisible(True)
            self._choose_custom_dir()
        else:
            self.btn_custom_dir.setVisible(False)

    def _choose_custom_dir(self):
        start = self.custom_out_dir or self.target_dir or os.path.expanduser("~")
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, self._t("Export-Ordner wählen", "Choose export folder"), start, options=options)
        if d:
            self.custom_out_dir = os.path.abspath(d)
        else:
            self.cmb_export_dir.setCurrentIndex(0)

    def _referenzbild(self):
        """
        Das Bild, an dem Messbereich und Bildausschnitt eingestellt werden:
        das in der Bildleiste gewaehlte, sofern es im Arbeitsbereich liegt,
        sonst das Startbild. Nie ein Bild ausserhalb des Bereichs - die
        Bilder davor sind oft gerade die unbrauchbaren.
        """
        files = self._arbeitsdateien()
        if not files:
            return None
        zeile = self.list_widget.currentRow()
        if 0 <= zeile < len(self.tiles):
            name = self.tiles[zeile].get('name')
            for f in files:
                if os.path.basename(f) == name:
                    return f
        return files[0]

    def _open_camera_path_dialog(self):
        files = self._arbeitsdateien()
        if not files:
            QtWidgets.QMessageBox.warning(self, self._t("Fehler", "Error"),
                                          self._t("Bitte wähle zuerst einen Ordner mit Bildern aus.",
                                                  "Please choose a folder with images first."))
            return
        try:
            dlg = CameraPathDialog(self._referenzbild() or files[0], self.cam_keyframes,
                                   self, self.lang)
        except (ValueError, cv2.error) as e:
            QtWidgets.QMessageBox.warning(
                self, "Fehler" if self.lang == 'de' else "Error",
                ("Das erste Bild konnte nicht geladen werden.\n\n" if self.lang == 'de'
                 else "The first image could not be loaded.\n\n") + str(e))
            return
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.cam_keyframes = dlg.kf
            def r(values):
                return [round(x, 3) for x in values]
            if r(self.cam_keyframes['start']) == r(self.cam_keyframes['end']):
                self.lbl_cam_status.setText(self._t("Statisch (Festgelegter 16:9 Crop)",
                                                    "Static (fixed 16:9 crop)"))
                zustand_setzen(self.lbl_cam_status, "fest", 'art')
            else:
                self.lbl_cam_status.setText(self._t("Dynamisch (Start \u2192 Ende)",
                                                    "Dynamic (start \u2192 end)"))
                zustand_setzen(self.lbl_cam_status, "aktiv", 'art')

    def _select_roi(self):
        if not self._jpg_files and not self._nef_files:
            return
        f = self._referenzbild()
        if f is None:
            return
        bgr = load_preview_image(f, max_width=1000)
        if bgr is None:
            QtWidgets.QMessageBox.warning(
                self, "Fehler" if self.lang == 'de' else "Error",
                "Das Bild konnte nicht geladen werden." if self.lang == 'de'
                else "The image could not be loaded.")
            return
        img = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        h, w, ch = img.shape
        bpl = ch * w
        qimg = QtGui.QImage(img.data, w, h, bpl, QtGui.QImage.Format_RGB888).copy()
        dlg = ROIDialog(qimg, self, self.lang)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            if dlg.roi_rel and dlg.roi_rel[2] > 0.05 and dlg.roi_rel[3] > 0.05:
                self.roi_rel = dlg.roi_rel
                self.btn_roi.setText(self._tab(" [✔] Messbereich (ROI) ist AKTIV! (Klick = neu)"))
                t_roi = self._farben()
                self.btn_roi.setStyleSheet(
                    f"border: 1px solid {t_roi['accent']}; color: {t_roi['accent']};")
            else:
                self.roi_rel = None
                self.btn_roi.setText(self._tab(" [+] Messbereich (ROI) festlegen"))
                self.btn_roi.setStyleSheet("")
            self._refresh_preview()

    def _refresh_preview(self):
        if not self.target_dir or not os.path.isdir(self.target_dir):
            return
        t = THEMES[self.theme]
        self.graph.setTitle(f'<span style="color:{t["warn"]};">'
                            + self._t("Lese Bilder ein…", "Reading images…") + '</span>')
        self.list_widget.clear()
        self.tiles = []
        self._sel_row = -1
        self._hl_werte = []
        if getattr(self, 'sicht_band', None) is not None:
            self.sicht_band.setVisible(False)
        self._tile_last = 0
        self.luma_history.clear()
        for v in self.curves.values():
            v.clear()
        self.curves['residual'] = load_residuals(self.target_dir)
        self.frames_x.clear()
        for m in getattr(self, 'kf_marker', []):
            self.graph.removeItem(m)
        self.kf_marker = []
        for m in self.sun_marker:
            self.graph.removeItem(m)
        self.sun_marker = []
        if getattr(self, 'vb_wb', None) is not None:
            for m in self.sun_h_marker:
                self.vb_wb.removeItem(m)
        self.sun_h_marker = []
        self._exif_times = []
        self._sun_crossings = []
        if self.plot_wb is not None:
            self.plot_wb.setData([], [])
        self.plot_raw.setData([], [])
        self.plot_smooth.setData([], [])
        if self.gallery_worker and self.gallery_worker.isRunning():
            # Nicht unbegrenzt warten: ein gerade dekodiertes RAW kann eine
            # Sekunde dauern, und so lange stand die Oberflaeche. Laeuft der
            # alte Lader noch, wird er stummgeschaltet und darf im
            # Hintergrund zu Ende laufen - seine Bilder gehoeren zum alten
            # Ordner und duerfen nicht mehr ankommen.
            self.gallery_worker._abort = True
            if not self.gallery_worker.wait(300):
                self.gallery_worker.blockSignals(True)
                rest = [w for w in getattr(self, '_alte_lader', []) if w.isRunning()]
                self._alte_lader = rest + [self.gallery_worker]
        self.lbl_gaps.setVisible(False)
        self.lbl_clip.setVisible(False)
        self.lbl_farbstich.setVisible(False)
        self._last_clip = None
        if self.btn_kf_filter.isChecked():
            self.btn_kf_filter.blockSignals(True)
            self.btn_kf_filter.setChecked(False)
            self.btn_kf_filter.blockSignals(False)
            self.btn_kf_filter.setText(self._t("★ nur Keyframes",
                                               "★ keyframes only"))
        self.btn_kf_edit.setEnabled(False)
        self.progress.setValue(0)
        if getattr(self, 'lade_schirm', None) is not None:
            self.lade_schirm.zeige(self.target_dir, self.lang)
        self.gallery_worker = GalleryWorker(self.target_dir, self.roi_rel, lang=self.lang)
        # Jeder Ladelauf bekommt eine Nummer. Signale, die ein abgeloester
        # Lader schon abgeschickt hatte, kommen sonst noch nach dem Leeren
        # der Bildleiste an - und haengen alte Kacheln vor die neuen: aus
        # 2 Keyframes wurden kurz 4, und die Zeilen passten nicht mehr zum
        # Diagramm. blockSignals() hilft dagegen nicht, es haelt nur kuenftige
        # Signale auf, keine, die schon in der Warteschlange stehen.
        self._galerie_lauf = getattr(self, '_galerie_lauf', 0) + 1
        lauf = self._galerie_lauf

        def nur_aktuell(slot):
            return lambda *a: slot(*a) if lauf == self._galerie_lauf else None
        w = self.gallery_worker
        w.scan_done.connect(nur_aktuell(self._on_scan_done))
        w.gaps_found.connect(nur_aktuell(self._on_gaps_found))
        w.curves_ready.connect(nur_aktuell(self._on_curves_ready))
        w.status.connect(nur_aktuell(self._on_gallery_status))
        w.progress.connect(nur_aktuell(self._on_gallery_progress))
        w.image_ready.connect(nur_aktuell(self._on_image_ready))
        w.finished_loading.connect(nur_aktuell(self._on_finished_loading))
        w.start()

    def _on_gallery_status(self, text):
        """Zeigt Zaehlerstand und ETA waehrend des Einlesens an."""
        t = THEMES[self.theme]
        self.graph.setTitle(f'<span style="color:{t["warn"]};">{text}</span>')
        self.lbl_status.setText(text)

    def _on_gallery_progress(self, done, total):
        if getattr(self, 'lade_schirm', None) is not None and self.lade_schirm.isVisible():
            self.lade_schirm.stand(done, total, self.lbl_status.text())
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(done)

    def _on_scan_done(self, num_jpg, num_nef, jpg, nef, num_keys):
        self._jpg_files = jpg
        self._nef_files = nef
        if not jpg and not nef and getattr(self, 'lade_schirm', None) is not None:
            self.lade_schirm.hide()          # leerer Ordner: nichts zu laden
        key_text = (self._t(f" | ★ {num_keys} bearbeitete Keyframes",
                            f" | ★ {num_keys} edited keyframes") if num_keys > 0
                    else self._t(" | Keine Keyframes gefunden", " | No keyframes found"))
        self.lbl_count.setText(self._t(f"Gefunden: {num_jpg} JPG(s) und {num_nef} NEF(s)",
                                       f"Found: {num_jpg} JPG(s) and {num_nef} NEF(s)") + key_text)
        self._kf_count = num_keys
        if num_nef > 0 and num_jpg == 0:
            self.rb_raw.setChecked(True)
        elif num_jpg > 0 and num_nef == 0:
            self.rb_jpg.setChecked(True)   # reiner JPG-Ordner: RAW waere leer
        self._update_filesize_estimate()
        if self._auto_step:
            self._auto_step = False
            self._pick_step_for_folder()
        else:
            self._update_steps()
            self._update_summary()

    def _on_curves_ready(self, daten):
        """Nimmt die aus den EXIF-Daten gewonnenen Kurven entgegen."""
        for schluessel in ('ev', 'interval'):
            if schluessel in daten:
                self.curves[schluessel] = list(daten[schluessel])
        self._exif_times = daten.get('times', [])
        self._recompute_sun_curve()
        self._redraw_graph()

    def _on_gaps_found(self, gaps, basis):
        self._last_gaps = (gaps, basis)
        lo, mid, hi = basis
        if hi > lo * 1.5:
            intervall = self._t(
                f"Intervall laeuft von {lo:.0f}s auf {hi:.0f}s (bei Holy Grail normal)",
                f"Interval ramps from {lo:.0f}s to {hi:.0f}s (normal for holy grail)")
        else:
            intervall = self._t(f"Intervall {mid:.0f}s", f"Interval {mid:.0f}s")
        if not gaps:
            text = self._t(f"{intervall} - keine fehlenden Bilder.",
                           f"{intervall} - no missing frames.")
            kurz, tip = "·  " + text, ""
            self._gaps_warn = False
        else:
            fehlend = sum(g[2] for g in gaps)
            teile = [self._t(f"vor Bild {i}: {k} fehlt" if k == 1 else
                             f"vor Bild {i}: {k} fehlen",
                             f"before frame {i}: {k} missing") + f" ({d:.0f}s)"
                     for i, d, k in gaps[:25]]
            liste = "; ".join(teile)
            if len(gaps) > 25:
                liste += self._t(f"; ... und {len(gaps) - 25} weitere Stellen",
                                 f"; ... and {len(gaps) - 25} more places")
            text = self._t(
                f"⚠ {fehlend} fehlende Aufnahme(n) an {len(gaps)} Stelle(n). "
                f"{intervall}. {liste}",
                f"⚠ {fehlend} missing frame(s) at {len(gaps)} place(s). "
                f"{intervall}. {liste}")
            # Kurze Warnmarke; die Einzelheiten stehen im Tooltip und im Protokoll.
            kurz = self._t(f"⚠ {fehlend} Bild fehlt" if fehlend == 1 else
                           f"⚠ {fehlend} Bilder fehlen",
                           f"⚠ {fehlend} frame missing" if fehlend == 1 else
                           f"⚠ {fehlend} frames missing")
            tip = self._t(f"{fehlend} fehlende Aufnahme(n) an {len(gaps)} Stelle(n). {intervall}.",
                          f"{fehlend} missing frame(s) at {len(gaps)} place(s). {intervall}.") \
                + "\n" + liste.replace("; ", "\n")
            self._gaps_warn = True
        self.lbl_gaps.setText(kurz)
        self.lbl_gaps.setToolTip(tip)
        self._style_gaps()
        self.lbl_gaps.setVisible(True)
        self._on_log("purelapse@engine:~$ " + text)
        self._style_clip()

    def _style_gaps(self):
        t = THEMES[self.theme]
        if getattr(self, '_gaps_warn', False):
            self.lbl_gaps.setStyleSheet(
                f"color: {t['warn']}; border: 1px solid {t['warn']};"
                " border-radius: 9px; padding: 1px 9px; font-weight: bold;")
        else:
            self.lbl_gaps.setStyleSheet(f"color: {t['dim']};")

    def _style_tile(self, widget, is_keyframe, ausgewaehlt=False):
        """
        Rahmen und Hintergrund einer Kachel.

        Keyframes bekommen einen farbigen Rahmen. Die ausgewaehlte Kachel
        bekommt zusaetzlich einen eingefaerbten Hintergrund - ohne den
        waere die Auswahl unsichtbar, weil das Kachel-Widget ueber dem
        Listeneintrag liegt und dessen Markierung verdeckt.
        """
        t = THEMES[self.theme]
        if is_keyframe:
            farbe = t['curves']['kf']
        elif ausgewaehlt:
            farbe = t['accent']
        else:
            farbe = 'transparent'
        hintergrund = f" background: {t['sel']};" if ausgewaehlt else ""
        widget.setStyleSheet(f"#tile {{ border: 2px solid {farbe};"
                             f" border-radius: 6px;{hintergrund} }}")

    def _markiere_auswahl(self, row):
        """
        Faerbt die gewaehlte Kachel um.

        Nur die vorher und die jetzt gewaehlte Kachel werden angefasst;
        bei tausend Bildern waere ein Durchlauf ueber alle Kacheln bei
        jedem Klick traege.
        """
        vorher = getattr(self, '_sel_row', -1)
        for i in {vorher, row}:
            if 0 <= i < len(self.tiles):
                t = self.tiles[i]
                chk = t.get('chk')
                self._style_tile(t['widget'],
                                 bool(chk.isChecked()) if chk is not None else False,
                                 i == row)
        self._sel_row = row

    def _arbeitsdateien(self, is_raw=None):
        """Die Bilder, mit denen gearbeitet wird: Startbild bis Endbild."""
        if is_raw is None:
            is_raw = self.rb_raw.isChecked()
        files = self._nef_files if is_raw else self._jpg_files
        start, ende = getattr(self, '_bereich', (None, None))
        return bereich_anwenden(files, start, ende)[0]

    def _setze_bereich(self, welches):
        """Macht das gewaehlte Bild zum Start- oder Endbild."""
        zeile = self.list_widget.currentRow()
        if not self.target_dir or not (0 <= zeile < len(self.tiles)) or self._is_busy():
            return
        namen = [t['name'] for t in self.tiles]
        start, ende = self._bereich
        if welches == 'start':
            start = None if zeile == 0 else namen[zeile]
        else:
            ende = None if zeile == len(namen) - 1 else namen[zeile]
        a = namen.index(start) if start in namen else 0
        b = namen.index(ende) if ende in namen else len(namen) - 1
        if a > b:
            self.lbl_status.setText(self._t(
                "Das Startbild muss vor dem Endbild liegen.",
                "The start frame must come before the end frame."))
            return
        self._bereich = (start, ende)
        speichere_bereich(self.target_dir, start, ende)
        self._bereich_zeigen()
        self._update_filesize_estimate()
        self._update_summary()
        self._on_log("purelapse@engine:~$ " + self._t(
            f"Arbeitsbereich: Bild {a + 1} bis {b + 1} von {len(namen)} "
            f"({b - a + 1} Bilder). Bitte Pass 1 neu laufen lassen.",
            f"Working range: frame {a + 1} to {b + 1} of {len(namen)} "
            f"({b - a + 1} frames). Please run pass 1 again."))

    def _bereich_zeigen(self):
        """Blendet die ausgeschlossenen Kacheln ab und nennt den Bereich."""
        if not hasattr(self, 'lbl_bereich'):
            return
        namen = [t['name'] for t in self.tiles]
        start, ende = getattr(self, '_bereich', (None, None))
        a = namen.index(start) if start in namen else 0
        b = namen.index(ende) if ende in namen else len(namen) - 1
        if a > b:
            a, b = 0, len(namen) - 1
        for i, t in enumerate(self.tiles):
            draussen = i < a or i > b
            if draussen == bool(t.get('draussen', False)):
                continue
            t['draussen'] = draussen
            if draussen:
                effekt = QtWidgets.QGraphicsOpacityEffect(t['widget'])
                effekt.setOpacity(0.28)
                t['widget'].setGraphicsEffect(effekt)
            else:
                t['widget'].setGraphicsEffect(None)
        if namen and (a > 0 or b < len(namen) - 1):
            self.lbl_bereich.setText(self._t(
                f"Arbeitsbereich: Bild {a + 1} \u2013 {b + 1} von {len(namen)}",
                f"Working range: frame {a + 1} \u2013 {b + 1} of {len(namen)}"))
            self.lbl_bereich.setVisible(True)
        else:
            self.lbl_bereich.setVisible(False)

    def _springe_zu(self, ziel):
        """Waehlt das erste (0) oder letzte (-1) sichtbare Bild und rollt
        die Bildleiste dorthin."""
        sichtbar = [i for i, t in enumerate(self.tiles)
                    if not t['item'].isHidden()]
        if not sichtbar:
            return
        zeile = sichtbar[0] if ziel == 0 else sichtbar[-1]
        self.list_widget.setCurrentRow(zeile)
        self.list_widget.scrollToItem(self.tiles[zeile]['item'])

    def _row_of_widget(self, obj):
        """
        Zu welcher Kachel gehoert das angeklickte Widget?

        Der Klick landet je nach Stelle auf dem Vorschaubild, der
        Beschriftung, dem Kaestchen oder der Kachel selbst. Deshalb wird
        von dort aus nach oben gesucht, bis die Kachel mit ihrer
        hinterlegten Zeilennummer gefunden ist.
        """
        w = obj if isinstance(obj, QtWidgets.QWidget) else None
        for _ in range(6):
            if w is None:
                break
            r = w.property("tile_row")
            if r is not None:
                try:
                    return int(r)
                except (TypeError, ValueError):
                    return None
            w = w.parentWidget()
        return None

    def _on_image_ready(self, index, filename, qimg, daten):
        luma = float(daten.get('luma', 0.0))
        is_keyframe = bool(daten.get('kf', False))
        widget = QtWidgets.QWidget()
        widget.setObjectName("tile")
        widget.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self._style_tile(widget, is_keyframe)
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 3)
        layout.setSpacing(1)
        lbl_img = QtWidgets.QLabel()
        lbl_img.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(lbl_img)
        lbl_txt = QtWidgets.QLabel(filename)
        lbl_txt.setAlignment(QtCore.Qt.AlignCenter)
        lbl_txt.setWordWrap(True)
        # Der Stern ist das Keyframe-Kaestchen: anklicken markiert das Bild.
        chk_kf = QtWidgets.QCheckBox("")
        chk_kf.setObjectName("stern")
        chk_kf.setToolTip(self._t("Als Keyframe markieren", "Mark as keyframe"))
        if is_keyframe:
            chk_kf.setStyleSheet("color: #ffcc00; font-weight: bold; font-size: 10px;")
            lbl_txt.setStyleSheet("color: #ffcc00; font-weight: bold; font-size: 10px;")
        else:
            chk_kf.setStyleSheet("color: #888888; font-size: 10px;")
            lbl_txt.setStyleSheet("color: #cccccc; font-size: 10px;")
        chk_kf.setChecked(is_keyframe)
        chk_kf.toggled.connect(lambda checked, f=filename, l=lbl_txt, c=chk_kf: self._toggle_keyframe_status(checked, f, l, c))
        # Die Zeilennummer steht erst weiter unten an der Kachel; sie wird
        # deshalb beim Umschalten aus dem Widget gelesen, nicht hier
        # eingefangen - sonst waere sie zum Zeitpunkt dieser Zeile noch
        # gar nicht vergeben.
        chk_kf.toggled.connect(
            lambda checked, w=widget:
            self._style_tile(w, checked,
                             w.property("tile_row") == getattr(self, '_sel_row', -1)))
        chk_kf.toggled.connect(lambda _c: self._update_kf_buttons())
        chk_kf.toggled.connect(
            lambda _c: self._on_filter_keyframes(True)
            if self.btn_kf_filter.isChecked() else None)
        layout.addWidget(lbl_txt)
        # Unter dem Namen: links die Warnzeichen dieses Bildes, rechts der
        # Stern.
        fuss = QtWidgets.QHBoxLayout()
        fuss.setContentsMargins(2, 0, 2, 0)
        fuss.setSpacing(4)
        nummer = QtWidgets.QLabel(str(index + 1))
        nummer.setStyleSheet(f"color: {THEMES[self.theme]['dim']}; font-size: 10px;")
        nummer.setToolTip(self._t(f"Bild {index + 1}", f"Frame {index + 1}"))
        fuss.addWidget(nummer)
        t_k = THEMES[self.theme]
        if float(daten.get('clip', 0.0)) > CLIP_SCHWELLE_VORSCHAU:
            m = QtWidgets.QLabel("\u25b2")
            m.setStyleSheet(f"color: {t_k['warn']}; font-size: 11px;")
            m.setToolTip(self._t("Ausgefressene Lichter (vorlaeufig, aus dem "
                                 "Vorschaubild)", "Blown highlights "
                                 "(preliminary, from the preview)"))
            fuss.addWidget(m)
        if float(daten.get('hl_bunt', 0.0)) > 0.15:
            m = QtWidgets.QLabel("\u25cf")
            m.setStyleSheet(f"color: {t_k['curves']['ev']}; font-size: 11px;")
            m.setToolTip(self._t("Verfaerbte Lichter - Abhilfe: im Keyframe "
                                 "'Lichter rekonstruieren' einschalten",
                                 "Tinted highlights - remedy: switch on "
                                 "'reconstruct highlights' in a keyframe"))
            fuss.addWidget(m)
        fuss.addStretch()
        fuss.addWidget(chk_kf)
        layout.addLayout(fuss)
        item = QtWidgets.QListWidgetItem(self.list_widget)
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)
        # Zeilennummer an der Kachel hinterlegen und alle ihre Teile
        # abhoeren, damit ein Klick die Zeile auswaehlt. Ohne das bliebe
        # currentRow() bei -1 und die Kachelknoepfe waeren immer gesperrt.
        zeile = len(self.tiles)
        widget.setProperty("tile_row", zeile)
        widget.installEventFilter(self)
        for kind in widget.findChildren(QtWidgets.QWidget):
            kind.installEventFilter(self)
        self.tiles.append({'item': item, 'widget': widget,
                           'img': lbl_img, 'qimg': qimg,
                           'chk': chk_kf, 'name': filename})
        self._resize_tile(self.tiles[-1], self._tile_width())
        self.frames_x.append(index)
        self.luma_history.append(luma)
        self.curves['wb'].append(float(daten.get('wb', 0.0)))
        self.curves['clip'].append(float(daten.get('clip', 0.0)))
        self._hl_werte.append(float(daten.get('hl_bunt', 0.0)))
        if is_keyframe:
            line = self._kf_linie(index)
            self.graph.addItem(line)
            self.kf_marker.append(line)
        if index % 25 == 0:
            self.plot_raw.setData(self.frames_x, self.luma_history)

    TILE_MIN = 104
    TILE_MAX = 240

    def _tile_width(self):
        rand = self.list_widget.spacing()
        breite = max(self.TILE_MIN, self.list_widget.viewport().width() - 4)
        spalten = max(1, int((breite - rand) // (self.TILE_MIN + rand)))
        kachel = int((breite - rand * (spalten + 1)) / spalten)
        return max(self.TILE_MIN, min(self.TILE_MAX, kachel))

    def _resize_tile(self, eintrag, breite):
        qimg = eintrag['qimg']
        bild_b = max(16, breite - 12)
        if qimg.width() > 0:
            bild_h = int(bild_b * qimg.height() / qimg.width())
        else:
            bild_h = bild_b
        eintrag['img'].setPixmap(QtGui.QPixmap.fromImage(qimg).scaled(
            bild_b, bild_h, QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation))
        gesamt = bild_h + 48
        eintrag['widget'].setFixedSize(breite, gesamt)
        eintrag['item'].setSizeHint(QtCore.QSize(breite, gesamt))

    def _relayout_gallery(self):
        if not self.tiles:
            return
        breite = self._tile_width()
        if breite == getattr(self, '_tile_last', 0):
            return
        self._tile_last = breite
        for eintrag in self.tiles:
            self._resize_tile(eintrag, breite)
        self.list_widget.doItemsLayout()
        self._band_timer.start()

    def _zeilen_abstand(self):
        """
        Abstand von einer Kachelreihe zur naechsten, in Pixeln.

        Aus der Lage der ersten Kachel und der ersten Kachel, die tiefer
        liegt - so stimmt er auch mit Rand und Zwischenraum.
        """
        oben = None
        for t in self.tiles:
            if t['item'].isHidden():
                continue
            r = self.list_widget.visualItemRect(t['item'])
            if oben is None:
                oben = r.top()
            elif r.top() > oben:
                return int(r.top() - oben)
        return 0

    def _gallerie_einrasten(self, wert=None):
        """
        Laesst die Bildleiste nur um ganze Reihen rollen.

        Die Kacheln stehen dadurch immer an denselben Plaetzen, beim Rollen
        wechselt nur ihr Inhalt - wie beim Daumenkino sieht man den Verlauf
        der Sequenz, statt die Bilder vorbeiziehen zu sehen.
        """
        if getattr(self, '_rastet', False):
            return
        sb = self.list_widget.verticalScrollBar()
        schritt = self._zeilen_abstand()
        if schritt <= 0:
            return
        wert = sb.value() if wert is None else int(wert)
        hoechst = sb.maximum()
        if wert >= hoechst:
            return
        ziel = min(hoechst, int(round(wert / float(schritt))) * schritt)
        if ziel != wert:
            self._rastet = True
            try:
                sb.setValue(ziel)
            finally:
                self._rastet = False

    def _gallerie_rad(self, delta):
        """Mausrad: eine Raste = eine Kachelreihe. Feine Schritte eines
        Touchpads werden gesammelt, bis eine ganze Raste voll ist."""
        schritt = self._zeilen_abstand()
        if schritt <= 0:
            return False
        self._rad_rest = getattr(self, '_rad_rest', 0) + int(delta)
        rasten = int(self._rad_rest / 120)
        if rasten:
            self._rad_rest -= rasten * 120
            sb = self.list_widget.verticalScrollBar()
            sb.setValue(sb.value() - rasten * schritt)
        return True

    def eventFilter(self, obj, event):
        if obj is self.list_widget.viewport() and event.type() == QtCore.QEvent.Resize:
            self._tile_timer.start(80)
        if (obj is self.list_widget.viewport()
                and event.type() == QtCore.QEvent.Wheel):
            try:
                delta = event.angleDelta().y()
            except Exception:
                delta = 0
            if delta and self._gallerie_rad(delta):
                return True
        typ = event.type()
        if typ in (QtCore.QEvent.MouseButtonPress,
                   QtCore.QEvent.MouseButtonDblClick):
            row = self._row_of_widget(obj)
            if row is not None:
                if row != self.list_widget.currentRow():
                    self.list_widget.setCurrentRow(row)
                else:
                    # Gleiche Zeile: currentRowChanged feuert nicht, die
                    # Knoepfe muessen trotzdem stimmen.
                    self._update_kf_buttons()
                if (typ == QtCore.QEvent.MouseButtonDblClick
                        and self.btn_kf_edit.isEnabled()):
                    QtCore.QTimer.singleShot(0, self._open_quick_dialog)
        # Nicht abfangen: das Kaestchen und die Kachel sollen den Klick
        # weiterhin bekommen.
        return super().eventFilter(obj, event)

    def _toggle_keyframe_status(self, checked, filename, lbl_txt, chk_kf):
        full_path = os.path.join(self.target_dir, filename)
        arp_path = sidecar(full_path)
        if checked:
            lbl_txt.setStyleSheet("color: #ffcc00; font-weight: bold; font-size: 10px;")
            chk_kf.setStyleSheet("color: #ffcc00; font-weight: bold; font-size: 10px;")
        else:
            lbl_txt.setStyleSheet("color: #cccccc; font-size: 10px;")
            chk_kf.setStyleSheet("color: #888888; font-size: 10px;")
        if getattr(self, '_sterne_sync', False):
            return      # nur Anzeige nachziehen - die Dateien stimmen schon
        # Rank im INI-Profil nur bei ART/RawTherapee. Bei Darktable wuerde
        # write_arp_dict ein Belichtungsmodul in den Verlauf schreiben.
        if eng('kind') == 'ini' and os.path.exists(arp_path):
            arp_data = read_arp_dict(arp_path)
            for sec in arp_data:
                arp_data[sec].pop('Rank', None)
                arp_data[sec].pop('Rating', None)
            arp_data.setdefault('General', {})['Rank'] = '5' if checked else '0'
            try:
                write_arp_dict(arp_path, arp_data)
            except OSError as fehler:
                self._on_log("> " + self._t(f"FEHLER: {fehler}", f"ERROR: {fehler}"))
        # Die Bewertung in die .xmp des Bildes - bei Darktable ist das die
        # Begleitdatei selbst, sonst eine Zusatzdatei. bewertung_schreiben
        # aendert in einer vorhandenen Datei nur die Bewertung.
        bewertung_schreiben(f"{full_path}.xmp", 5 if checked else 0)
        if eng('kind') == 'darktable' and not getattr(self, '_dt_stern_gemeldet', False):
            # Einmal je Programmlauf: sonst wundert man sich, warum die
            # Sterne in Darktable nicht auftauchen.
            self._dt_stern_gemeldet = True
            self._on_log("> " + self._t("HINWEIS: ", "NOTE: ")
                         + DT_STERNE_HINWEIS['en' if self.lang == 'en' else 'de'])
        self._recount_keyframes()

    def _sterne_abgleichen(self):
        """
        Liest die Keyframe-Sterne der Bildleiste neu aus den Begleitdateien.

        Ob ein Bild Keyframe ist, haengt von der Engine ab: bei RawTherapee
        und ART zaehlt auch "Rank=5" im Profil, bei Darktable nur die .xmp.
        Nach einem Engine-Wechsel zeigte die Bildleiste sonst noch die alten
        Sterne, waehrend Zaehler und Entwicklung schon die neuen nahmen -
        oben "8 Keyframes", im Filter 4. Geschrieben wird dabei nichts.
        Rueckgabe: Zahl der geaenderten Sterne.
        """
        if not self.target_dir or not self.tiles:
            return 0
        anders = 0
        self._sterne_sync = True
        try:
            for t in self.tiles:
                chk, name = t.get('chk'), t.get('name')
                if chk is None or not name:
                    continue
                ist = check_is_keyframe(sidecar(os.path.join(self.target_dir, name)))
                if chk.isChecked() != ist:
                    chk.setChecked(ist)
                    anders += 1
        finally:
            self._sterne_sync = False
        return anders

    def _kf_linien_neu(self):
        """
        Zeichnet die Keyframe-Linien im Diagramm nach dem Stand der Sterne
        in der Bildleiste neu.

        Bisher entstanden die Linien nur beim Einlesen. Ein Stern, der
        danach gesetzt oder entfernt wurde, erschien im Diagramm erst nach
        "Aktualisieren" - oder gar nicht, wenn das Einlesen zwischendurch
        auf einen Teil der Bilder beschraenkt war.
        """
        if not hasattr(self, 'graph'):
            return
        for m in getattr(self, 'kf_marker', []):
            try:
                self.graph.removeItem(m)
            except Exception:
                pass
        self.kf_marker = []
        for i, t in enumerate(getattr(self, 'tiles', [])):
            chk = t.get('chk')
            if chk is None or not chk.isChecked() or i >= len(self.frames_x):
                continue
            line = self._kf_linie(self.frames_x[i])
            self.graph.addItem(line)
            self.kf_marker.append(line)

    def _recount_keyframes(self):
        self._kf_linien_neu()
        count = 0
        files = self._nef_files if self.rb_raw.isChecked() else self._jpg_files
        for f in files:
            if check_is_keyframe(sidecar(f)):
                count += 1
        num_jpg = len(self._jpg_files)
        num_nef = len(self._nef_files)
        key_text = (self._t(f" | ★ {count} bearbeitete Keyframes",
                            f" | ★ {count} edited keyframes") if count > 0
                    else self._t(" | Keine Keyframes ausgewählt", " | No keyframes selected"))
        self.lbl_count.setText(self._t(f"Gefunden: {num_jpg} JPG(s) und {num_nef} NEF(s)",
                                       f"Found: {num_jpg} JPG(s) and {num_nef} NEF(s)") + key_text)
        self._kf_count = count
        if hasattr(self, 'btn_start'):
            self._update_steps()
            self._update_summary()

    def _on_finished_loading(self):
        if getattr(self, 'lade_schirm', None) is not None:
            self.lade_schirm.hide()
        self._apply_theme(self.theme)
        self._redraw_graph()
        self._pruefe_lichter()
        self._update_kf_buttons()
        self._kf_linien_neu()
        self._bereich_zeigen()
        self._band_timer.start()
        self.progress.setValue(0)
        self.lbl_status.setText(self._t("Bereit.", "Ready."))

    def _pruefe_lichter(self):
        """Vorlaeufige Lichterwarnung aus den Vorschaubildern."""
        anzahl, gesamt, schlimmste = lichter_auswerten(
            self.curves.get('clip', []), CLIP_SCHWELLE_VORSCHAU)
        self._zeige_lichter(anzahl, gesamt, schlimmste, quelle='vorschau')
        self._pruefe_farbstich()

    def _pruefe_farbstich(self):
        """
        Meldet verfaerbte Lichter ueber die ganze Sequenz.

        Ein rosa Sonnenball ist kein Einzelfall - wenn er in einem Bild
        auftritt, steht er meist in Dutzenden. Deshalb gehoert die Zahl
        neben die Lueckenmeldung und nicht nur in den Keyframe-Dialog.
        """
        werte = getattr(self, '_hl_werte', [])
        betroffen = [i for i, v in enumerate(werte) if v > 0.15]
        self._last_farbstich = (len(betroffen), len(werte), betroffen[:25])
        if not werte or not betroffen:
            self.lbl_farbstich.setVisible(False)
            return
        n, ges = len(betroffen), len(werte)
        self.lbl_farbstich.setText(self._t(
            f"⚠ {n} Bilder mit verfärbten Lichtern",
            f"⚠ {n} frames with tinted highlights"))
        self.lbl_farbstich.setToolTip(self._t(
            f"In {n} von {ges} Bildern sind die hellsten Stellen farbig "
            "statt weiss - der rosa Sonnenball.\n\n"
            "Im Kern der Sonne steht Gruen zuerst am Anschlag, und die "
            "Faktoren des Weissabgleichs heben Rot und Blau danach weiter "
            "an. Eine negative Belichtungskorrektur hilft dagegen nicht.\n\n"
            "Abhilfe: ein Bild als Keyframe markieren, "
            "\u201eKeyframe einstellen\u201c oeffnen und dort "
            "\u201eLichter rekonstruieren\u201c einschalten. Die "
            "Interpolation traegt das auf die ganze Sequenz.\n\n"
            f"Betroffen ab Bild: {', '.join(str(i) for i in betroffen[:25])}"
            + (" ..." if n > 25 else ""),
            f"In {n} of {ges} frames the brightest areas are coloured "
            "instead of white - the pink sun disc.\n\nIn the sun's core "
            "green saturates first, and the white balance factors then "
            "lift red and blue further. Negative exposure compensation "
            "does not help.\n\nRemedy: mark a frame as a keyframe, open "
            "\u201cEdit keyframe\u201d and switch on \u201creconstruct "
            "highlights\u201d. Interpolation carries it across the "
            "sequence.\n\n"
            f"Affected from frame: {', '.join(str(i) for i in betroffen[:25])}"
            + (" ..." if n > 25 else "")))
        t = THEMES[self.theme]
        self.lbl_farbstich.setStyleSheet(
            f"color: {t['warn']}; border: 1px solid {t['warn']};"
            " border-radius: 9px; padding: 1px 9px; font-weight: bold;")
        self.lbl_farbstich.setVisible(True)
        self._on_log("purelapse@engine:~$ " + self._t(
            f"{n} von {ges} Bildern haben verfaerbte Lichter. Abhilfe: in "
            "einem Keyframe 'Lichter rekonstruieren' einschalten.",
            f"{n} of {ges} frames have tinted highlights. Remedy: switch "
            "on 'reconstruct highlights' in a keyframe."))

    def _on_clip_report(self, anzahl, gesamt, schlimmste):
        """Genaue Lichterwarnung aus den Messwerten von Pass 1."""
        self._zeige_lichter(anzahl, gesamt, [tuple(x) for x in schlimmste],
                            quelle='raw')

    def _zeige_lichter(self, anzahl, gesamt, schlimmste, quelle):
        """
        Fuellt das Infofeld neben der Lueckenmeldung.

        quelle='vorschau' kommt aus dem eingebetteten JPEG und ist nur ein
        Hinweis; quelle='raw' kommt aus der Messung der Sensordaten und ist
        belastbar. Der Unterschied steht im Hinweistext, damit eine
        vorlaeufige Warnung nicht fuer eine Diagnose gehalten wird.
        """
        self._last_clip = (anzahl, gesamt, schlimmste, quelle)
        if not gesamt:
            self.lbl_clip.setVisible(False)
            return
        anteil = 100.0 * anzahl / gesamt
        genau = (quelle == 'raw')
        if anzahl == 0:
            kurz = self._t("·  Lichter in Ordnung", "·  highlights fine")
            tip = self._t(
                "Kein Bild hat nennenswert ausgefressene Lichter."
                + ("\nGemessen an den Sensordaten in 16 Bit." if genau else
                   "\nGemessen an den Vorschaubildern der Kamera."),
                "No frame has noticeably blown highlights."
                + ("\nMeasured on the 16-bit sensor data." if genau else
                   "\nMeasured on the camera preview images."))
            self._clip_warn = False
        else:
            kurz = self._t(
                (f"⚠ {anzahl} Bild mit ausgefressenen Lichtern" if anzahl == 1
                 else f"⚠ {anzahl} Bilder mit ausgefressenen Lichtern"),
                (f"⚠ {anzahl} frame with blown highlights" if anzahl == 1
                 else f"⚠ {anzahl} frames with blown highlights"))
            if not genau:
                kurz += self._t(" (vorlaeufig)", " (provisional)")
            liste = "\n".join(
                self._t(f"Bild {i}: {100.0 * v:.1f} % der Pixel geklippt",
                        f"frame {i}: {100.0 * v:.1f} % of pixels clipped")
                for i, v in schlimmste)
            if genau:
                erklaerung = self._t(
                    f"{anzahl} von {gesamt} Bildern ({anteil:.0f} %) haben mehr als "
                    f"{100 * CLIP_SCHWELLE_RAW:.1f} % geklippte Pixel.\n"
                    "Gemessen an den Sensordaten in 16 Bit und linearem Licht - "
                    "diese Lichter sind wirklich verloren und lassen sich auch "
                    "durch eine negative Belichtungskorrektur nicht "
                    "zurueckholen.\n"
                    "Fuer den Deflicker ist das unschaedlich: die Messung "
                    "laesst ausgebrannte Stellen samt schmalem Saum aus, "
                    "solange mindestens ein Fuenftel des Bildes uebrig bleibt.",
                    f"{anzahl} of {gesamt} frames ({anteil:.0f} %) have more than "
                    f"{100 * CLIP_SCHWELLE_RAW:.1f} % clipped pixels.\n"
                    "Measured on the 16-bit sensor data in linear light - these "
                    "highlights are genuinely lost and cannot be brought back "
                    "by negative exposure compensation.\n"
                    "For the deflicker this is harmless: the measurement leaves "
                    "clipped areas out, together with a narrow seam, as long as "
                    "at least a fifth of the frame remains.")
            else:
                erklaerung = self._t(
                    f"{anzahl} von {gesamt} Bildern ({anteil:.0f} %) haben mehr als "
                    f"{100 * CLIP_SCHWELLE_VORSCHAU:.0f} % geklippte Pixel im "
                    "Vorschaubild.\n"
                    "Gemessen am eingebetteten JPEG der Kamera. Das ist die "
                    "Kamera-Entwicklung und klippt frueher als die Sensordaten - "
                    "im RAW steckt oft noch Zeichnung.\n"
                    "Pass 1 misst es genau und ersetzt diese Angabe.",
                    f"{anzahl} of {gesamt} frames ({anteil:.0f} %) have more than "
                    f"{100 * CLIP_SCHWELLE_VORSCHAU:.0f} % clipped pixels in the "
                    "preview image.\n"
                    "Measured on the camera's embedded JPEG, which clips earlier "
                    "than the sensor data - the RAW often still holds detail.\n"
                    "Pass 1 measures it precisely and replaces this figure.")
            tip = erklaerung + "\n\n" + self._t("Staerkste Faelle:",
                                                 "Worst cases:") + "\n" + liste
            self._clip_warn = True
            self._on_log("purelapse@engine:~$ " + kurz.replace("⚠ ", "") +
                         " - " + erklaerung.replace("\n", " "))
        self.lbl_clip.setText(kurz)
        self.lbl_clip.setToolTip(tip)
        self._style_clip()
        self.lbl_clip.setVisible(True)

    def _style_clip(self):
        t = THEMES[self.theme]
        if getattr(self, '_clip_warn', False):
            self.lbl_clip.setStyleSheet(
                f"color: {t['warn']}; border: 1px solid {t['warn']};"
                " border-radius: 9px; padding: 1px 9px; font-weight: bold;")
        else:
            self.lbl_clip.setStyleSheet(f"color: {t['dim']};")

    def _on_smooth_changed(self, val):
        lin = max(0, min(100, int(round((val - 85) / 15.0 * 100))))
        if lin >= 100:
            self.lbl_smooth_val.setText(self._t("100% · reine Gerade", "100% · straight line"))
        elif lin > 0:
            self.lbl_smooth_val.setText(f"{val}% · " + self._t(f"Gerade zu {lin}%", f"{lin}% straight line"))
        else:
            self.lbl_smooth_val.setText(f"{val}%")
        self._redraw_graph()

    def _on_ev_changed(self, val):
        ev = val / 10.0
        self.lbl_ev_val.setText(f"{ev:+.1f} EV")
        self._redraw_graph()

    def _redraw_graph(self):
        if len(self.luma_history) < 2:
            return
        # Ein Kreis je Messpunkt ergibt bei langen Sequenzen ein breites
        # Band statt einer Kurve. Ab SYMBOL_GRENZE nur noch die Linie -
        # die Punkte liegen dann ohnehin dichter als ein Pixel.
        self._setze_symbole(len(self.luma_history) <= SYMBOL_GRENZE)
        self.plot_raw.setData(self.frames_x, self.luma_history)
        scene_int = self.cmb_scene.currentIndex() + 1
        smooth_val = self.slider_smooth.value()
        ev_val = self.slider_ev.value() / 10.0
        smoothed = two_pass_smooth(np.array(self.luma_history), is_sunset_sunrise_mode=scene_int, smooth_amount=smooth_val)
        smoothed = smoothed * (2 ** ev_val)
        self.plot_smooth.setData(self.frames_x, smoothed)
        self._draw_extra_curves()

    def _kf_linie(self, index):
        """
        Senkrechte Marke fuer ein Keyframe.

        Zwei Pixel breit statt einem und mit einem Stern am oberen Rand:
        eine duenne gestrichelte Linie geht zwischen Gitternetz und
        Kurven unter, besonders im hellen Farbschema.
        """
        farbe = THEMES[self.theme]['curves']['kf']
        return pg.InfiniteLine(
            pos=index, angle=90, pen=stift(farbe, 2, QtCore.Qt.DashLine),
            label="★", labelOpts={'position': 0.96, 'color': farbe,
                                  'fill': (0, 0, 0, 0), 'movable': False})

    def _setze_symbole(self, an):
        """Punktsymbole der Messkurve ein- oder ausschalten."""
        if getattr(self, '_symbole_an', None) == an:
            return
        self._symbole_an = an
        farbe = THEMES[self.theme]['curves']['raw']
        try:
            if an:
                self.plot_raw.setSymbol('o')
                self.plot_raw.setSymbolSize(6)
                self.plot_raw.setSymbolBrush(farbe)
            else:
                self.plot_raw.setSymbol(None)
        except (AttributeError, TypeError):
            pass

    def _draw_extra_curves(self):
        if not self.extra_plots:
            return
        x = self.frames_x
        n = len(x)

        def vorbereiten(name):
            werte = self.curves.get(name) or []
            if len(werte) < 2:
                return None
            v = np.array(werte[:n], dtype=np.float64)
            if v.size < n:
                v = np.concatenate([v, np.full(n - v.size, np.nan)])
            if name in ('ev', 'interval'):
                gut = v[np.isfinite(v)]
                if gut.size < 2:
                    return None
                if name == 'interval':
                    v = np.log2(np.maximum(v, 1e-6) / max(np.median(gut), 1e-6))
                else:
                    v = v - np.median(gut)
            return v

        for name, kurve in self.extra_plots.items():
            sichtbar = self.curve_toggles[name].isChecked()
            v = vorbereiten(name) if sichtbar else None
            if v is None:
                kurve.setData([], [])
            else:
                kurve.setData(np.asarray(x[:v.size], dtype=np.float64), v)
        self._update_sun_markers()

    def _sichtbare_zeilen(self):
        """
        Erste und letzte Zeile, die in der Bildleiste gerade zu sehen ist.

        Die Kacheln liegen in Bildreihenfolge; es genuegt deshalb, von vorn
        zu gehen und aufzuhoeren, sobald eine Kachel unterhalb des
        sichtbaren Ausschnitts liegt. Ausgeblendete Kacheln (Keyframe-
        Filter) zaehlen nicht.
        """
        try:
            hoehe = int(self.list_widget.viewport().height())
        except (TypeError, ValueError):
            return None, None
        erste = letzte = None
        for i, t in enumerate(self.tiles):
            eintrag = t['item']
            if eintrag.isHidden():
                continue
            r = self.list_widget.visualItemRect(eintrag)
            if r.bottom() < 0:
                continue
            if r.top() > hoehe:
                break
            if erste is None:
                erste = i
            letzte = i
        return erste, letzte

    def _update_sicht_band(self):
        """Schiebt den Streifen im Diagramm auf den sichtbaren Bereich."""
        if self.sicht_band is None:
            return
        erste, letzte = self._sichtbare_zeilen()
        n = len(self.frames_x)
        if erste is None or n == 0:
            self.sicht_band.setVisible(False)
            return
        a = self.frames_x[min(erste, n - 1)] - 0.5
        b = self.frames_x[min(letzte, n - 1)] + 0.5
        self.sicht_band.setRegion((a, b))
        self.sicht_band.setVisible(True)

    def _style_sicht_band(self):
        """Faerbt den Streifen passend zum Farbschema."""
        if self.sicht_band is None:
            return
        t = THEMES[self.theme]
        # Im dunklen Schema heller, im hellen dunkler als der Grund -
        # jeweils die Schriftfarbe, stark durchscheinend.
        r, g, b = _rgb(t['text'])
        try:
            self.sicht_band.setBrush(pg.mkBrush(r, g, b, 34))
            for linie in self.sicht_band.lines:
                linie.setPen(pg.mkPen((r, g, b, 90), width=1))
        except Exception:
            pass

    def _on_graph_scene_clicked(self, ereignis):
        """Klick ins Diagramm: das Bild an dieser Stelle auswaehlen."""
        try:
            vb = self.graph.plotItem.vb
            pos = ereignis.scenePos()
            if not vb.sceneBoundingRect().contains(pos):
                return
            x = float(vb.mapSceneToView(pos).x())
        except Exception:
            return
        n = len(self.frames_x)
        if n == 0:
            return
        # naechstgelegenes Bild; frames_x ist aufsteigend
        idx = min(range(n), key=lambda i: abs(self.frames_x[i] - x))
        if 0 <= idx < self.list_widget.count():
            eintrag = self.list_widget.item(idx)
            if eintrag is not None and eintrag.isHidden():
                return        # durch den Keyframe-Filter ausgeblendet
            self.list_widget.setCurrentRow(idx)
            self.list_widget.scrollToItem(eintrag)

    def _on_graph_clicked(self, item, points):
        if not points:
            return
        idx = int(points[0].pos().x())
        if 0 <= idx < self.list_widget.count():
            self.list_widget.setCurrentRow(idx)
            self.list_widget.scrollToItem(self.list_widget.item(idx))

    def _codec_available(self, idx):
        """Fragt den Selbsttest, mit Zwischenspeicher je Programmlauf."""
        if idx in self._codec_probe:
            return self._codec_probe[idx]
        crf = ["16", "20", "23", "28"][max(0, min(3, self.cmb_quality.currentIndex()))]
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            ok, grund = probe_encoder(idx, crf=crf)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self._codec_probe[idx] = (ok, grund)
        return ok, grund

    def _codec_fallback_text(self, idx, grund):
        """Meldung, die den Fehlschlag erklaert, ohne FFmpeg zu zitieren."""
        grund = probe_grund_text(grund, self.lang)
        c = codec_def(idx)
        fb = codec_def(c['fb'])
        art = {'nvenc': self._t("die NVIDIA-Grafikkarte", "the NVIDIA graphics card"),
               'qsv': self._t("Intel QuickSync", "Intel QuickSync"),
               'vaapi': self._t("die Grafikkarte (VAAPI)", "the graphics card (VAAPI)")}
        wer = art.get(c['hw'], self._t("die Grafikkarte", "the graphics card"))
        return (self._t(f"Der Codec \u201e{c['label']}\u201c laeuft auf diesem Rechner nicht.\n\n"
                        f"FFmpeg kann {wer} nicht ansprechen. Haeufigste Ursache ist ein "
                        "Grafiktreiber, der nicht zur FFmpeg-Fassung passt.\n\n"
                        f"Meldung von FFmpeg:\n{grund}\n\n"
                        f"Soll stattdessen \u201e{fb['label']}\u201c verwendet werden? "
                        "Das Ergebnis ist gleichwertig, das Rendern dauert laenger.",
                        f"The codec \u201c{c['label']}\u201d does not work on this machine.\n\n"
                        f"FFmpeg cannot reach {wer}. The usual cause is a graphics driver "
                        "that does not match this FFmpeg build.\n\n"
                        f"FFmpeg says:\n{grund}\n\n"
                        f"Use \u201c{fb['label']}\u201d instead? The result is equivalent, "
                        "encoding just takes longer."))

    def _on_codec_changed(self, idx):
        """Prueft einen Hardware-Codec sofort bei der Auswahl."""
        c = codec_def(idx)
        if not c['hw'] or idx == c['fb']:
            return
        ok, grund = self._codec_available(idx)
        if ok:
            return
        antwort = QtWidgets.QMessageBox.question(
            self, self._t("Codec nicht verfuegbar", "Codec not available"),
            self._codec_fallback_text(idx, grund),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if antwort == QtWidgets.QMessageBox.Yes:
            self.cmb_codec.setCurrentIndex(c['fb'])

    def _preflight_codec(self, params):
        """
        Testet den Encoder, bevor die eigentliche Arbeit beginnt.

        Ohne diesen Test faellt ein untauglicher Hardware-Encoder erst beim
        Rendern auf - bei Pass 2 also nach Stunden Entwicklungsarbeit.

        Rueckgabe: True = weitermachen. params wird bei Bedarf umgestellt.
        """
        mode = params.get('mode', 'normal')
        if mode in ('preview', 'compare', 'schnell'):
            return True
        idx = params.get('codec_idx')
        if not isinstance(idx, int):
            return True
        if params.get('format') == 'jpg' and not params.get('make_video', True):
            return True
        c = codec_def(idx)
        if not c['hw']:
            return True
        ok, grund = self._codec_available(idx)
        if ok:
            return True
        fb = codec_def(c['fb'])
        # Im Stapelbetrieb steht niemand vor dem Rechner: umstellen und
        # protokollieren, statt auf eine Antwort zu warten.
        if self.batch_running:
            params['codec_idx'] = c['fb']
            erst = probe_grund_text(grund, self.lang).splitlines()[0] if grund else '?'
            self._on_log(self._t(f"> ACHTUNG: {c['label']} laeuft hier nicht ({erst})",
                                 f"> WARNING: {c['label']} does not work here ({erst})"))
            self._on_log(self._t(f"> Es wird auf {fb['label']} umgestellt.",
                                 f"> Switching to {fb['label']}."))
            return True
        antwort = QtWidgets.QMessageBox.question(
            self, self._t("Codec nicht verfuegbar", "Codec not available"),
            self._codec_fallback_text(idx, grund),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.Yes)
        if antwort != QtWidgets.QMessageBox.Yes:
            return False
        params['codec_idx'] = c['fb']
        self.cmb_codec.blockSignals(True)
        self.cmb_codec.setCurrentIndex(c['fb'])
        self.cmb_codec.blockSignals(False)
        self._update_filesize_estimate()
        return True

    def _update_filesize_estimate(self):
        # Gezaehlt wird, was ins Video kommt: Startbild bis Endbild.
        num_frames = len(self._arbeitsdateien())
        if num_frames == 0 or not self.chk_video.isChecked():
            self.lbl_size_est.setText(self._t("Geschätzte Dateigröße: -- MB",
                                              "Estimated file size: -- MB"))
            return
        try:
            fps = float(self.cmb_fps.currentText())
        except ValueError:
            fps = 25.0
        duration = num_frames / fps
        res_mult = [0.4, 1.0, 1.8, 4.0, 16.0][self.cmb_res.currentIndex()]
        qual_mult = [2.5, 1.5, 1.0, 0.6][self.cmb_quality.currentIndex()]
        codec_mult = codec_def(self.cmb_codec.currentIndex())['mult']
        base_mbps = 1.25
        fps_mult = fps / 25.0
        mb_per_sec = base_mbps * res_mult * qual_mult * codec_mult * fps_mult
        total_mb = duration * mb_per_sec
        groesse = (f"{total_mb/1024:.2f} GB" if total_mb > 1024 else f"{total_mb:.0f} MB")
        fps_text = f"{fps:g}".replace(".", ",") if self.lang != 'en' else f"{fps:g}"
        self.lbl_size_est.setText(self._t(
            f"Videolänge: {videolaenge_text(duration)} ({num_frames} Bilder bei "
            f"{fps_text} fps)  \u00b7  Geschätzte Dateigröße: ~ {groesse}",
            f"Video length: {videolaenge_text(duration, 'en')} ({num_frames} frames at "
            f"{fps_text} fps)  \u00b7  Estimated file size: ~ {groesse}"))

    def _update_visibility(self):
        # Welche Gruppen zu sehen sind, bestimmt die Schrittleiste
        # (_go_step); hier geht es nur noch um JPG/RAW-Unterschiede.
        is_raw = self.rb_raw.isChecked()
        self.chk_video.setVisible(not is_raw)
        video_on = self.chk_video.isChecked() or is_raw
        for w in (self.cmb_fps, self.cmb_res, self.cmb_blur, self.cmb_codec, self.cmb_quality,
                  self.btn_cam_path, self.chk_reverse, self.chk_stab, self.chk_astro,
                  self.chk_hotpix, self.cmb_fade):
            w.setEnabled(video_on)
        self.chk_denoise.setVisible(not is_raw)
        self.box_export.setVisible(video_on)
        if not video_on:
            self.lbl_size_est.setText(self._t("Geschätzte Dateigröße: -- MB",
                                              "Estimated file size: -- MB"))
        else:
            self._update_filesize_estimate()
        if hasattr(self, 'btn_start'):
            self._update_steps()
            self._update_summary()

    def _collect_params(self):
        is_raw = self.rb_raw.isChecked()
        files = self._arbeitsdateien(is_raw)
        if len(files) < 50:
            QtWidgets.QMessageBox.warning(self, self._t("Zu wenige Bilder", "Too few images"),
                                          self._t(f"Nur {len(files)} Bilder gefunden (mind. 50).",
                                                  f"Only {len(files)} images found (at least 50)."))
            return None
        _, max_blur, min_blur = self.blur_options[self.cmb_blur.currentIndex()]
        width, res_name = self.res_map[self.cmb_res.currentIndex()]
        p = {
            'target_dir': self.target_dir, 'files': files,
            'format': 'raw' if is_raw else 'jpg',
            'scene_int': self.cmb_scene.currentIndex() + 1,
            'smooth_val': self.slider_smooth.value(),
            'ev_val': self.slider_ev.value() / 10.0,
            'roi_rel': self.roi_rel,
            'fps': self.cmb_fps.currentText(),
            'width': width, 'res_name': res_name, 'res_idx': self.cmb_res.currentIndex(),
            'max_blur': max_blur, 'min_blur': min_blur,
            'cam_keyframes': self.cam_keyframes,
            'reverse_play': self.chk_reverse.isChecked(),
            'stabilize': self.chk_stab.isChecked(),
            'denoise': self.chk_denoise.isChecked(),
            'astro_clean': self.chk_astro.isChecked(),
            'hotpixel': self.chk_hotpix.isChecked(),
            'fade_sec': [0.0, 0.5, 1.0, 2.0, 3.0][self.cmb_fade.currentIndex()],
            'telemetry': self.chk_tel.isChecked(),
            'make_video': (self.chk_video.isChecked() or is_raw),
            # 3-Wege-Zuordnung statt vorher nur 2 (art/rt).
            'engine': {0: 'art', 1: 'rt', 2: 'dt'}.get(self.cmb_engine.currentIndex(), 'art'),
            'cores': self.cmb_cores.currentIndex() + 1,
            'procs': PROZESS_WAHL[max(0, min(len(PROZESS_WAHL) - 1,
                                             self.cmb_procs.currentIndex()))],
            'codec_idx': self.cmb_codec.currentIndex(),
            'qual_idx': self.cmb_quality.currentIndex(),
            'calib_rounds': self.cmb_calib.currentIndex(),
            'diag': self.chk_diag.isChecked(),
            'tiff16': self.chk_tiff16.isChecked(),
            'out_dir_mode': self.cmb_export_dir.currentIndex(),
            'custom_out_dir': self.custom_out_dir,
            'versioning': self.cmb_versioning.currentIndex() == 0
        }
        if is_raw:
            p['raw_mode'] = 'pass1' if self.cmb_rawmode.currentIndex() == 0 else 'pass2'
            art = self.txt_art_path.text().strip()
            if p['raw_mode'] == 'pass1':
                p['make_video'] = False
                p['art_cli_path'] = art if art and os.path.isfile(art) else ''
            else:
                if not art or not os.path.isfile(art):
                    QtWidgets.QMessageBox.warning(self, self._t("Fehler", "Error"), self._t(f"Bitte zuerst {eng('bin')} in den Einstellungen auswählen.",
                            f"Please select {eng('bin')} in the settings first."))
                    return None
                p['art_cli_path'] = art
        return p

    def _start(self):
        if not self.target_dir or not os.path.isdir(self.target_dir):
            return
        params = self._collect_params()
        if not params:
            return
        # Die Zusammenfassung ueber den Knoepfen zeigt bereits, was jetzt
        # laeuft; waehrend des Laufs wird sie nur hervorgehoben.
        self._update_summary()
        self.lbl_summary.setStyleSheet(
            f"color: {self._farben()['accent']}; font-weight: bold;")
        self._save_settings()
        self._launch(params, "INIT PROCESS")
        self._last_run = params.get('raw_mode') or 'jpg'
        self._on_log(f"purelapse@engine:~$ TARGET DIR = {self.target_dir}")

    def _launch(self, params, banner):
        # Erst pruefen, ob der Video-Encoder ueberhaupt arbeitet.
        if not self._preflight_codec(params):
            self.lbl_status.setText(self._t("Abgebrochen - Codec nicht verfuegbar",
                                            "Cancelled - codec not available"))
            return
        self._log_leeren()
        self.progress.setValue(0)
        self._last_run = None
        self._busy = True
        self._vom_benutzer_abgebrochen = False
        modus = params.get('mode', 'normal')
        anzahl = len(params.get('files') or [])
        self._lauf_art = {
            'plain': self._t("Rohfassung", "Plain version"),
            'compare': self._t("Vergleichsvideo", "Comparison video"),
            'preview': self._t("Vorschau", "Preview"),
            'schnell': self._t("Schnellvorschau", "Quick preview"),
        }.get(modus) or (
            ("Pass 1" if params.get('raw_mode') == 'pass1' else
             self._t("Pass 2 (Video)", "Pass 2 (video)"))
            if params.get('format') == 'raw' else self._t("JPG-Zeitraffer", "JPG timelapse"))
        if anzahl:
            self._lauf_art += self._t(f", {anzahl} Bilder", f", {anzahl} frames")
        self._lauf_modus = modus
        # Der Ablauf beginnt mit dem Plan dieses Laufs und fuellt sich mit
        # jeder Statuszeile des Workers.
        self._ablauf = Ablauf(ablauf_plan(params))
        self._ablauf_zeigen()
        self._ablauf_timer.start()
        for b in (self.btn_start, self.btn_plain, self.btn_preview, self.btn_compare,
                  self.btn_q_add, self.btn_q_del, self.btn_q_clear, self.btn_q_run,
                  self.btn_schnell):
            b.setEnabled(False)
        # Die Engine darf waehrend eines Laufs nicht wechseln: Worker und
        # Galerie lesen dieselbe globale Einstellung, ein Umschalten
        # mitten im Lauf wuerde die Endung der Sidecars verdrehen.
        self.cmb_engine.setEnabled(False)
        self.btn_kf_edit.setEnabled(False)
        self._apply_action_state()
        self.btn_cancel.setEnabled(True)
        self._on_log(f"purelapse@engine:~$ {banner} (v{VERSION})")
        params['lang'] = self.lang
        try:
            self.worker = Worker(params)
            self.worker.log.connect(self._on_log)
            self.worker.status.connect(self._on_status)
            self.worker.progress.connect(self._on_progress)
            self.worker.finished_ok.connect(self._on_done)
            self.worker.output_ready.connect(self._on_output_ready)
            self.worker.clip_report.connect(self._on_clip_report)
            self.worker.failed.connect(self._on_fail)
            self.worker.start()
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.worker = None
            self.batch_running = False
            self._ablauf_ende(False)
            self._enable_buttons()
            self.btn_cancel.setEnabled(False)
            self.lbl_status.setText(self._t("Start fehlgeschlagen", "Start failed"))
            self._on_log(f"[FEHLER] {type(e).__name__}: {e}")
            QtWidgets.QMessageBox.critical(
                self, self._t("Fehler", "Error"),
                self._t("Der Arbeitsschritt konnte nicht gestartet werden.\n\n",
                        "The task could not be started.\n\n") + f"{type(e).__name__}: {e}")

    def _start_plain(self):
        if not self.target_dir or not os.path.isdir(self.target_dir):
            return
        is_raw = self.rb_raw.isChecked()
        files = self._arbeitsdateien(is_raw)
        if not files:
            QtWidgets.QMessageBox.warning(
                self, "Keine Bilder" if self.lang == 'de' else "No images",
                "Im gewaehlten Ordner sind keine passenden Bilder."
                if self.lang == 'de' else "No matching images in the selected folder.")
            return
        width, res_name = self.res_map[self.cmb_res.currentIndex()]
        p = {
            'mode': 'plain', 'target_dir': self.target_dir, 'files': files,
            'format': 'raw' if is_raw else 'jpg',
            'fps': self.cmb_fps.currentText(),
            'width': width, 'res_name': res_name,
            'codec_idx': self.cmb_codec.currentIndex(),
            'qual_idx': self.cmb_quality.currentIndex(),
            'out_dir_mode': self.cmb_export_dir.currentIndex(),
            'custom_out_dir': self.custom_out_dir,
            'versioning': self.cmb_versioning.currentIndex() == 0,
            'name_suffix': '_Original',
            'cam_keyframes': None, 'diag': False,
        }
        self.lbl_summary.setText(
            f"Rohfassung: {len(files)} Bilder | {res_name} @ {p['fps']} fps\n"
            "Ohne Deflicker, ohne Keyframes, ohne Effekte"
            if self.lang == 'de' else
            f"Untouched version: {len(files)} images | {res_name} @ {p['fps']} fps\n"
            "No deflicker, no keyframes, no effects")
        self.lbl_summary.setStyleSheet(
            f"color: {self._farben()['accent']}; font-weight: bold;")
        self._launch(p, "INIT ROHFASSUNG")

    # ------------------------------------------------------------------
    #  Warteschlange
    # ------------------------------------------------------------------
    STATUS_SYMBOL = {'pending': '•', 'running': '▶', 'done': '✔', 'failed': '✗'}

    def _on_output_ready(self, path):
        if path and os.path.isdir(path):
            self.last_output_dir = path

    def _current_output_dir(self):
        if self.last_output_dir and os.path.isdir(self.last_output_dir):
            return self.last_output_dir
        idx = self.cmb_export_dir.currentIndex()
        if idx == 1 and self.target_dir:
            return os.path.dirname(self.target_dir)
        if idx == 2:
            return SCRIPT_DIR
        if idx == 3 and self.custom_out_dir:
            return self.custom_out_dir
        if self.target_dir:
            # Standard: der Ordner "Purelapse" im Bilderordner - solange es ihn
            # noch nicht gibt, der Bilderordner selbst.
            pl = pl_ordner(self.target_dir)
            return pl if os.path.isdir(pl) else self.target_dir
        return ""

    def _open_output_dir(self):
        d = self._current_output_dir()
        if not d or not os.path.isdir(d):
            QtWidgets.QMessageBox.information(
                self, self._t("Kein Ordner", "No folder"),
                self._t("Es gibt noch keinen Ausgabeordner. Bitte zuerst einen "
                        "Zeitraffer-Ordner waehlen oder ein Video erzeugen.",
                        "There is no output folder yet. Please select a timelapse "
                        "folder or create a video first."))
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(d))
        self._on_log(self._t(f"purelapse@engine:~$ Ordner geoeffnet: {d}",
                             f"purelapse@engine:~$ Folder opened: {d}"))

    def _enable_buttons(self):
        self._busy = False
        for b in (self.btn_start, self.btn_plain, self.btn_preview, self.btn_compare,
                  self.btn_q_add, self.btn_q_del, self.btn_q_clear, self.btn_schnell):
            b.setEnabled(True)
        self.cmb_engine.setEnabled(True)
        self._update_kf_buttons()
        self._queue_refresh()
        self._update_steps()      # Haken der Schrittleiste + Sperren je Schritt
        self._update_summary()

    def _queue_refresh(self):
        self.list_queue.clear()
        for job in self.queue:
            sym = self.STATUS_SYMBOL.get(job.get('status', 'pending'), '•')
            item = QtWidgets.QListWidgetItem(f" {sym}  {job.get('label', '?')}")
            st = job.get('status', 'pending')
            t_q = THEMES[self.theme]
            item.setForeground(QtGui.QColor(
                {'done': t_q['ok'], 'failed': t_q['err'],
                 'running': t_q['warn']}.get(st, t_q['text'])))
            self.list_queue.addItem(item)
        offen = sum(1 for j in self.queue if j.get('status') in ('pending', 'running'))
        self.btn_q_run.setText(
            self._t(f" Stapel abarbeiten ({offen} offen)", f" Run queue ({offen} pending)")
            if self.queue else self._t(" Stapel abarbeiten", " Run queue"))
        self.btn_q_run.setEnabled(bool(offen) and not self.batch_running)
        self.btn_queue_open.setText(
            self._t(f" Warteschlange… ({offen})", f" Queue… ({offen})") if offen
            else self._t(" Warteschlange…", " Queue…"))

    def _queue_add(self):
        params = self._collect_params()
        if not params:
            return
        speicher = {k: v for k, v in params.items() if k != 'files'}
        schritt = (self._t("Pass 1", "Pass 1") if params.get('raw_mode') == 'pass1'
                   else self._t("Pass 2", "Pass 2") if params.get('raw_mode') == 'pass2'
                   else "JPG")
        label = f"{os.path.basename(self.target_dir)}  [{schritt}]  {len(params['files'])} " + \
                self._t("Bilder", "images")
        self.queue.append({'dir': self.target_dir, 'label': label,
                           'status': 'pending', 'params': speicher})
        save_queue(self.queue)
        self._queue_refresh()
        self._on_log(self._t(f"purelapse@engine:~$ Auftrag eingereiht: {label}",
                             f"purelapse@engine:~$ Job queued: {label}"))

    def _queue_remove(self):
        r = self.list_queue.currentRow()
        if 0 <= r < len(self.queue) and not self.batch_running:
            del self.queue[r]
            save_queue(self.queue)
            self._queue_refresh()

    def _queue_clear(self):
        if self.batch_running or not self.queue:
            return
        if QtWidgets.QMessageBox.question(
                self, self._t("Warteschlange leeren", "Clear queue"),
                self._t(f"Alle {len(self.queue)} Auftraege verwerfen?",
                        f"Discard all {len(self.queue)} jobs?"),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No) != QtWidgets.QMessageBox.Yes:
            return
        self.queue = []
        save_queue(self.queue)
        self._queue_refresh()

    def _queue_start(self):
        if self.batch_running:
            return
        for job in self.queue:
            if job.get('status') == 'running':
                job['status'] = 'pending'
        self.batch_running = True
        self._on_log(self._t("purelapse@engine:~$ STAPELVERARBEITUNG GESTARTET",
                             "purelapse@engine:~$ BATCH PROCESSING STARTED"))
        self._queue_next()

    def _queue_next(self):
        self.batch_index = next((i for i, j in enumerate(self.queue)
                                 if j.get('status') == 'pending'), -1)
        if self.batch_index < 0:
            self.batch_running = False
            save_queue(self.queue)
            self._queue_refresh()
            fertig = sum(1 for j in self.queue if j.get('status') == 'done')
            fehler = sum(1 for j in self.queue if j.get('status') == 'failed')
            msg = self._t(f"Stapel abgeschlossen: {fertig} erledigt, {fehler} fehlgeschlagen.",
                          f"Batch finished: {fertig} done, {fehler} failed.")
            self._on_log("\npurelapse@engine:~$ " + msg)
            self._telegram_melden(fehler == 0, msg,
                                  self._t(f"Warteschlange, {len(self.queue)} Auftraege",
                                          f"Queue, {len(self.queue)} jobs"))
            QtWidgets.QMessageBox.information(self, self._t("Stapel fertig", "Batch done"), msg)
            return
        job = self.queue[self.batch_index]
        params = dict(job['params'])
        d = job['dir']
        if not os.path.isdir(d):
            job['status'] = 'failed'
            self._on_log(f"[FEHLER] {self._t('Ordner fehlt', 'Folder missing')}: {d}")
            self._queue_refresh()
            self._queue_next()
            return
        if params.get('format') == 'raw':
            files = find_raw_files(d)
        else:
            files = sorted(glob.glob(os.path.join(d, "*.jpg")) +
                           glob.glob(os.path.join(d, "*.JPG")))
        if not files:
            job['status'] = 'failed'
            self._on_log(f"[FEHLER] {self._t('Keine Bilder in', 'No images in')} {d}")
            self._queue_refresh()
            self._queue_next()
            return
        params['files'] = files
        params['target_dir'] = d
        job['status'] = 'running'
        save_queue(self.queue)
        self._queue_refresh()
        self._launch(params, f"BATCH {self.batch_index + 1}/{len(self.queue)}: {job['label']}")

    def _queue_finish(self, status):
        if 0 <= self.batch_index < len(self.queue):
            self.queue[self.batch_index]['status'] = status
            save_queue(self.queue)
            self._queue_refresh()
        self._queue_next()

    def _start_preview(self):
        params = self._collect_params()
        if not params:
            return
        params['mode'] = 'preview'
        params['preview_count'] = 5
        params['luma_curve'] = list(self.luma_history)
        params['diag'] = False
        if params['format'] == 'raw' and not params.get('art_cli_path'):
            art = self.txt_art_path.text().strip()
            if not art or not os.path.isfile(art):
                QtWidgets.QMessageBox.warning(
                    self, "Fehler" if self.lang == 'de' else "Error",
                    self._t(f"Für die RAW-Vorschau wird {eng('bin')} benötigt (siehe Einstellungen).",
                            f"The RAW preview needs {eng('bin')} (see settings)."))
                return
            params['art_cli_path'] = art
        self._launch(params, "INIT VORSCHAU")

    def _start_schnell(self):
        params = self._collect_params()
        if not params:
            return
        params['mode'] = 'schnell'
        params['diag'] = False
        self._launch(params, "INIT SCHNELLVORSCHAU")

    def _open_compare_dialog(self):
        start = self.custom_out_dir or self.target_dir or os.path.expanduser("~")
        dlg = CompareDialog(start, self.lang, self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        a, b, style, out = dlg.values()
        if not (a and b and out):
            return
        self._launch({'mode': 'compare', 'target_dir': self.target_dir or start,
                      'video_a': a, 'video_b': b, 'compare_style': style,
                      'compare_out': out, 'diag': False},
                     "INIT VERGLEICH")

    # ------------------------------------------------------------------
    #  Telegram
    # ------------------------------------------------------------------
    def _telegram_merken(self):
        telegram_speichern(self.chk_telegram.isChecked(),
                           self.txt_tg_token.text(), self.txt_tg_chat.text())

    def _telegram_chat_ermitteln(self):
        self._telegram_merken()
        chat, info = telegram_chat_finden(self.txt_tg_token.text().strip(), self.lang)
        if chat:
            self.txt_tg_chat.setText(chat)
            self._telegram_merken()
            QtWidgets.QMessageBox.information(
                self.dlg_settings, "Telegram",
                self._t(f"Chat gefunden: {info or chat}\nChat-ID {chat} ist eingetragen.",
                        f"Chat found: {info or chat}\nChat ID {chat} has been set."))
        else:
            QtWidgets.QMessageBox.warning(self.dlg_settings, "Telegram", info)

    def _telegram_test(self):
        self._telegram_merken()
        ok, info = telegram_senden(
            self.txt_tg_token.text().strip(), self.txt_tg_chat.text().strip(),
            self._t("\U0001f44b Purelapse: Testnachricht. Die Benachrichtigung funktioniert.",
                    "\U0001f44b Purelapse: test message. Notifications work."),
            lang=self.lang)
        if ok:
            QtWidgets.QMessageBox.information(
                self.dlg_settings, "Telegram",
                self._t("Testnachricht gesendet.", "Test message sent."))
        else:
            QtWidgets.QMessageBox.warning(self.dlg_settings, "Telegram", info)

    def _telegram_melden(self, erfolg, meldung, art=None):
        """
        Schickt den Bericht zu einem beendeten Lauf - im Hintergrund, damit
        eine langsame Verbindung das Fenster nicht anhaelt. Ein Fehler beim
        Senden landet im Protokoll, aber nie als Dialog.
        """
        tg = telegram_laden()
        if not (tg['an'] and tg['token'] and tg['chat']):
            return
        rest = None
        for _wann, zeile in reversed(getattr(self, '_log_eintraege', [])):
            if "Restflackern" in zeile or "Residual flicker" in zeile:
                m = re.search(r"([0-9]+[.,][0-9]+)\s*EV", zeile)
                if m:
                    rest = m.group(1) + " EV"
                break
        text = telegram_bericht(erfolg, self.target_dir,
                                art or getattr(self, '_lauf_art', ""),
                                getattr(self, '_ablauf', None), meldung, rest, self.lang)
        ergebnis = {}
        lang = self.lang

        def senden():
            ergebnis['wert'] = telegram_senden(tg['token'], tg['chat'], text, lang=lang)

        faden = threading.Thread(target=senden, daemon=True)
        faden.start()
        self._telegram_faden = faden

        def pruefen(versuch=0):
            if 'wert' in ergebnis:
                ok, info = ergebnis['wert']
                if not ok:
                    self._on_log(self._t(f"> WARNUNG: Telegram-Nachricht nicht gesendet: {info}",
                                         f"> WARNING: Telegram message not sent: {info}"))
            elif versuch < 40:
                QtCore.QTimer.singleShot(500, lambda: pruefen(versuch + 1))
        QtCore.QTimer.singleShot(500, pruefen)

    def _cancel(self):
        self._vom_benutzer_abgebrochen = True
        if self.worker:
            self.worker.cancel()
            self._on_log("\npurelapse@engine:~$ ABBRUCH DURCH BENUTZER ANGEFORDERT...")
            self.btn_cancel.setEnabled(False)

    def _on_log(self, msg):
        """Nimmt eine Meldung ins Protokoll, mit Datum und Uhrzeit."""
        wann = datetime.datetime.now()
        self._log_eintraege.append((wann, str(msg)))
        if len(self._log_eintraege) > 5000:
            del self._log_eintraege[:1000]
        self._log_schreiben(wann, msg)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _log_schreiben(self, wann, msg):
        zeilen = log_html(msg, wann, self._farben())
        if zeilen:
            self.txt_log.appendHtml(zeilen)

    def _log_leeren(self):
        self._log_eintraege = []
        self.txt_log.clear()

    def _log_neu_zeichnen(self):
        """Schreibt das Protokoll in den Farben des jetzigen Schemas neu."""
        eintraege = getattr(self, '_log_eintraege', None)
        if not eintraege:
            return
        self.txt_log.clear()
        for wann, msg in eintraege:
            self._log_schreiben(wann, msg)
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_status(self, text):
        """
        Statuszeile des Workers.

        Oben steht die Kurzfassung (Schritt und Zaehlerstand). Die Zeiten
        wandern in den Ablauf darunter, wo sie neben den erledigten und
        den ausstehenden Schritten stehen.
        """
        if self._ablauf is not None and self._ablauf.ende is None:
            label, fertig, gesamt, _zusatz = status_zerlegen(text)
            self._ablauf.melde(label, fertig, gesamt)
            self._ablauf_zeigen()
        self.lbl_status.setText(status_kurz(text, self.lang))

    def _ablauf_zeigen(self):
        """Bringt Ablauf-Leiste und Laufzeit auf den aktuellen Stand."""
        if not hasattr(self, 'ablauf_leiste'):
            return
        ablauf = getattr(self, '_ablauf', None)
        self.ablauf_leiste.zeige(ablauf, self.lang)
        self.lbl_lauf.setText(ablauf_kopf(ablauf, self.lang))

    def _ablauf_ende(self, erfolg):
        self._ablauf_timer.stop()
        if getattr(self, '_ablauf', None) is not None:
            self._ablauf.abschliessen(erfolg)
            self._ablauf_zeigen()

    def _prozent_zeigen(self, *_):
        """Die Zahl neben dem Fortschrittsbalken."""
        try:
            hoechst = int(self.progress.maximum())
            wert = int(self.progress.value())
        except (TypeError, ValueError):
            return
        if hoechst <= 0 or wert <= 0:
            self.lbl_prozent.setText("")
        else:
            self.lbl_prozent.setText(f"{min(100, wert * 100 // hoechst)} %")

    def _on_progress(self, cur, total):
        if total > 0:
            self.progress.setMaximum(total)
            self.progress.setValue(cur)

    def _on_done(self, msg):
        self._ablauf_ende(True)
        if msg.startswith("SCHNELL::"):
            pfad = msg[len("SCHNELL::"):]
            self.lbl_status.setText(self._t("Schnellvorschau fertig \u2714",
                                            "Quick preview done \u2714"))
            self._on_log("> " + self._t("Schnellvorschau: ", "Quick preview: ") + pfad)
            self._enable_buttons()
            self.btn_cancel.setEnabled(False)
            try:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(pfad))
            except Exception:
                pass
            return
        if msg.startswith("PREVIEW::"):
            entries = []
            for part in msg[len("PREVIEW::"):].split(";;"):
                if "|" in part:
                    i, path = part.split("|", 1)
                    entries.append((int(i), path))
            self.lbl_status.setText(self._t("Vorschau bereit", "Preview ready"))
            self._enable_buttons()
            self.btn_cancel.setEnabled(False)
            if entries:
                PreviewDialog(entries, self.lang, self).exec_()
            return
        self.lbl_status.setText(self._t("Fertig ✔", "Done ✔"))
        self._on_log("\n" + msg)
        self._enable_buttons()
        self.btn_cancel.setEnabled(False)
        if self.batch_running:
            self._queue_finish('done')
            return
        if getattr(self, '_lauf_modus', 'normal') in ('normal', 'plain'):
            self._telegram_melden(True, msg)
        if self._last_run == 'pass1':
            self._go_step('keys')     # nach Pass 1 geht es mit den Keyframes weiter
        QtWidgets.QMessageBox.information(self, self._t("Fertig", "Done"), msg)

    def _on_fail(self, msg):
        self._ablauf_ende(False)
        if (not getattr(self, '_vom_benutzer_abgebrochen', False)
                and getattr(self, '_lauf_modus', 'normal') in ('normal', 'plain')):
            self._telegram_melden(False, msg)
        self.lbl_status.setText(self._t("Fehler / Abbruch", "Error / cancelled"))
        self._on_log("\n" + self._t("[FEHLER] ", "[ERROR] ") + msg)
        self.btn_log.setChecked(True)     # bei Fehlern das Protokoll zeigen
        self._enable_buttons()
        self.btn_cancel.setEnabled(False)
        if self.batch_running:
            abgebrochen = "abgebrochen" in msg.lower() or "cancel" in msg.lower()
            if 0 <= self.batch_index < len(self.queue):
                self.queue[self.batch_index]['status'] = 'pending' if abgebrochen else 'failed'
                save_queue(self.queue)
            self.batch_running = False
            self._queue_refresh()
            self._on_log(self._t("purelapse@engine:~$ STAPEL ANGEHALTEN",
                                 "purelapse@engine:~$ BATCH PAUSED"))
            return
        QtWidgets.QMessageBox.critical(self, self._t("Fehler", "Error"), msg)

    # ------------------------------------------------------------------
    #  Sonnenstand
    # ------------------------------------------------------------------
    def _parse_coord(self, text):
        try:
            return float(text.strip().replace(',', '.'))
        except (ValueError, AttributeError):
            return None

    def _recompute_sun_curve(self):
        """Berechnet die Sonnenstands-Kurve neu und meldet Grenzuebergaenge."""
        if not self._exif_times:
            self.curves['sun'] = []
            self._sun_crossings = []
            self._update_sun_markers()
            return
        lat = self._parse_coord(self.txt_lat.text())
        lon = self._parse_coord(self.txt_lon.text())
        if lat is None or lon is None:
            self.curves['sun'] = []
            self._sun_crossings = []
            self._draw_extra_curves()
            return
        try:
            tz = float(self.txt_utc.text().strip().replace(',', '.'))
        except (ValueError, AttributeError):
            tz = 0.0
        grad = compute_sun_elevation(self._exif_times, lat, lon, tz)
        self.curves['sun'] = [v / 15.0 if v == v else float('nan') for v in grad]
        neu = self._find_sun_crossings(grad)
        if neu != self._sun_crossings:
            self._sun_crossings = neu
            self._report_sun_crossings(neu)
        self._draw_extra_curves()

    def _find_sun_crossings(self, grad):
        """Findet die Bildindizes, an denen der Sonnenstand eine Daemmerungsgrenze ueberschreitet."""
        grenzen = [(0.0, self._t("Sonnenuntergang/-aufgang", "Sunset/sunrise")),
                  (-6.0, self._t("bürgerliche Dämmerung", "civil twilight")),
                  (-12.0, self._t("nautische Dämmerung", "nautical twilight")),
                  (-18.0, self._t("astronomische Dämmerung", "astronomical twilight"))]
        out = []
        g = np.asarray(grad, dtype=np.float64)
        for grenze, label in grenzen:
            for i in range(1, g.size):
                a, b = g[i - 1], g[i]
                if not (a == a and b == b):
                    continue
                if a >= grenze > b:
                    out.append((i, grenze, label, self._t("dunkler werdend", "getting darker")))
                elif a < grenze <= b:
                    out.append((i, grenze, label, self._t("heller werdend", "getting brighter")))
        out.sort(key=lambda t: t[0])
        return out

    def _report_sun_crossings(self, crossings):
        """Meldet im Log, an welchen Bildern eine Daemmerungsgrenze ueberschritten wird."""
        if not crossings:
            return
        zeilen = []
        for idx, grenze, label, richtung in crossings[:15]:
            zeilen.append(self._t(
                f"  Bild {idx + 1}: {label} beginnt ({richtung}, Elevation kreuzt {grenze:g}°)",
                f"  frame {idx + 1}: {label} begins ({richtung}, elevation crosses {grenze:g}°)"))
        if len(crossings) > 15:
            zeilen.append(self._t(f"  ... und {len(crossings) - 15} weitere Übergänge",
                                  f"  ... and {len(crossings) - 15} more transitions"))
        self._on_log(self._t("purelapse@engine:~$ Sonnenstand:",
                             "purelapse@engine:~$ Sun elevation:") + "\n" + "\n".join(zeilen))

    def _update_sun_markers(self):
        """Zeigt/versteckt die Daemmerungs-Linien: waagerecht als Referenz und
        senkrecht dort, wo die Sequenz eine Grenze tatsaechlich ueberschreitet."""
        if getattr(self, 'vb_wb', None) is not None:
            for m in self.sun_h_marker:
                self.vb_wb.removeItem(m)
        self.sun_h_marker = []
        for m in self.sun_marker:
            self.graph.removeItem(m)
        self.sun_marker = []
        if getattr(self, 'vb_wb', None) is None or not self.curve_toggles['sun'].isChecked():
            return
        farbe = THEMES[self.theme]['curves'].get('sun', '#ba68c8')
        for grad in (-6, -12, -18):
            line = pg.InfiniteLine(pos=grad / 15.0, angle=0,
                                   pen=pg.mkPen(farbe, width=1, style=QtCore.Qt.DotLine))
            self.vb_wb.addItem(line)
            self.sun_h_marker.append(line)
        kuerzel = {0.0: "☼", -6.0: "C", -12.0: "N", -18.0: "A"}
        for idx, grenze, label, richtung in self._sun_crossings:
            line = pg.InfiniteLine(
                pos=idx, angle=90,
                pen=pg.mkPen(farbe, width=1, style=QtCore.Qt.DashLine),
                label=kuerzel.get(grenze, "?"),
                labelOpts={'color': farbe, 'position': 0.9})
            self.graph.addItem(line)
            self.sun_marker.append(line)

    def _gps_from_exif(self, files=None, silent=False):
        """Versucht, GPS-Koordinaten aus dem EXIF des ersten Bildes zu lesen."""
        if files is None:
            files = self._nef_files if self.rb_raw.isChecked() else self._jpg_files
        if not files:
            return False

        def _to_deg(vals, ref):
            d = float(vals[0].num) / float(vals[0].den)
            m = float(vals[1].num) / float(vals[1].den)
            s = float(vals[2].num) / float(vals[2].den)
            deg = d + m / 60.0 + s / 3600.0
            return -deg if ref in ('S', 'W') else deg

        try:
            with open(files[0], 'rb') as f:
                tags = exifread.process_file(f, details=False)
            lat_tag = tags.get('GPS GPSLatitude')
            lon_tag = tags.get('GPS GPSLongitude')
            if not (lat_tag and lon_tag):
                raise ValueError("keine GPS-Tags")
            lat_ref = str(tags.get('GPS GPSLatitudeRef', 'N'))
            lon_ref = str(tags.get('GPS GPSLongitudeRef', 'E'))
            self.txt_lat.setText(f"{_to_deg(lat_tag.values, lat_ref):.5f}")
            self.txt_lon.setText(f"{_to_deg(lon_tag.values, lon_ref):.5f}")
            self._recompute_sun_curve()
            return True
        except Exception:
            if not silent:
                QtWidgets.QMessageBox.information(
                    self, self._t("Keine GPS-Daten", "No GPS data"),
                    self._t("Das erste Bild enthaelt keine GPS-EXIF-Daten. Bitte "
                            "Breite/Laenge manuell eingeben.",
                            "The first image has no GPS EXIF data. Please enter "
                            "latitude/longitude manually."))
            return False

    # ------------------------------------------------------------------
    #  Einstellungen merken
    # ------------------------------------------------------------------
    def _settings_widgets(self):
        return {
            'scene': self.cmb_scene, 'rawmode': self.cmb_rawmode,
            'fps': self.cmb_fps, 'res': self.cmb_res, 'codec': self.cmb_codec,
            'quality': self.cmb_quality, 'blur': self.cmb_blur,
            'cores': self.cmb_cores, 'calib': self.cmb_calib, 'fade': self.cmb_fade,
            'procs': self.cmb_procs,
            'engine': self.cmb_engine,
            'export_dir': self.cmb_export_dir, 'versioning': self.cmb_versioning,
            'smooth': self.slider_smooth, 'ev': self.slider_ev,
            'video': self.chk_video, 'stab': self.chk_stab,
            'denoise': self.chk_denoise, 'reverse': self.chk_reverse,
            'telemetry': self.chk_tel, 'astro': self.chk_astro,
            'hotpix': self.chk_hotpix, 'diag': self.chk_diag, 'tiff16': self.chk_tiff16,
            'curve_wb': self.curve_toggles['wb'],
            'curve_ev': self.curve_toggles['ev'],
            'curve_interval': self.curve_toggles['interval'],
            'curve_clip': self.curve_toggles['clip'],
            'curve_residual': self.curve_toggles['residual'],
            'curve_sun': self.curve_toggles['sun'],
            'lat': self.txt_lat, 'lon': self.txt_lon, 'utc': self.txt_utc,
            'log_open': self.btn_log,
        }

    def _save_settings(self):
        data = {}
        for key, w in self._settings_widgets().items():
            if isinstance(w, QtWidgets.QComboBox):
                data[key] = w.currentIndex()
            elif isinstance(w, QtWidgets.QSlider):
                data[key] = w.value()
            elif isinstance(w, QtWidgets.QLineEdit):
                data[key] = w.text()
            else:
                data[key] = w.isChecked()
        data['raw_mode_selected'] = self.rb_raw.isChecked()
        data['custom_out_dir'] = self.custom_out_dir
        konfig_setzen('einstellungen', data)

    def _load_settings(self):
        data = konfig_lesen('einstellungen', standard=None)
        if not isinstance(data, dict):
            return
        for key, w in self._settings_widgets().items():
            if key not in data:
                continue
            v = data[key]
            try:
                w.blockSignals(True)
                if isinstance(w, QtWidgets.QComboBox):
                    if 0 <= int(v) < w.count():
                        w.setCurrentIndex(int(v))
                elif isinstance(w, QtWidgets.QSlider):
                    w.setValue(int(v))
                elif isinstance(w, QtWidgets.QLineEdit):
                    w.setText(str(v))
                else:
                    w.setChecked(bool(v))
            except (TypeError, ValueError):
                pass
            finally:
                w.blockSignals(False)
        self.custom_out_dir = data.get('custom_out_dir', '')
        self._on_engine_changed()
        if data.get('raw_mode_selected'):
            self.rb_raw.blockSignals(True)
            self.rb_raw.setChecked(True)
            self.rb_raw.blockSignals(False)
        self._on_smooth_changed(self.slider_smooth.value())
        self._on_ev_changed(self.slider_ev.value())
        self.btn_custom_dir.setVisible(self.cmb_export_dir.currentIndex() == 3)
        self._on_log_toggled(self.btn_log.isChecked())
        self._update_visibility()
        self._recompute_sun_curve()

    def closeEvent(self, event):
        self._save_settings()
        if self.gallery_worker and self.gallery_worker.isRunning():
            self.gallery_worker._abort = True
            self.gallery_worker.wait(1000)
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(2000)
        event.accept()
def main():
    multiprocessing.freeze_support()
    app_instance.setStyle("Fusion")
    win = MainWindow()
    win.show()
    QtCore.QTimer.singleShot(0, win._startauswahl)
    sys.exit(app_instance.exec_())


if __name__ == "__main__":
    main()
