#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nachbau von rawtherapee-cli / ART-cli fuer den Pruefstand.

Verhaelt sich an den Stellen wie das Original, auf die es ankommt:
  - "-s" nimmt bei fehlendem oder unlesbarem Profil stillschweigend die
    Standardwerte und schreibt nur eine Warnung nach stderr
  - "-S" bricht fuer dieses Bild ab
  - ein Profil ohne [Version] als erste Sektion oder mit einer Kommazahl
    in einer Ganzzahlliste gilt als nicht ladbar
  - die Tonwertkurve ist NICHT linear, damit die Nachkalibrierung etwas
    zu tun hat - genau wie bei der echten Engine

Unter dem Namen ...ART... sucht es .arp, sonst .pp3.
"""
import os, sys, time
import numpy as np
import cv2

ART = "art" in os.path.basename(os.environ.get("FAKE_ENGINE_NAME") or sys.argv[0]).lower()
EXT = ".arp" if ART else ".pp3"

STANDARD_RT = """[Version]
AppVersion=5.9
Version=346

[General]
Rank=0
ColorLabel=0
InTrash=false

[Exposure]
Auto=false
Clip=0.02
Compensation=0
Brightness=0
Contrast=0
Saturation=0
Black=0
HighlightCompr=0
HistogramMatching=true
CurveFromHistogramMatching=false
CurveMode=Standard
CurveMode2=Standard
Curve=0;
Curve2=0;

[HLRecovery]
Enabled=false
Method=Coloropp

[Channel Mixer]
Enabled=false
Red=1000;0;0;
Green=0;1000;0;
Blue=0;0;1000;

[Sharpening]
Enabled=false
Method=usm
Radius=0.5
Amount=200
Threshold=20;80;2000;1200;

[White Balance]
Enabled=true
Setting=Camera
Temperature=5500
Green=1

[Directional Pyramid Denoising]
Enabled=false
Luma=0
Chroma=15
Gamma=1.7

[Vibrance]
Enabled=false
Pastels=0
Saturated=0
PSThreshold=0;75;
ProtectSkins=false
AvoidColorShift=true
PastSatTog=true

[Shadows & Highlights]
Enabled=false
Highlights=0
HighlightTonalWidth=70
Shadows=0
ShadowTonalWidth=30
Radius=40
Lab=false

[RAW]
HotPixelFilter=false
DeadPixelFilter=false
HotDeadPixelThresh=100
"""

STANDARD_ART = """[Version]
AppVersion=1.25
Version=1040

[General]
Rank=0
ColorLabel=0
InTrash=false

[Exposure]
Enabled=true
Compensation=0
Black=0
HLRecovery=Off
HLRecoveryBlur=0

[Saturation]
Enabled=false
Saturation=0
Vibrance=0

[ToneCurve]
Enabled=true
Contrast=0
HistogramMatching=true
CurveFromHistogramMatching=false
CurveMode=Neutral
Curve=0;
Curve2=0;

[Luminance Curve]
Enabled=false
Brightness=0
Contrast=0
Chromaticity=0

[ToneEqualizer]
Enabled=false
Band0=0
Band1=0
Band2=0
Band3=0
Band4=0
Regularization=4
Pivot=0

[Channel Mixer]
Enabled=false
Red=1000;0;0;
Green=0;1000;0;
Blue=0;0;1000;

[Sharpening]
Enabled=false
Contrast=20
Method=rld
Radius=0.5
Amount=200
Threshold=20;80;2000;1200;

[White Balance]
Enabled=true
Setting=Camera
Temperature=5500
Green=1
Multipliers=1;1;1;

[Denoise]
Enabled=false
ColorSpace=RGB
Luminance=0
Chrominance=15

