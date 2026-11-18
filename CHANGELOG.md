# Changelog

Versionsnummern folgen [Semantic Versioning](https://semver.org/lang/de/).
Das Anhaengsel `-beta` kennzeichnet oeffentliche Testversionen.

## [2.39.0-beta] – 2026-11-18

Erste oeffentliche Testversion.

### Enthalten
- Deflicker fuer RAW (ART, RawTherapee, Darktable) in zwei Durchgaengen:
  Pass 1 misst die RAWs in linearem Licht, Pass 2 entwickelt, misst das
  Ergebnis nach und kalibriert, bis das Restflackern unter 0,008 EV liegt.
- Deflicker fuer JPG-Serien in einem Durchgang.
- Keyframes mit weicher Ueberblendung; Schnelleinstellungen (Weissabgleich,
  Helligkeit, Kontrast, Saettigung, Schaerfe, Entrauschen, Lichter-
  Rekonstruktion) mit echter Vorschau durch die Engine.
- Schnellvorschau aus den eingebetteten Kamerabildern.
- Start- und Endbild, Messbereich (ROI), 16:9-Kamerafahrt, Motion Blur,
  Stabilisierung, Astro-Clean, Telemetrie-Overlay.
- Videoausgabe ueber FFmpeg: H.264/H.265 (CPU, NVIDIA, Intel QuickSync,
  VAAPI) und ProRes; Codec-Selbsttest vor jedem Lauf.
- Parallele Entwicklung und Messung auf mehreren Kernen.
- Warnungen fuer Luecken in der Sequenz, ausgebrannte und rosa verfaerbte
  Lichter.
- Warteschlange, Telegram-Benachrichtigung, Ablaufanzeige mit Zeiten,
  Protokoll mit Zeitstempeln, helles und dunkles Design, Deutsch/Englisch.
- AppImage fuer Linux, Startskript und Bauskript fuer Windows.

### Bekannte Einschraenkungen
- Unter Windows bisher nicht getestet.
- Darktable: Schnelleinstellungen und echte Vorschau gibt es nur fuer ART
  und RawTherapee.
