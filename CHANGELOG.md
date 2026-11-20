# Changelog

Versionsnummern folgen [Semantic Versioning](https://semver.org/lang/de/).
Das Anhaengsel `-beta` kennzeichnet oeffentliche Testversionen.

## [Unveröffentlicht]

### Webseite
- **Weltkarte „Purelapse in aller Welt“:** Besucher setzen einen Pin mit
  Reaktion und Engine, der Ort wird schon im Browser auf etwa 50 km
  gerundet. Gespeichert wird über einen Cloudflare Worker mit D1-Datenbank
  (Hoheitsgebiet EU); ein Pin je Besucher und Tag, Bot-Schutz mit Cloudflare
  Turnstile, der erst beim Setzen eines Pins lädt. Keine IP-Adressen, keine
  fremden Kartenkacheln – die Karte ist eine eigene Punktgrafik. Quelltext
  und Prüfung in `karte/`.

## [2.42.1-beta] – 2026-11-20

Fehlerbehebung für 2.42.0. Wer mit 16-Bit-Zwischenbildern arbeitet, sollte
umsteigen.

### Neu
- **Eingestellte Engine immer sichtbar:** Rechts in der Zeile unter dem
  Ordnerpfad steht „Engine: ART“, „Engine: RawTherapee“ bzw. „Engine:
  Darktable“, bei JPG-Serien „JPG · ohne Engine“. Fehlt bei RAW das
  Programm der Engine, steht dort eine Warnung. Ein Klick öffnet die
  Einstellungen.

### Behoben
- **16-Bit-Zwischenbilder mit Telemetrie-Overlay brachen ab** („img.depth() ==
  CV_8U in function 'putText'“), und zwar erst nach der Entwicklung, beim
  Rendern des Videos. OpenCV zeichnet Text nur in 8-Bit-Bilder. Die Zeile wird
  jetzt als 8-Bit-Maske gezeichnet und in das 16-Bit-Bild übertragen –
  Ergebnis wie bei 8 Bit. Die entwickelten Bilder bleiben erhalten; ein
  erneuter Start von Pass 2 rendert nur noch das Video.
- **Astro-Clean mit 16-Bit-Zwischenbildern:** Die Schwelle (30 Stufen) galt
  auch für 16 Bit, wo 30 von 65 535 Stufen Rauschen sind – nahezu jeder
  Bildpunkt wäre durch den Mittelwert der Nachbarbilder ersetzt worden. Sie
  wird jetzt mitskaliert.
- **Hinweis nach Pass 1 bei ausgefressenen Lichtern** war seit 2.42 falsch:
  Er behauptete, die Messung falle dort zu schwach aus, und empfahl einen
  Messbereich ohne Himmel. Seit 2.42 lässt die Messung ausgebrannte Stellen
  aus. Jetzt ein Hinweis statt einer Warnung: der Deflicker ist nicht
  betroffen, gegen eine rosa Sonne hilft „Lichter rekonstruieren“.
- Ebenso der Hinweistext am Lichter-Feld („in diesen Bildern unterschätzt die
  Messung die wahre Belichtung“).
- Hinweis zur Engine-Auswahl: Bei Darktable stand noch, Purelapse ergänze nur
  ein eigenes Belichtungs-Modul. Seit 2.42 schreibt es in die wirksame
  Belichtung und überträgt den Modulstapel der Keyframes.
- Hinweis „Parallele Prozesse“: „gilt nicht für Darktable“ stimmte nicht
  mehr. Die Einstellung gilt auch dort, begrenzt auf 4 Prozesse.

### Intern
- Neue Prüfung: Engine-Schild für alle Engines, JPG, fehlendes Programm
  und beide Sprachen.
- Neue Prüfung: Pass 2 mit 16-Bit-Zwischenbildern, Telemetrie, Astro-Clean,
  Motion Blur und Blende; Telemetrie und Astro-Clean in 8 und 16 Bit
  verglichen.

### Webseite
- Stand 2.42 und neuer Bereich „Technik“ (Deutsch und Englisch): alle
  Funktionen mit Rechenwegen, Grenzwerten, Engine-Aufrufen und Dateien, in
  16 aufklappbaren Kapiteln.
- Neue Seite „Versionen“ (`versionen.html` / `versions.html`) mit den
  wichtigsten Änderungen jeder Version ab 2.39, verlinkt aus Navigation,
  Download-Bereich und Fußzeile. Wird bei jedem Release ergänzt.

## [2.42.0-beta] – 2026-11-20

### Wichtig beim Umstieg
- **Eine Konfigurationsdatei:** Purelapse legt seine Einstellungen nur noch
  in `~/.config/purelapse/purelapse.json` ab, statt in bis zu 16 Einzeldateien
  `~/.purelapse_*` im Benutzerordner. Die alten Dateien werden beim ersten
  Start übernommen und danach entfernt. Die Datei ist nur für den Benutzer
  lesbar (sie enthält den Telegram-Token). Selbst erzeugte Basisprofile der
  Engines liegen jetzt im Datenordner (`~/.local/share/purelapse`).
- **Deflicker-Messung geändert:** Ausgebrannte Flächen (Sonne, Lampen)
  zählen nicht mehr mit (siehe unten). Bei Sequenzen mit Sonne fällt die
  Korrektur dadurch anders – richtiger – aus; Pass 1 und Pass 2 neu laufen
  lassen, statt alte Profile weiterzuverwenden.

### Bildqualität
- **Sonne und ausgebrannte Lichter:** Ausgebranntes bleibt gleich hell, egal
  wie die Kamera belichtet, und zog den Messwert zu sich – die Korrektur
  fiel zu schwach aus. Pass 1 lässt jetzt Bildpunkte weg, die auf dem
  Sensor ausgebrannt sind (plus einen schmalen Saum), und rechnet in 32 statt
  64 Bit (halber Speicher je Mess-Thread). Auf dem Prüfstand sank das
  sichtbare Restflackern mit Sonne von 0,011 EV (kleine Sonne) bzw. 0,05 EV
  (große Sonne) auf 0,0005 EV; ohne Sonne bleibt alles, wie es war. Auch im
  JPG-Ablauf: 0,025 → 0,0045 EV.
- **Nachkalibrierung bestimmt Ausgebranntes für die ganze Sequenz:** Im
  fertigen Bild hängt „ausgebrannt“ von der Korrektur ab (eine abgedunkelte
  Sonne ist grau statt weiß). Bild für Bild entschieden, „korrigierte“ die
  Nachkalibrierung dadurch Flackern, das es nicht gab, und machte es
  sichtbar (Prüfstand: 0,0002 → 0,0096 EV). Jetzt zählen nur Bereiche, die
  in keinem Bild der Sequenz ausbrennen; in allen 32 geprüften
  Kombinationen bleibt das Ergebnis bei 0,0002–0,0006 EV.
- **Kamerafahrt mit Bruchteilen von Bildpunkten:** Der Ausschnitt wurde auf
  ganze Bildpunkte gerundet, Breite und Höhe einzeln – langsame Fahrten
  ruckelten (Sprünge von 0,5 Bildpunkten) und das Seitenverhältnis
  „atmete“. Jetzt wird passend weichgezeichnet und genau abgetastet:
  gleichmäßige Bewegung (±0,013 Bildpunkte), die Schärfe schwankt nicht im
  Takt der Bildpunkte (0,1 %), gleich schnell wie vorher.
- **Sanftes Anfahren und Abbremsen** der Kamerafahrt (je 10 % der Laufzeit)
  statt schlagartigem Start und Halt.
- **Videofarben nach BT.709:** FFmpeg rechnete nach der Norm für
  Standard-Definition um und kennzeichnete nichts; Player gingen von HD aus,
  Grün- und Rottöne waren leicht verschoben. Jetzt BT.709, im Video
  gekennzeichnet.
- **Encoder gründlicher:** x264/x265 „slow“ statt „fast“, NVIDIA „p6“ statt
  „p4“, Intel QuickSync „slow“ – bessere Qualität bei gleicher Stufe.
- **HEVC 10 Bit** (CPU und NVIDIA) als neue Codecs – weniger Stufen in
  Himmelsverläufen.
- **16-Bit-Zwischenbilder (TIFF)** als Option in den Einstellungen: Die
  Engine entwickelt in Pass 2 nach 16-Bit-TIFF, das Video wird durchgehend
  in 16 Bit gerechnet. Braucht ein Vielfaches an Platz (bei 24 Megapixeln
  etwa 120 MB je Bild); Purelapse prüft vorher, ob er reicht. Wer
  umschaltet, bekommt die Bilder neu entwickelt.
- **Nachmessung genauer:** Die entwickelten Bilder wurden vor der Messung
  ohne Mittelung auf 320 Punkte Breite verkleinert – Sterne und feine
  Details erzeugten Messrauschen. Jetzt zählt jeder Bildpunkt, exakt
  gerechnet.
- **Bewegungsunschärfe** mittelt in 32 Bit und rundet, statt abzuschneiden.

### Darktable
- **Hotpixel-Korrektur wirkt jetzt** (Modul „Hotpixel“, wird bei Bedarf
  angelegt – auch in den Keyframes). Vorher wirkungslos.
- **Schnelleinstellungen für Darktable:** Helligkeit, Kontrast, Sättigung
  (Farbbalance RGB) und Schärfe. Weißabgleich und Entrauschen fehlen bewusst:
  Darktable speichert dort kameraabhängige Werte, die sich ohne die
  Farbmatrix der Kamera nicht berechnen lassen.
- **Echte Vorschau mit darktable-cli** in den Schnelleinstellungen.
- **darktable-cli parallel:** bis zu 4 Prozesse gleichzeitig, jeder mit
  eigenem Konfigurationsordner (darktable-cli sperrt seine
  Preset-Datenbank). Die Einstellungen und Presets des Nutzers werden
  übernommen. Nebenbei läuft Pass 2 jetzt auch bei geöffnetem darktable.
- Frische Profile aus Pass 1 behalten Darktables Grundeinstellungen
  (`auto_presets_applied`); nur aus Keyframes übernommene Stapel gelten als
  fertig.

### Neu
- **Protokoll vollständig zweisprachig:** 57 Meldungen, die auch in der
  englischen Oberfläche deutsch waren, gibt es jetzt auf Englisch.
- Die Knöpfe oben (Ordner wählen, Aktualisieren, Zurücksetzen,
  Einstellungen) sind jetzt Symbole; der Name steht im Hinweis beim
  Darüberfahren. Die Symbole wechseln mit dem Farbschema.
- Die Schrittknöpfe (Bilder laden, Helligkeit glätten, …) sind im unteren
  Fünftel in ihrer Farbe gefüllt statt nur mit einem dünnen Rand.
- Darktable-Keyframes übertragen jetzt den kompletten Modulstapel in die
  Bilder dazwischen, nicht nur die Belichtung. Zahlenwerte – Weißabgleich,
  Farbkalibrierung, Schärfe, Farbbalance RGB (Sättigung, Farbtöne auf dem
  kürzeren Weg um den Farbkreis), Filmic, Sigmoid, Tonwert-Equalizer,
  lokaler Kontrast und rund 60 weitere Module – werden weich überblendet.
  Schalter, Auswahllisten, Masken und Module, die nur in einem Keyframe
  vorkommen, kommen vom näheren Keyframe; Purelapse meldet sie vorher.
  Die Parameter-Layouts stammen aus dem Quelltext von darktable 4.6.1 und
  werden vor jeder Überblendung über Modulversion und Größe geprüft.
- Vor der Verteilung steht im Protokoll, welche Module aus den Keyframes
  übernommen und welche überblendet werden.
- Hinweis auf der Keyframe-Seite: in allen Keyframes dieselben Module
  verwenden (Verlauf kopieren mit Strg+Umschalt+C / Strg+Umschalt+V).
- Hinweis für Darktable: Darktable liest .xmp-Dateien nur beim ersten
  Import. Auf der Seite „Keyframes bearbeiten“ und beim ersten gesetzten
  Stern steht jetzt, wie Darktable die Sterne aus Purelapse übernimmt.

### Behoben
- **Geisterschrift:** Mit Bewegungsunschärfe und Telemetrie geriet der Text
  in den Bildpuffer und tauchte in den nächsten gemittelten Bildern als
  Schatten wieder auf.
- **Schreibfehler werden gemeldet:** Konnte ein ART/RawTherapee-Profil nicht
  geschrieben werden (Platte voll, keine Rechte), stand das nur auf der
  Konsole – das Video wurde ohne diese Korrektur gerendert. Jetzt hält der
  Lauf mit einer Meldung an. Ebenso bei den Deflicker-Basiswerten und der
  Kalibrierung.
- **darktable-cli kann nicht mehr hängen:** Zeitlimit von 10 Minuten je
  Bild; ein Abbruch beendet laufende Prozesse sofort (vorher wartete
  Purelapse das laufende Bild ab).
- **Dateien werden atomar geschrieben** (erst daneben, dann in einem Schritt
  an ihren Platz): Sidecars, Darktable-XMPs, Messdateien, Konfiguration.
  Bricht der Rechner mitten im Schreiben ab, bleibt die alte Fassung stehen.
- **Kein Hänger beim Ordnerwechsel:** Purelapse wartete unbegrenzt auf den
  Vorschau-Lader des alten Ordners; jetzt höchstens 0,3 s, der Rest läuft
  stumm im Hintergrund aus.
- Darktable-Hinweis in den Einstellungen war seit 2.40 veraltet („ändert
  nur die Belichtung“).
- Darktable: Der Deflicker-Wert landete in einer zweiten Belichtungsinstanz
  mit derselben Priorität wie Darktables eigene. Darktable fasst beide
  zusammen, der spätere Eintrag gewinnt – auf bearbeiteten Keyframes war
  der Deflicker-Wert dadurch wirkungslos. Purelapse schreibt jetzt, wie bei
  ART, in die wirksame Belichtungsinstanz; die eigene Belichtungsänderung
  des Nutzers bleibt als Abstand erhalten.
- Darktable: Belichtung wird auch bei benutzerdefinierter Modul-Reihenfolge
  geschrieben (vorher übersprungen).
- Darktable: Fehlen die XMP-Begleitdateien, bricht Pass 1 jetzt sofort mit
  einer Erklärung ab statt nach der ganzen Messung mit „Errno 2“.
- Fehlermeldungen erscheinen in der eingestellten Sprache (vorher immer
  Deutsch).
- Keyframe-Sterne: In einer vorhandenen XMP (z. B. von Darktable) wird nur
  noch die Bewertung geändert. Vorher wurde sie bei ART/RawTherapee durch
  eine Minimaldatei ersetzt, und bei Darktable ohne XMP wurde gar nichts
  geschrieben.
- Ein Stern schreibt bei Darktable kein Belichtungsmodul mehr in den
  Verlauf.

### Intern
- **Eine Videostrecke statt zwei:** JPG-Ablauf und RAW Pass 2 hatten fast
  gleiche, getrennt gepflegte Schleifen. Laden, Ablegen, Stabilisieren und
  Bildausschnitt laufen jetzt in mehreren Threads voraus; EXIF-Daten werden
  zwischengespeichert statt je Bild neu aus der RAW gelesen.
- **Aufgeteilt:** Texte der Oberfläche (`purelapse_texte.py`) und
  Erscheinungsbild (`purelapse_design.py`) liegen in eigenen Dateien.
- **Prüfungen im Repository:** `tests/` mit rund 3000 Prüfungen und
  nachgebautem Qt, rawpy und Engines; GitHub prüft jeden Push mit Python
  3.10 und 3.12 (`.github/workflows/pruefung.yml`).
- Lauffähig ab Python 3.9; unnötige Importe und Formatierungen entfernt.
- Verworfen nach Messung: JPEGs verkleinert zu dekodieren (schneller, aber
  um bis zu 0,08 EV verfälscht) und eine Lanczos-Abbildung für die
  Kamerafahrt (zehnmal langsamer, Schärfe schwankte um 15 %).

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
- AppImage fuer Linux

### Bekannte Einschraenkungen
- Darktable: Weißabgleich und Entrauschen gibt es in den
  Schnelleinstellungen nur für ART und RawTherapee (seit 2.42).
