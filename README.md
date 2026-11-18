# Purelapse

**Deutsch** · [English](README.en.md)

**Zeitraffer ohne Flackern – aus RAW- oder JPG-Serien, mit ART, RawTherapee oder Darktable.**

> ⚠️ **Beta-Version.** Purelapse wird aktiv entwickelt. Bitte Originalbilder
> sichern und Fehler als [Issue](https://github.com/slvobng/purelapse/issues) melden.

![Purelapse: Bildleiste, Helligkeitsverlauf und Einstellungen](docs/screenshot.jpg)

## Inhalt

- [Was Purelapse macht](#was-purelapse-macht)
- [Funktionen im Überblick](#funktionen-im-überblick)
- [Deflicker](#deflicker)
- [Holy Grail: Tag-Nacht-Übergänge](#holy-grail-tag-nacht-übergänge)
- [Keyframes und Schnelleinstellungen](#keyframes-und-schnelleinstellungen)
- [Video-Ausgabe und Qualität](#video-ausgabe-und-qualität)
- [Bild und Effekte](#bild-und-effekte)
- [Analyse und Warnungen](#analyse-und-warnungen)
- [Vorschau und Vergleich](#vorschau-und-vergleich)
- [Warteschlange und Telegram](#warteschlange-und-telegram)
- [Leistung](#leistung)
- [Bedienung](#bedienung)
- [Installation (Linux)](#installation-linux)
- [Aus dem Quelltext starten](#aus-dem-quelltext-starten)
- [Selbst bauen](#selbst-bauen)
- [Bekannte Einschränkungen](#bekannte-einschränkungen)
- [Lizenz](#lizenz)

## Was Purelapse macht

Bei Zeitraffern mit wechselndem Licht (Sonnenuntergang, Holy Grail,
Nachtaufnahmen) springt die Helligkeit von Bild zu Bild. Purelapse glättet
diesen Verlauf in drei Schritten:

1. **Pass 1 – Helligkeit glätten:** Purelapse misst die Helligkeit jedes RAWs
   in linearem Licht und schreibt eine Belichtungskorrektur in die
   Begleitdateien der Engine (`.arp`, `.pp3` oder `.xmp`).
2. **Keyframes (freiwillig):** Einzelne Bilder gestalten – direkt in Purelapse
   über die Schnelleinstellungen oder in der Engine. Purelapse blendet
   dazwischen weich über.
3. **Pass 2 – Video rendern:** Die Engine entwickelt alle Bilder, Purelapse
   misst das Ergebnis nach, korrigiert die Abweichungen in weiteren Runden und
   erzeugt das Video.

JPG-Serien laufen in einem einzigen Durchgang, ohne externe Engine.

## Funktionen im Überblick

| Bereich | Funktionen |
|---|---|
| **Deflicker** | Messung in linearem Licht (16 Bit), zweistufige Glättung, Nachkalibrierung bis unter 0,008 EV Restflackern, Messbereich (ROI), Lichtverlauf Sonnenaufgang/-untergang/gleichbleibend |
| **Holy Grail** | Belichtungs- und ISO-Sprünge werden ausgeglichen, wechselndes Intervall wird erkannt, EXIF-Belichtung und Sonnenstand als Kurven |
| **RAW-Entwicklung** | ART, RawTherapee, Darktable; Formate NEF, CR2, CR3, DNG, ARW, RAF, ORF, RW2, PEF, SRW |
| **Keyframes** | Weiche Überblendung zwischen Keyframes, Schnelleinstellungen mit echter Engine-Vorschau, automatisch optimieren, Lichter-Rekonstruktion |
| **Video** | 720p bis 8K, 23,976 bis 120 fps, H.264, H.265, ProRes 422 HQ, CPU oder NVIDIA, Intel QuickSync, VAAPI, vier Qualitätsstufen |
| **Effekte** | Motion Blur (3–25 Bilder), 16:9-Kamerafahrt, Stabilisierung, Entrauschen, Hotpixel, Astro-Clean, Telemetrie-Overlay, Ein-/Ausblenden, rückwärts |
| **Kontrolle** | Schnellvorschau, 5-Bilder-Vorschau, Rohfassung, Vergleichsvideo, Lücken- und Lichter-Warnungen |
| **Ablauf** | Warteschlange, Telegram-Benachrichtigung, Fortsetzen nach Abbruch, parallele Verarbeitung |
| **Oberfläche** | Schrittleiste, Ablaufanzeige mit Zeiten, helles und dunkles Design, Deutsch und Englisch |

## Deflicker

- **Messung in linearem Licht.** RAWs werden mit 16 Bit und Gamma 1,0 gemessen.
  So bleibt die Messung auch in dunklen Nachtaufnahmen zuverlässig, wo eine
  8-Bit-Messung große Bildteile als Schwarz zusammenfassen würde.
- **Zweistufige Glättung.** Der Regler *Deflicker-Stärke* bestimmt, wie stark
  geglättet wird: niedrig entfernt nur schnelles Flackern, hoch formt auch den
  Lichtverlauf. Ab 85 % geht die Kurve stufenlos in eine reine
  Ausgleichsgerade über.
- **Lichtverlauf.** *Gleichbleibend* lässt den Verlauf, wie er ist;
  *Sonnenaufgang* und *Sonnenuntergang* erzwingen einen Verlauf, der nur heller
  bzw. nur dunkler wird.
- **Belichtung (EV).** Verschiebt die Zielhelligkeit der ganzen Sequenz um bis
  zu ±3 EV.
- **Messbereich (ROI).** Beschränkt die Messung auf einen Bildausschnitt –
  sinnvoll, wenn Sonne, Lampen oder bewegte Objekte die Messung stören.
- **Nachkalibrierung.** Nach dem Entwickeln misst Purelapse das Ergebnis der
  Engine, schreibt die verbleibende Abweichung in die Begleitdateien zurück und
  lässt neu entwickeln – nur die Bilder, die sich geändert haben. Bis zu drei
  Runden; Abbruch, sobald das Restflackern unter 0,008 EV liegt.
- **Bestehende Bearbeitungen bleiben erhalten.** Purelapse setzt nur die
  Belichtung im Profil. Bei Darktable kommt ein eigenes Belichtungsmodul hinzu,
  der bestehende Verlauf der Bearbeitung bleibt unangetastet.
- **JPG-Workflow.** JPG-Serien werden direkt und ohne Engine entflackert, auf
  Wunsch auch nur als Einzelbilder ohne Video.

## Holy Grail: Tag-Nacht-Übergänge

Bei Holy-Grail-Aufnahmen verändert die Kamera während der Serie Belichtungszeit,
Blende oder ISO. Purelapse ist dafür ausgelegt:

- **Belichtungssprünge ausgleichen.** Weil jedes RAW in linearem Licht gemessen
  wird, erscheinen die Sprünge durch geänderte Kameraeinstellungen als
  Helligkeitsstufen – und werden vom Deflicker geglättet.
- **Wechselndes Intervall.** Wächst oder schrumpft das Aufnahmeintervall mit der
  Belichtungszeit, erkennt Purelapse das als normal und meldet nur echte Lücken.
- **Kurven zur Kontrolle.** Neben der Helligkeit lassen sich die
  EXIF-Belichtung und das Intervall im Diagramm einblenden.
- **Sonnenstand.** Mit Breiten- und Längengrad (oder GPS aus dem Bild) zeigt
  Purelapse den Sonnenstand als Kurve und markiert die Grenzen der
  bürgerlichen, nautischen und astronomischen Dämmerung – ideal, um dort
  Keyframes zu setzen.

## Keyframes und Schnelleinstellungen

- **Keyframes.** Einzelne Bilder werden als Keyframe markiert (5 Sterne) und in
  der Engine oder in Purelapse gestaltet. Beim Rendern überträgt Purelapse die
  Einstellungen weich auf alle Bilder dazwischen.
- **Schnelleinstellungen** (ART und RawTherapee) direkt in Purelapse über
  *Keyframe einstellen…*, ohne die Engine zu öffnen:

  | Regler | Bereich |
  |---|---|
  | Farbtemperatur | 2000 – 12000 K |
  | Grünabgleich | 0,6 – 1,8 |
  | Helligkeit, Kontrast, Sättigung | −100 – +100 |
  | Schärfe | 1 – 1000 |
  | Entrauschen Helligkeit / Farbe | 0 – 100 |

  Jeder Regler hat ein eigenes Häkchen: Was nicht angehakt ist, bleibt im
  Profil unverändert. Die Belichtung bleibt ausgenommen – die gehört dem
  Deflicker.
- **Echte Vorschau.** Die Engine entwickelt das Bild mit den gewählten Werten,
  mit Histogramm und *Vorher zeigen*.
- **Automatisch optimieren.** Misst das Bild und schlägt Helligkeit, Kontrast,
  Sättigung, Schärfe und Entrauschen (passend zum ISO-Wert) vor – jeweils mit
  Begründung, worauf der Wert beruht.
- **Von anderem Keyframe übernehmen.** Einstellungen eines Keyframes auf einen
  anderen kopieren.
- **Lichter-Rekonstruktion.** Gegen den rosa Sonnenball: rechnet ausgebrannte
  Farbkanäle aus der Umgebung nach (ART: Blend, Farbe, Ausgewogen;
  RawTherapee: Blend, Farbe, Farbfortsetzung).
- **Nur Keyframes zeigen.** Filtert die Bildleiste auf die markierten Bilder.

## Video-Ausgabe und Qualität

| Einstellung | Möglichkeiten |
|---|---|
| **Auflösung (16:9)** | 720p (HD Ready), 1080p (Full HD), 1440p (2,5K), 2160p (4K), 4320p (8K) |
| **Bildrate** | 23,976 · 24 · 25 · 29,97 · 30 · 50 · 59,94 · 60 · 120 fps |
| **Qualität** | Visuell verlustfrei (CRF 16) · Hoch (CRF 20) · Standard (CRF 23) · Niedrig (CRF 28) |
| **Ein-/Ausblenden** | Aus · 0,5 · 1 · 2 · 3 Sekunden aus/nach Schwarz |
| **Speicherort** | Bilderordner, übergeordneter Ordner, Programmordner oder eigener Ordner |
| **Vorhandene Datei** | Neue Version anlegen (`_v1`, `_v2`, …) oder überschreiben |

**Video-Codecs:**

| Codec | Kodierung | Datei |
|---|---|---|
| H.264 | CPU (libx264) | `.mp4` |
| H.264 | NVIDIA GPU (NVENC) | `.mp4` |
| H.264 | Intel QuickSync | `.mp4` |
| H.264 | VAAPI (AMD/Intel) | `.mp4` |
| H.265 / HEVC | CPU (libx265) | `.mp4` |
| H.265 / HEVC | NVIDIA GPU (NVENC) | `.mp4` |
| H.265 / HEVC | Intel QuickSync | `.mp4` |
| H.265 / HEVC | VAAPI (AMD/Intel) | `.mp4` |
| Apple ProRes 422 HQ | CPU | `.mov` |

- **Codec-Selbsttest.** Vor jedem Lauf prüft Purelapse, ob der gewählte
  Hardware-Codec auf dem Rechner funktioniert, und bietet sonst den passenden
  CPU-Codec an.
- **Geschätzte Dateigröße** wird schon vor dem Start angezeigt.

## Bild und Effekte

- **Motion Blur.** Mittelt 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 18, 20 oder 25
  Bilder zu einem Videobild – für weiche, filmische Bewegung von Wolken,
  Wasser und Sternen.
- **16:9-Kamerafahrt / Crop.** Bildausschnitt für das erste und das letzte
  Bild festlegen; dazwischen fährt die Kamera weich von A nach B. Ohne Angabe
  wird mittig auf 16:9 zugeschnitten.
- **Optische Stabilisierung.** Gleicht Verwacklungen zwischen den Bildern aus
  (kostet etwas Bildrand).
- **Entrauschen.** Rauschminderung, stärker bei hohen ISO-Werten.
- **Tote / heiße Pixel entfernen.** Bei RAW über die Engine; bei JPG sucht
  Purelapse Punkte, die in der ganzen Sequenz an derselben Stelle auffallen –
  Sterne und Motivdetails bleiben unangetastet.
- **Astro-Clean.** Entfernt Satellitenspuren durch Vergleich jedes Bildes mit
  seinen beiden Nachbarn.
- **Telemetrie-Overlay.** Blendet Uhrzeit, ISO, Blende und Belichtungszeit ins
  Video ein.
- **Rückwärts rendern.** Spielt die Sequenz rückwärts ab.
- **Start- und Endbild.** Begrenzt den ganzen Arbeitsgang auf einen Teil der
  Serie; wird je Ordner gespeichert.

## Analyse und Warnungen

- **Helligkeitsdiagramm** mit gemessener Kurve, Zielkurve, Keyframes und
  gewähltem Bild; zuschaltbar: Weißabgleich, Belichtung (EXIF), Intervall,
  Clipping, Restflackern und Sonnenstand.
- **Lücken in der Sequenz.** Fehlende Aufnahmen werden aus den Aufnahmezeiten
  erkannt und mit Position angezeigt.
- **Ausgebrannte Lichter.** Anteil der Bildpunkte, die auf dem Sensor am
  Anschlag stehen, je Bild.
- **Rosa verfärbte Lichter.** Warnung vor dem typischen magentafarbenen
  Sonnenball, mit Hinweis auf die Lichter-Rekonstruktion.
- **Schwankender Weißabgleich** der Kamera innerhalb der Serie wird gemeldet.
- **Diagnose-Modus.** Schreibt auf Wunsch Messprotokolle (CSV) und
  Prüfberichte in den Bilderordner.

## Vorschau und Vergleich

- **⚡ Schnellvorschau.** Ein grobes Video in Minuten statt Stunden, aus den
  eingebetteten Vorschaubildern der Kamera, mit der Glättung aus dem Diagramm
  und dem gewählten Bildausschnitt (bis 1280 Pixel breit).
- **Vorschau (5 Bilder).** Entwickelt fünf über die Sequenz verteilte Bilder
  mit allen Einstellungen – spart einen kompletten Fehldurchlauf.
- **Rohfassung.** Der Zeitraffer ganz ohne Bearbeitung, als Referenz.
- **Vergleichsvideo.** Stellt zwei fertige Videos nebeneinander oder als
  geteiltes Bild gegenüber.

## Warteschlange und Telegram

- **Warteschlange.** Mehrere Ordner mit jeweils eigenen Einstellungen
  einreihen und nacheinander abarbeiten lassen. Abbrechen hält den Stapel an;
  beim nächsten Start geht es an derselben Stelle weiter.
- **Telegram-Benachrichtigung.** Nach Abschluss oder bei einem Fehler schickt
  Purelapse eine Nachricht mit Ordner, Arbeitsschritten, Dauer und
  Restflackern. Die Chat-ID ermittelt Purelapse selbst; eine Testnachricht
  prüft die Verbindung.

## Leistung

- **Parallele Entwicklung.** Mehrere Engine-Prozesse mit je wenigen Kernen
  statt eines Prozesses mit allen Kernen – auf vielkernigen Rechnern deutlich
  schneller. *Automatisch* richtet sich nach Kernzahl und freiem
  Arbeitsspeicher.
- **Parallele Messung** auf mehreren Kernen.
- **Fortsetzen nach Abbruch.** Bereits entwickelte, unveränderte Bilder werden
  nicht noch einmal entwickelt.

## Bedienung

- **Schrittleiste** führt durch Bilder laden → Helligkeit glätten → Keyframes
  bearbeiten → Video rendern; erledigte Schritte sind markiert.
- **Startdialog** bietet an, den letzten Arbeitsgang fortzusetzen.
- **Ablaufanzeige** mit Fortschritt, Restzeit und Dauer jedes Schritts.
- **Protokoll** mit Zeitstempeln; öffnet sich bei Fehlern von selbst.
- **Zurücksetzen** löscht gezielt Arbeitsdateien im Bilderordner.
- **Engine-Erkennung.** Liegen schon Begleitdateien im Ordner, stellt
  Purelapse die passende Engine selbst ein.
- **Helles und dunkles Design**, Oberfläche auf **Deutsch und Englisch**.

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

Für JPG-Serien wird keine Engine benötigt.

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

## Bekannte Einschränkungen

- Unter Windows bisher nicht getestet.
- Darktable: Schnelleinstellungen, echte Vorschau und Hotpixel-Entfernung gibt
  es nur für ART und RawTherapee.

## Lizenz

Purelapse steht unter der [GNU General Public License v3](LICENSE).

Purelapse ruft ART, RawTherapee, Darktable und FFmpeg als eigenständige
Programme auf; deren Lizenzen gelten für diese Programme. Die AppImage
enthält ein FFmpeg aus dem Paket `imageio-ffmpeg`.

Copyright (C) 2026 slvobng
