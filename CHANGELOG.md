# Changelog

Versionsnummern folgen [Semantic Versioning](https://semver.org/lang/de/).
Das Anhaengsel `-beta` kennzeichnet oeffentliche Testversionen.

## [2.44.0-beta] – 2026-11-22

Ein ruhigeres, professionelleres Erscheinungsbild nach dem Vorbild von DaVinci Resolve – und die Ordnerwahl zeigt jetzt alle Bilder eines Ordners als scrollbares Raster.

### Neu
- **Ordnerwahl: alle Bilder als scrollbares Raster.** Statt sechs ausgewählter Vorschauen zeigt der Dialog jetzt jedes Bild des Ordners. Geladen werden nur die Kacheln, die gerade zu sehen sind (plus eine Zeile Vorlauf) – beim Scrollen kommen die nächsten nach, beim Wechsel des Ordners bricht das Laden sofort ab. Das Durchklicken bleibt so bei 50 wie bei 5000 Bildern flüssig. Ein Tooltip nennt Nummer und Dateinamen.

### Geändert
- **Ruhigeres dunkles Erscheinungsbild nach dem Vorbild von DaVinci Resolve:** neutrale Grautöne ohne Blaustich, Trennlinien dunkler als die Flächen (Bereiche wirken eingelassen statt umrandet), Eingabefelder dunkler als ihre Umgebung, kleinere Eckenradien und etwas kompaktere Abstände. Beschriftungen sind gedämpft, Weiß bleibt dem Wichtigen vorbehalten.
- Schrittleiste: Der aktive Schritt wird nicht mehr ganz eingefärbt, sondern heller hinterlegt mit einer farbigen Unterkante; die übrigen Schritte zeigen ihre Farbe nur als schmale Linie. Die Schrittfarben sind etwas gedämpft.
- Das helle Farbschema behält seine Farben und übernimmt die kleineren Radien und Abstände.

### Intern
- `test_ordnerwahl.py` neu gefasst: sichtbarer Bereich des Rasters (auch bei 5000 Bildern gleich viele Kacheln), Wunschliste des Laders samt Ersetzen während des Ladens, Nachladen beim Scrollen, kein Bild aus dem vorigen Ordner.

## [2.43.1-beta] – 2026-11-22

Korrektur zu 2.43.0: Keyframes stimmen nach einem Wechsel der Engine wieder überall überein.

### Behoben
- **Keyframes nach einem Engine-Wechsel:** Ob ein Bild Keyframe ist, hängt von der Engine ab – bei RawTherapee und ART zählt auch der Eintrag im Profil, bei darktable nur der Stern in der `.xmp`. Nach dem Umschalten rechneten Zähler und Entwicklung schon mit der neuen Engine, die Sterne in der Bildleiste zeigten noch den alten Stand. So stand oben „8 bearbeitete Keyframes“, der Filter zeigte 4, und vier Bilder wurden als Keyframe entwickelt, ohne dass man es sah. Jetzt liest die Bildleiste ihre Sterne beim Engine-Wechsel neu, meldet Abweichungen im Protokoll und schreibt dabei nichts in die Dateien.
- Vorschau mit der Engine: Nach einem Abbruch fasst das Aufräumen des Arbeitsordners kurz nach, falls die Engine noch an ihren Dateien hängt.

### Intern
- Neue Prüfreihe `test_kf_engine.py`: Bildleiste, Filter, Zähler und Dateien stimmen nach dem Wechsel zwischen darktable und RawTherapee überein; das Abgleichen schreibt keine Datei.
- Prüfstand: Pakete, die mit `pip install --user` unter `~/.local` liegen (etwa OpenCV), finden jetzt auch die nachgebauten Engines. Vorher scheiterten auf solchen Rechnern acht Prüfreihen, obwohl das Programm selbst in Ordnung war.
- `tests/alle.py` wertet jetzt auch Prüfreihen als fehlgeschlagen, die ihre Fehler nur in der letzten Zeile melden („… 2 fehlgeschlagen“). Dabei fiel eine veraltete Erwartung in `test_schnell.py` auf: Das Video der Schnellvorschau liegt jetzt richtig im Ordner `Purelapse`.
- Prüfstand: Die Codec-Prüfung gibt jetzt selbst vor, dass NVIDIA fehlt – auf Rechnern mit NVIDIA-Grafikkarte schlug sie sonst fehl, obwohl der Codec zu Recht wählbar blieb. Zwischendateien legt der Prüfstand in einen eigenen Ordner statt ins allgemeine `/tmp`, damit ein gleichzeitig offenes Purelapse die Zählung nicht stört. Ebenso zählt die Prüfung „keine Engine läuft nach dem Abbruch weiter“ nur noch die nachgebaute Engine des Prüfstands, nicht ein echtes RawTherapee, das nebenher arbeitet.

## [2.43.0-beta] – 2026-11-22

Ordnerwahl mit Vorschau der Bilder, und alles, was Purelapse erzeugt, liegt
jetzt geordnet im Unterordner „Purelapse“ statt lose zwischen den Bildern.

### Neu
- **Ordnerwahl mit Vorschau:** Der Dialog „Zeitraffer-Ordner wählen“ zeigt
  rechts, was im markierten Ordner liegt: Anzahl und Art der Bilder, erstes
  und letztes Bild und sechs über die Serie verteilte Vorschauen. Bei RAW
  werden die eingebetteten Vorschaubilder der Kamera gelesen, im
  Hintergrund – das Durchklicken bleibt flüssig. Unter 50 Bildern steht ein
  Hinweis. Der Dialog ist größer als bisher, etwa 70 % von Breite und Höhe
  des Hauptfensters.

### Geändert
- **Eigener Ordner „Purelapse“ im Bilderordner:** Videos, entwickelte Bilder
  (`Deflickered_JPG`), Messwerte (`purelapse_deflicker.json`,
  `purelapse_calib.json`, `purelapse_result.json`) und die Protokolle des
  Diagnose-Modus liegen nicht mehr lose zwischen den Bildern, sondern im
  Unterordner `Purelapse`. Neben den Bildern bleiben nur die Begleitdateien
  der Engine (`.arp`, `.pp3`, `.xmp`), weil ART, RawTherapee und darktable
  sie dort erwarten.
- **Ältere Ordner werden umgeräumt:** Beim Öffnen eines Ordners – und beim
  Start eines Auftrags aus der Warteschlange – verschiebt Purelapse die
  losen Dateien älterer Versionen einmalig in den Ordner `Purelapse` und
  meldet das im Protokoll. Fremde Dateien bleiben unberührt; liegt im
  Ordner `Purelapse` schon eine gleichnamige Datei, wird nichts
  überschrieben.
- Speicherort „1. Quell-Ordner (Bilder)“ heißt jetzt „1. Purelapse-Ordner im
  Bilderordner (empfohlen)“. Übergeordneter, Programm- und eigener Ordner bleiben
  wählbar. „Ordner öffnen“ zeigt auf den Purelapse-Ordner.
- „Zurücksetzen“ sucht an der neuen Stelle und räumt den Ordner `Purelapse`
  weg, wenn er danach leer ist.

### Intern
- Neue Prüfreihe `test_ordnerwahl.py` (Bilder finden, Auswahl über die
  Serie, Vorschaubilder für RAW und JPG, Lader im Hintergrund).
- Neue Prüfreihe `test_ordner.py`: Ablage bei RAW und JPG, mit und ohne
  Diagnose-Modus, eigener Speicherort, Umräumen alter Ordner (auch ohne
  Überschreiben), Startdialog und Zurücksetzen.

### Webseite
- Technik-Bereich: neuer Abschnitt zur Ablage im Ordner `Purelapse`.
- **Mastodon:** Link auf [@purelapse@mastodon.social](https://mastodon.social/@purelapse)
  in der Fußzeile, mit `rel="me"` – damit bestätigt Mastodon die Webseite
  im Profil mit einem grünen Häkchen.

## [2.42.2-beta] – 2026-11-21

Englische Oberfläche ohne deutsche Reste und ein abgedunkelter Hintergrund,
solange ein Dialog im Vordergrund steht.

### Neu
- **Hintergrund abgedunkelt bei Dialogen:** Solange ein Fenster im
  Vordergrund auf eine Eingabe wartet – Startdialog, Einstellungen,
  Keyframe-Dialog, Rückfragen, Meldungen, Dateiauswahl –, liegt über dem
  Hauptfenster ein Schleier, der sanft einblendet. Der Blick geht zum
  Dialog, und man sieht sofort, dass das Fenster dahinter gerade gesperrt
  ist. Im hellen Farbschema ist der Schleier leichter. Nicht modale
  Fenster wie die Warteschlange dunkeln nicht ab.

### Behoben
- **Englische Oberfläche ohne deutsche Reste:** Bei Sprache Englisch kamen
  noch etliche Texte auf Deutsch:
  - die Statuszeile während der Arbeit („Analysiere RAWs“, „Entwicklung“,
    „Nachkalibrierung“, „Schreibe Sidecar …“, „Suche defekte Pixel“) und
    der Zähler im Ladeschirm („5 von 56“),
  - alle Fertig-Meldungen („Fertiges Video“, „Pass 1 abgeschlossen …“,
    „Rohfassung fertig“, „Entflackerte JPGs liegen in“) – und damit auch
    der Text der **Telegram-Nachricht**,
  - die Fehlertexte der Telegram-Anbindung, Dialogtitel der Dateiauswahl,
    einige Warnungen und Protokollzeilen,
  - die Begründungen der automatischen Schnelleinstellungen und die
    Befunde der Profilprüfung,
  - die Tooltips von Erstes/Letztes Bild, Startbild/Endbild, Basisprofil,
    Diagnose-Modus, 16-Bit-Zwischenbildern und Schnellvorschau, die
    Auswahlliste Motion Blur sowie Hilfetext und Platzhalter für Telegram.
- **Tooltips zeigten „\n“:** Bei acht Tooltips (u. a. Engine, Hotpixel,
  Vorschau, Warteschlange) stand statt eines Zeilenumbruchs ein sichtbares
  „\n“ – in beiden Sprachen.

### Intern
- Neue Prüfreihen `test_englisch_oberflaeche.py` (Statuszeile,
  Fertig-Meldungen, Telegram, Tooltips und Listen in Englisch) und
  `test_abdunkeln.py` (Schleier bei modalen Fenstern, verschachtelte
  Dialoge, Ladeschirm, Dateidialoge, Farbschema).

### Webseite
- **Weltkarte „Purelapse in aller Welt“:** Besucher setzen einen Pin mit
  Reaktion und Engine, der Ort wird schon im Browser auf etwa 50 km
  gerundet. Gespeichert wird über einen Cloudflare Worker mit D1-Datenbank
  (Hoheitsgebiet EU); ein Pin je Besucher und Tag, Bot-Schutz mit Cloudflare
  Turnstile, der erst beim Setzen eines Pins lädt. Keine IP-Adressen, keine
  fremden Kartenkacheln – die Karte ist eine eigene Punktgrafik. Quelltext
  und Prüfung in `karte/`.
- **Auffindbarkeit in Suchmaschinen:** `robots.txt` und `sitemap.xml`
  (mit Sprachzuordnung Deutsch/Englisch), strukturierte Daten
  (`SoftwareApplication`) auf der Startseite. Die automatische
  Sprachweiterleitung der deutschen Seiten gilt nicht mehr für
  Suchmaschinen – bisher landete der Google-Crawler mit englischer
  Browsersprache immer auf der englischen Seite, die deutschen Seiten
  wurden dadurch womöglich nicht erfasst.
- **Neue Projektadresse:** Purelapse liegt jetzt in der GitHub-Organisation
  `purelapse` (github.com/purelapse/purelapse). Alle Links auf der Webseite
  und in den READMEs zeigen dorthin; alte Links leitet GitHub weiter.
- **Neues Vergleichsvideo in 4K:** Die zweite Serie (Sonnenuntergang am
  Meer) ersetzt das bisherige Video. Links mit den Standardeinstellungen
  von darktable entwickelt, rechts nach Purelapse; die Trennlinie liegt auf
  dem Stromboli, wo die Sonne untergeht. 3840 × 2160, 50 fps, für das Netz
  neu kodiert (H.264, zwei Durchgänge).

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
