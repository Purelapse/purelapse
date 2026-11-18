# Purelapse

**Zeitraffer ohne Flackern – aus RAW- oder JPG-Serien, mit ART, RawTherapee oder Darktable.**

> ⚠️ **Beta-Version.** Purelapse wird aktiv entwickelt. Bitte Originalbilder
> sichern und Fehler als [Issue](https://github.com/slvobng/purelapse/issues) melden.

*English summary: Purelapse is a deflicker and rendering tool for timelapse
sequences on Linux. It measures every frame, drives ART/RawTherapee/Darktable
for RAW development, re-measures the developed result and recalibrates until
the remaining flicker is below 0.008 EV, then encodes the video with FFmpeg.
The user interface is available in German and English.*

![Purelapse: Bildleiste, Helligkeitsverlauf und Einstellungen](docs/screenshot.jpg)

## Was Purelapse macht

Bei Zeitraffern mit wechselndem Licht (Sonnenuntergang, Heiliger Gral,
Nachtaufnahmen) springt die Helligkeit von Bild zu Bild. Purelapse glättet
diesen Verlauf:

1. **Pass 1** misst die Helligkeit jedes RAWs in linearem Licht und schreibt
   eine Belichtungskorrektur in die Begleitdateien der Engine (`.arp`, `.pp3`
   oder `.xmp`).
2. **Keyframes** (freiwillig): einzelne Bilder gestalten – direkt in Purelapse
   über die Schnelleinstellungen oder in der Engine. Purelapse blendet
   dazwischen weich über.
3. **Pass 2** lässt die Engine alle Bilder entwickeln, misst das Ergebnis nach,
   korrigiert die Abweichungen in weiteren Runden und erzeugt das Video.

Weitere Funktionen: Schnellvorschau aus den Kamera-Vorschaubildern,
Start-/Endbild, Messbereich, 16:9-Kamerafahrt, Motion Blur, Stabilisierung,
Hardware-Kodierung (NVIDIA, Intel QuickSync, VAAPI), Warteschlange und
Telegram-Benachrichtigung nach Abschluss.

## Installation (Linux)

1. **RawTherapee** und/oder **ART** installieren (für die RAW-Entwicklung).
2. Unter [Releases](https://github.com/slvobng/purelapse/releases) die Datei `Purelapse-…-x86_64.AppImage`
   herunterladen.
3. Ausführbar machen und starten:
   ```bash
   chmod +x Purelapse-*-x86_64.AppImage
   ./Purelapse-*-x86_64.AppImage
   ```
4. In Purelapse unter **Einstellungen…** den Pfad zu `rawtherapee-cli` bzw.
   `ART-cli` eintragen.

Die AppImage enthält Python, Qt, OpenCV, rawpy und FFmpeg. Sie läuft auf
Linux Mint 21 / Ubuntu 22.04 und neuer. Ist ein System-FFmpeg vorhanden,
wird dieses bevorzugt (passend zum Grafiktreiber).

## Aus dem Quelltext starten

```bash
git clone https://github.com/slvobng/purelapse.git
cd purelapse
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python purelapse_main.py
```

Unter Windows (bisher ungetestet): `purelapse_windows.bat` doppelklicken.

## Selbst bauen

| Ergebnis | Befehl | Voraussetzung |
|---|---|---|
| Linux-AppImage | `bash build_appimage.sh` | Docker, Internet |
| Windows-`.exe` | `build_windows.bat` | Python 3, Internet |

## Lizenz

Purelapse steht unter der [GNU General Public License v3](LICENSE).

Purelapse ruft ART, RawTherapee, Darktable und FFmpeg als eigenständige
Programme auf; deren Lizenzen gelten für diese Programme. Die AppImage
enthält ein FFmpeg aus dem Paket `imageio-ffmpeg`.

Copyright (C) 2026 slvobng
