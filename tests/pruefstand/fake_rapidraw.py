#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nachbau von "RapidRAW export" fuer den Pruefstand.

Verhaelt sich an den Stellen wie das Original (src-tauri/src/app/
launch_request.rs, export/mod.rs), auf die es ankommt:
  - "export <Quelle> --output <Ziel>": Quelle ist ein Bild oder ein Ordner,
    der samt Unterordnern durchsucht wird (auch verknuepfte Dateien)
  - die Regler kommen aus BILD.rrdata neben dem Bild; "--adjustments"
    ersetzt sie fuer alle Bilder
  - im Ordner-Export heissen die Ausgaben BILD_edited.<Format>, wobei das
    Format woertlich zur Endung wird (jpeg -> .jpeg); vorhandene Dateien
    werden nicht ueberschrieben, sondern BILD_edited_1 ...
  - der Regler "exposure" wirkt als 2^(Wert / 0,8)
  - die Ausgabe bekommt das Datum der Quelle (preserve_timestamps)
  - ohne "export" oeffnet sich die Oberflaeche und kehrt nie zurueck
    (so verhaelt sich eine Fassung vor 1.6)
"""
import os, sys, time, json
import numpy as np
import cv2

RAW = ('.nef', '.cr2', '.cr3', '.arw', '.dng', '.raf', '.orf', '.rw2')


def regler(bild):
    """Die Regler des Bildes aus seiner .rrdata (fehlt sie: Grundwerte)."""
    pfad = bild + ".rrdata"
    if not os.path.exists(pfad):
        return {}
    with open(pfad, encoding='utf-8') as f:
        doc = json.load(f)              # unlesbar: Fehler wie im Original
    adj = doc.get('adjustments')
    return adj if isinstance(adj, dict) else {}


def entwickle(pfad, adj, tief):
    with open(pfad, 'rb') as f:
        lin = np.load(f).astype(np.float64) / 65535.0
    werkzeuge = adj.get('activeTools') or {}
    if werkzeuge.get('basic', True):
        lin = lin * 2.0 ** (float(adj.get('exposure') or 0.0) / 0.8)
        kontrast = float(adj.get('contrast') or 0.0)
    else:
        kontrast = 0.0
    # Tonwertkurve mit Schulter (nicht linear: die Nachkalibrierung hat
    # etwas zu tun)
    lin = lin * (1.0 + lin / 9.0) / (1.0 + lin) * 1.9
    if kontrast:
        lin = 0.18 * np.power(np.maximum(lin, 1e-9) / 0.18, 1.0 + kontrast / 200.0)
    s = np.where(lin <= 0.0031308, 12.92 * lin,
                 1.055 * np.power(np.clip(lin, 0, 1), 1 / 2.4) - 0.055)
    s = np.clip(s, 0, 1)
    satt = float(adj.get('saturation') or 0.0)
    if satt:
        luma = (s[..., 0] * 0.2126 + s[..., 1] * 0.7152 + s[..., 2] * 0.0722)[..., None]
        s = np.clip(luma + (s - luma) * (1 + satt / 100.0), 0, 1)
    if tief:
        return (s * 65535 + 0.5).astype(np.uint16)
    return (s * 255 + 0.5).astype(np.uint8)


def main():
    a = sys.argv[1:]
    if not a or a[0] != "export":
        # Oberflaeche: wartet, bis jemand das Fenster schliesst
        while True:
            time.sleep(1)
    quelle = a[1] if len(a) > 1 and not a[1].startswith('-') else ""
    ausgabe, fmt, qual, tiefe, eigene = "", "jpeg", 90, 16, None
    i = 2
    while i < len(a):
        x = a[i]
        if x == "--output": ausgabe = a[i + 1]; i += 1
        elif x == "--format": fmt = a[i + 1]; i += 1
        elif x == "--quality": qual = int(a[i + 1]); i += 1
        elif x == "--tiff-bit-depth": tiefe = int(a[i + 1]); i += 1
        elif x == "--adjustments": eigene = a[i + 1]; i += 1
        i += 1
    if not os.path.exists(quelle):
        print(f"Headless export failed: Source path does not exist: {quelle}")
        return 1
    if os.path.isdir(quelle):
        bilder = []
        for wurzel, _ordner, dateien in os.walk(quelle):
            for d in sorted(dateien):
                if d.lower().endswith(RAW):
                    bilder.append(os.path.join(wurzel, d))
    else:
        bilder = [quelle]
    if not bilder:
        print("Headless export failed: No supported images found at the source path.")
        return 1
    einzel = (len(bilder) == 1 and os.path.splitext(ausgabe)[1] != ""
              and not os.path.isdir(ausgabe))
    os.makedirs(os.path.dirname(ausgabe) if einzel else ausgabe, exist_ok=True)
    adj_alle = None
    if eigene:
        with open(eigene, encoding='utf-8') as f:
            adj_alle = json.load(f)
    pause = float(os.environ.get("FAKE_VERZOEGERUNG", "0"))
    print(f"Found {len(bilder)} images to export. Processing...")
    fehler = 0
    for b in bilder:
        try:
            adj = adj_alle if adj_alle is not None else regler(b)
            bild = entwickle(b, adj, fmt == "tiff" and tiefe == 16)
        except Exception as e:
            print(f"Failed to export {b}: {e}")
            fehler += 1
            continue
        if pause:
            time.sleep(pause)
        if einzel:
            ziel = ausgabe
        else:
            stamm = os.path.splitext(os.path.basename(b))[0] + "_edited"
            ziel = os.path.join(ausgabe, f"{stamm}.{fmt}")
            n = 1
            while os.path.exists(ziel):
                ziel = os.path.join(ausgabe, f"{stamm}_{n}.{fmt}")
                n += 1
        bgr = cv2.cvtColor(bild, cv2.COLOR_RGB2BGR)
        if fmt == "tiff":
            ok, daten = cv2.imencode(".tif", bgr)
        else:
            ok, daten = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, min(100, qual)])
        with open(ziel, "wb") as f:
            f.write(daten.tobytes())
        # wie das Original (preserve_timestamps): Datum der Aufnahme
        st = os.stat(b)
        os.utime(ziel, (st.st_atime, st.st_mtime))
    if fehler:
        print(f"Headless export failed: Export completed with {fehler} errors.")
        return 1
    print("Headless export completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