[RAW]
HotPixelFilter=false
DeadPixelFilter=false
HotDeadPixelThresh=100
"""
STANDARD = STANDARD_ART if ART else STANDARD_RT


def lies_profil(text):
    """Rueckgabe: (dict, fehlergrund oder None)"""
    d, sek, erste = {}, None, None
    for zeile in text.splitlines():
        z = zeile.strip()
        if not z or z.startswith('#'):
            continue
        if z.startswith('[') and z.endswith(']'):
            sek = z[1:-1]
            if erste is None:
                erste = sek
            d.setdefault(sek, {})
        elif '=' in z and sek is not None:
            k, v = z.split('=', 1)
            d[sek][k.strip()] = v.strip()
    if erste != 'Version':
        return d, "erste Sektion ist nicht [Version]"
    for sek in ('Channel Mixer',):
        for k in ('Red', 'Green', 'Blue'):
            v = d.get(sek, {}).get(k)
            if v is not None and '.' in v:
                return d, f"Kommazahl in Ganzzahlliste [{sek}] {k}"
    return d, None


def zahl(d, sek, key, standard=0.0):
    try:
        return float(str(d.get(sek, {}).get(key, standard)).split(';')[0])
    except (TypeError, ValueError):
        return standard


def wahr(d, sek, key):
    return str(d.get(sek, {}).get(key, 'false')).strip().lower() == 'true'


def auto_kurve(pfad, profil):
    """
    Auto-angepasste Tonkurve wie im Original: steht HistogramMatching an
    und ist die Kurve nicht festgeschrieben (CurveFromHistogramMatching),
    rechnet die Engine fuer JEDES Bild eine eigene Kurve
    (simpleprocess.cc, getAutoMatchedToneCurve). Hier: eine je Datei
    andere Gradation um das mittlere Grau.
    Rueckgabe: (Gradation oder None, Modus ist an)
    """
    sek = 'ToneCurve' if ART else 'Exposure'
    an = wahr(profil, sek, 'HistogramMatching')
    fest = wahr(profil, sek, 'CurveFromHistogramMatching')
    if ART and fest:
        an = False                      # procparams.cc: histmatching = false
    if ART and not wahr(profil, sek, 'Enabled'):
        return None, an
    if an and not fest:
        import zlib
        rng = np.random.default_rng(zlib.crc32(os.path.basename(pfad).encode()))
        return float(np.clip(1.0 + 0.10 * rng.normal(), 0.75, 1.25)), an
    return None, an


def entwickle(pfad, profil):
    with open(pfad, 'rb') as f:
        lin = np.load(f).astype(np.float64) / 65535.0
    lin = lin * 2.0 ** zahl(profil, 'Exposure', 'Compensation')
    if ART:
        hell = zahl(profil, 'Luminance Curve', 'Brightness')
        satt = zahl(profil, 'Saturation', 'Saturation')
    else:
        hell = zahl(profil, 'Exposure', 'Brightness')
        satt = zahl(profil, 'Exposure', 'Saturation')
    gradation, auto_an = auto_kurve(pfad, profil)
    if auto_an and not ART:
        hell = 0.0                      # RawTherapee: brightness = contrast = 0
    if gradation is not None:
        lin = 0.18 * np.power(np.maximum(lin, 1e-9) / 0.18, gradation)
    lin = lin * 2.0 ** (hell / 66.0)
    # Nichtlineare Tonwertkurve mit Schulter
    lin = lin * (1.0 + lin / 9.0) / (1.0 + lin) * 1.9
    s = np.where(lin <= 0.0031308, 12.92 * lin,
                 1.055 * np.power(np.clip(lin, 0, 1), 1 / 2.4) - 0.055)
    s = np.clip(s, 0, 1)
    if satt:
        luma = (s[..., 0] * 0.2126 + s[..., 1] * 0.7152 + s[..., 2] * 0.0722)[..., None]
        s = np.clip(luma + (s - luma) * (1 + satt / 100.0), 0, 1)
    if os.environ.get("FAKE_TIEF") == "1":
        return (s * 65535 + 0.5).astype(np.uint16)
    return (s * 255 + 0.5).astype(np.uint8)


def main():
    a = sys.argv[1:]
    out, nur_profil_dir, sidecar, streng, qual = None, None, False, False, 92
    mit_standard = False
    tiff, tiefe = False, 8
    zusatz_profile = []
    dateien = []
    i = 0
    while i < len(a):
        x = a[i]
        if x == '-o': out = a[i + 1]; i += 1
        elif x == '-O': out = a[i + 1]; nur_profil_dir = a[i + 1]; i += 1
        elif x == '-d': mit_standard = True
        elif x == '-p': zusatz_profile.append(a[i + 1]); i += 1
        elif x == '-s': sidecar = True
        elif x == '-S': sidecar = True; streng = True
        elif x.startswith('-j'): qual = int(x[2:] or 92)
        elif x in ('-t', '-tz'): tiff = True
        elif x.startswith('-b'): tiefe = int(x[2:].rstrip('f') or 8)
        elif x == '-c': dateien = a[i + 1:]; break
        i += 1
    if not out or not dateien:
        sys.stderr.write("Aufruf unvollstaendig\n")
        return 2
    einzel = out.lower().endswith(('.jpg', '.jpeg')) and not os.path.isdir(out)
    os.makedirs(os.path.dirname(out) if einzel else out, exist_ok=True)
    pause = float(os.environ.get("FAKE_VERZOEGERUNG", "0"))
    fehler = 0
    for pfad in dateien:
        print(f"Output is {qual}-quality JPEG. Processing: {pfad}")
        # Ohne "-d" gelten die eingebauten Grundwerte, und in denen ist
        # die auto-angepasste Tonkurve AUS. Erst das Standardprofil fuer
        # RAW-Dateien ("Auto-Matched Curve") schaltet sie ein.
        grund = STANDARD if mit_standard else STANDARD.replace(
            "HistogramMatching=true", "HistogramMatching=false")
        profil, _ = lies_profil(grund)
        if mit_standard:
            print("  Merging default raw processing profile.")
        if sidecar:
            sc = pfad + EXT
            grund = None
            eigenes = None
            if not os.path.exists(sc):
                grund = "fehlt"
            else:
                eigenes, grund = lies_profil(open(sc, encoding='utf-8', errors='ignore').read())
            if grund:
                sys.stderr.write(f"Warning: sidecar file requested but not found for: {sc}\n")
                if streng:
                    sys.stderr.write(f"Error: no sidecar procparams found for: {pfad}\n")
                    fehler += 1
                    continue
            else:
                for sek, werte in eigenes.items():
                    profil.setdefault(sek, {}).update(werte)
                print("  Merging sidecar procparams.")
        for zp in zusatz_profile:           # "-p": weiteres Profil obenauf
            extra, grund_p = lies_profil(open(zp, encoding='utf-8', errors='ignore').read())
            if grund_p:
                sys.stderr.write(f"Error: could not load profile {zp}\n")
                fehler += 1
                extra = None
                break
            for sek, werte in extra.items():
                profil.setdefault(sek, {}).update(werte)
            print("  Merging procparams #0")
        if zusatz_profile and extra is None:
            continue
        try:
            os.environ["FAKE_TIEF"] = "1" if (tiff and tiefe == 16) else "0"
            bild = entwickle(pfad, profil)
            gr = profil.get('Resize', {})
            if str(gr.get('Enabled', 'false')).lower() == 'true' and gr.get('DataSpecified') == '3':
                h, w = bild.shape[:2]
                f = min(float(gr.get('Width', w)) / w, float(gr.get('Height', h)) / h)
                if f < 1.0:
                    bild = cv2.resize(bild, (max(1, int(round(w * f))), max(1, int(round(h * f)))),
                                      interpolation=cv2.INTER_AREA)
        except Exception as e:
            sys.stderr.write(f"Error loading file: {pfad} ({e})\n")
            fehler += 1
            continue
        if pause:
            time.sleep(pause)
        stamm = os.path.splitext(os.path.basename(pfad))[0]
        if tiff:
            ziel = os.path.join(out, stamm + ".tif")
            cv2.imwrite(ziel, cv2.cvtColor(bild, cv2.COLOR_RGB2BGR))
        else:
            ziel = out if einzel else os.path.join(out, stamm + ".jpg")
            cv2.imwrite(ziel, cv2.cvtColor(bild, cv2.COLOR_RGB2BGR),
                        [cv2.IMWRITE_JPEG_QUALITY, min(100, qual)])
        if nur_profil_dir:
            with open(ziel + EXT, 'w', encoding='utf-8') as f:
                f.write(grund)
    return -2 & 0xFF if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
