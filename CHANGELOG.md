# Changelog

Versionsnummern folgen [Semantic Versioning](https://semver.org/lang/de/).
Das Anhaengsel `-beta` kennzeichnet oeffentliche Testversionen.

## [Unveröffentlicht]

### Webseite
- Markenhinweis zu Lightroom in der Fußzeile der Webseite und in den READMEs.

### Geändert
- **16-Bit-Zwischenbilder sitzen jetzt beim Video** statt unter „Engine und Leistung“ – dort, wo man das Rendern einstellt. Darunter steht, wofür der Schalter gut ist: in der Regel nicht nötig, hilfreich bei Stufen in feinen Verläufen wie einem klaren Himmel, vor allem mit HEVC 10 Bit oder ProRes. Ist er an, steht der Hinweis in Warnfarbe mit dem Platzbedarf der Serie (aus der Bildgröße des ersten RAW), und die Zusammenfassung über den Knöpfen nennt „16-Bit-Zwischenbilder“ – damit er nicht versehentlich für jede Serie an bleibt. Bei JPG-Serien ist er ausgeblendet.
- **Icon in Spitzenqualität neu gerechnet:** gleiche Farben und Gestaltung, aber exakt aus der Geometrie (16-fach überabgetastet) statt nachgezeichnet. Keine Säume mehr – die Horizontlinie hatte oben und unten eine halb deckende Zeile, die Kanten von Punkten und Ecken nur wenige Abstufungen. Die Linie liegt jetzt in jeder Größe auf ganzen Bildpunkten; bis 24 px haben die Punkte mindestens 1,5 Bildpunkte Durchmesser, damit der Bogen in der Taskleiste nicht zu Grau verschwimmt. Durchsichtige Pixel tragen die Randfarbe statt Schwarz (kein dunkler Rand beim Skalieren).
- Windows: Die `.exe` bekommt ein eigenes `.ico` mit allen Größen von 16 bis 256 px.

### Intern
- Neue Prüfreihe `test_tiff16_schalter.py`; der nachgebaute rawpy kennt jetzt `sizes`.
- `grafik/icon_bauen.py` erzeugt alle Icons (Webseite, Favicon, AppImage, Windows-`.ico`, SVG-Vorlage, dazu 512 und 1024 px in `dist/`).
- `hochladen.sh "Nachricht"`: lässt alle Prüfungen laufen und lädt nur hoch, wenn sie grün sind; bricht bei Dateien über 50 MB und bei Bild-XMPs außerhalb von `tests/daten` ab. Legt von Claude nach `dist/` gelegte Ablaufdateien an ihren Platz. Sagt am Ende, wie es weitergeht: Prüfung auf GitHub, Webseite – und wenn die Versionsnummer noch kein Release hat, Schritt für Schritt das Veröffentlichen (AppImage bauen, Release mit vorausgefülltem Tag und Titel im Browser oder mit `gh` im Terminal).
- `.gitignore`: Bilder, Videos und RAW-Dateien im Hauptordner sowie `.exe` werden nie hochgeladen.

## [2.46.0-beta] – 2026-11-26

Purelapse läuft jetzt auch unter **Windows** – als einzelne `.exe`, ohne Installation. Dazu kommt **Lightroom Classic** als vierte Engine (über die XMP-Dateien), und unter Linux werden Engines aus **Flatpak** erkannt. darktable 5.x wird vollständig unterstützt.

### Windows
- **Purelapse für Windows 10/11 (64 Bit):** eine einzelne Datei `Purelapse-2.46.0-beta-windows-x64.exe` mit Python, Qt, OpenCV, rawpy und FFmpeg. Engines (ART, RawTherapee, darktable) werden in den üblichen Installationsordnern gefunden; Lightroom Classic läuft über die XMP-Dateien. Getestet mit RawTherapee: Ablauf und Bedienung wie unter Linux.
- Beim ersten Start meldet Windows evtl. „Der Computer wurde durch Windows geschützt“ – die Datei ist nicht signiert. Weiter über *Weitere Informationen → Trotzdem ausführen*.
- Gebaut wird die `.exe` auf GitHub (Ablauf *Windows-Paket*) und beim Veröffentlichen automatisch an das Release gehängt.
- **Videos tragen ihren Farbraum jetzt sicher:** Neuere FFmpeg-Fassungen (ab 8, unter Windows häufig) ließen Primärvalenzen und Kennlinie aus dem Video weg, obwohl Purelapse sie angab – Player mussten raten, Farben konnten leicht verschoben wirken. Die Angaben (BT.709) stehen jetzt zusätzlich an jedem Bild (`setparams`), FFmpeg übernimmt sie von dort.
- **Abbrechen beendet die Engine unter Windows vollständig:** Ein Programm, das selbst weitere Prozesse startet (etwa über eine `.cmd`- oder `.bat`-Hülle), lief nach dem Abbruch weiter. Purelapse beendet dort jetzt den ganzen Prozessbaum (`taskkill /T`) – in der echten Vorschau, bei Pass 2 und bei darktable-cli.
- **Prüfungen auch unter Windows grün:** Sechs Prüfreihen waren unter Windows bisher rot – fast alle wegen Unix-Annahmen in den Prüfungen selbst (Dateirechte 0600, Heimverzeichnis, Pfadtrenner). Seit 2.46 macht ein Fehlschlag unter Windows den Push rot.

### Neu
- **Lightroom Classic (XMP) als Engine.** Lightroom hat keine Kommandozeile; Purelapse arbeitet deshalb mit den XMP-Begleitdateien (`BILD.xmp`, so wie Lightroom sie nennt):
  1. In Lightroom alle Bilder der Serie auswählen → *Metadaten in Datei speichern* (Strg+S). Keyframes mit 5 Sternen markieren – in Lightroom oder in Purelapses Bildleiste.
  2. **Pass 1** misst die Helligkeit aus den RAWs und schreibt den Ausgleich in `crs:Exposure2012`.
  3. **Pass 2, erster Start:** überblendet die Keyframes in die Bilder dazwischen – alle Zahlenregler (Belichtung, Kontrast, Lichter, Tiefen, Weiß, Schwarz, Temperatur, Tönung, Dynamik, Klarheit, Dunst …) und Gradationskurven mit gleich vielen Punkten. Unterscheiden sich die Temperaturen, wird der Weißabgleich auf „Benutzerdefiniert“ gestellt. Masken, Profile und andere Auswahlwerte kommen vom näheren Keyframe (und stehen im Protokoll). Danach sagt Purelapse, was in Lightroom zu tun ist: *Metadaten aus Dateien lesen*, dann als JPG oder TIFF 16 Bit nach `Purelapse/Lightroom_Export` exportieren.
  4. **Pass 2, zweiter Start:** findet den vollständigen Export, misst das Restflackern der exportierten Bilder und gleicht es beim Videobau als Helligkeitsfaktor aus (höchstens 0,5 EV je Bild) – dann das Video mit allen Optionen. Ohne Video landen die abgeglichenen Bilder in `Purelapse/Deflickered_JPG`.
  - Ist der Export älter als eine XMP (Keyframe danach geändert), beginnt Pass 2 wieder mit Schritt 1. Fehlen einzelne Bilder im Export, nennt Purelapse sie, ohne etwas umzuschreiben.
  - Geschrieben werden nur die Entwicklungseinstellungen; Bewertung, Stichwörter und alles andere in der XMP bleiben, wie sie sind. Purelapse schreibt nur in XMP-Dateien, die Lightroom mit Einstellungen angelegt hat – eine selbst erzeugte würde beim Einlesen alles aus dem Katalog (Zuschnitt, Profil, Objektivkorrektur) auf Grundwerte setzen.
  - DNG wird abgelehnt: Lightroom speichert deren Einstellungen in der DNG-Datei selbst.
  - Warnung, wenn ein Keyframe auf automatischem Weißabgleich steht (würde je Bild neu berechnet und flackern).
  - Schnelleinstellungen für Lightroom-Keyframes: Farbtemperatur, Kontrast, Lichter, Tiefen, Dynamik, Sättigung, Schärfe, Rauschreduzierung. Vorschau: aus dem Export, solange der noch fehlt aus den eingebetteten Vorschaubildern.
  - Erkennung: Liegen Lightroom-XMP im Ordner, stellt Purelapse beim Einlesen auf Lightroom um. darktable-, Lightroom- und Purelapses eigene Sterne-XMP werden jetzt am Inhalt unterschieden.
- **Engines als Flatpak:** RawTherapee (`com.rawtherapee.RawTherapee`), ART (`us.pixls.art.ART`) und darktable (`org.darktable.Darktable`) aus Flathub werden erkannt – systemweit (`/var/lib/flatpak`) und für den Nutzer (`~/.local/share/flatpak`). Gespeichert wird der Ersatzpfad `flatpak:<App-ID>`; Purelapse startet damit `flatpak run --command=rawtherapee-cli` (bzw. `ART-cli`, `darktable-cli`). Weil die Engine in ihrer Sandbox läuft, gibt jeder Aufruf mit `--filesystem` genau die Ordner frei, die er braucht – Bilder, Ausgabe, Arbeits- und Konfigurationsordner, auch unter `/tmp` (das ART-Flatpak sieht `/tmp` sonst gar nicht). Die Zahl der Rechenkerne geht über `--env` mit. Systemordner (`/usr`, `/etc` …) werden nie freigegeben.
  - Einstellungen: Ist die Engine als Flatpak installiert, fragt „…“ beim Programmpfad zuerst, ob das Flatpak verwendet werden soll. Fehlt ein eingetragenes Programm (z. B. nach dem Umstieg auf Flatpak), sucht Purelapse neu.
  - Die Engine-Anzeige oben nennt „(Flatpak)“.
- **darktable 5 (getestet gegen den Quelltext von 5.6.2):** Neuere Modulversionen werden gelesen, geschrieben und überblendet – Belichtung 7 (neu: Lichterschutz `compensate_hilite_pres`), Weißabgleich 4 (neu: `preset`), Entrauschen (Profil) 12, Dunstentfernung 3.

- **Windows-Paket:** Ein neuer Ablauf bei GitHub (*Actions → Windows-Paket*) baut Purelapse auf einem Windows-Rechner von GitHub als einzelne `.exe` und startet sie zur Probe einmal. Bei einem Release wird sie automatisch angehängt.
- **Prüfungen auch unter Windows:** Bei jedem Push laufen alle Prüfungen zusätzlich auf Windows. Solange die Unterstützung im Aufbau ist, macht ein Fehlschlag dort den Push nicht rot.

### Geändert
- **Engines finden:** Unter Windows sucht Purelapse `ART-cli.exe`, `rawtherapee-cli.exe` und `darktable-cli.exe` nicht nur im Suchpfad, sondern auch in den üblichen Installationsordnern (`Program Files`, `%LOCALAPPDATA%\Programs`) – bei RawTherapee die neueste Version zuerst (5.10 vor 5.9).
- **Lange Befehlszeilen:** Windows erlaubt höchstens 32 767 Zeichen je Aufruf. Bei 900 Bildern mit langen Pfaden käme ART/RawTherapee darüber und startete gar nicht. Purelapse teilt die Bildliste dort auf mehrere Durchgänge nacheinander; unter Linux bleibt es bei einem Aufruf.
- **Kein Konsolenfenster:** Engines und FFmpeg starten unter Windows ohne eigenes Fenster – sonst blitzte bei jedem Aufruf eines auf.
- **VAAPI** ist unter Windows in der Codec-Liste gesperrt; die Liste bleibt vollständig, damit gespeicherte Einstellungen ihren Codec behalten.
- `Purelapse --version` nennt die Version und beendet sich – für die Startprobe beim Bauen.

### Behoben
- **Absturz beim Beenden (Speicherzugriffsfehler):** Wurde das Fenster geschlossen, während die Bildleiste noch Vorschaubilder las, wartete Purelapse nur eine Sekunde. Der Lader hatte aber alle Bilder schon eingereiht und las weiter, während Python schon aufräumte. Jetzt werden die noch nicht begonnenen Bilder gestrichen, und Purelapse wartet, bis die laufenden fertig sind.
- **darktable 5: Entflackern wirkungslos bzw. Einstellungen verloren.** Purelapse kannte nur die Belichtung in Version 6. In einem XMP aus darktable 5 (Version 7) konnte es den Wert nicht lesen und schrieb das Modul mit Grundwerten neu – Schwarzwert, Belichtungsausgleich und Lichterschutz des Nutzers gingen verloren, und die Belichtung der Keyframes floss nicht in die Bilder dazwischen. Jetzt bleibt das Modul in seiner Version, nur der Belichtungswert ändert sich. Neu angelegte Einträge bleiben Version 6; darktable 5 stuft sie beim Laden selbst hoch.
- **darktable 5: Weißabgleich sprang zwischen Keyframes.** Version 4 des Weißabgleichs war unbekannt; er schaltete deshalb in der Mitte hart um, statt weich überzublenden.
- **Keyframes aus darktable 4 und 5 gemischt:** Haben zwei Keyframes dasselbe Modul in verschiedenen Versionen, stuft Purelapse die ältere so hoch, wie darktable es beim Laden täte, und blendet weich über (vorher harter Wechsel „Modulversion“).
- **Jedes Bild doppelt auf Windows (und macOS):** Purelapse suchte `*.nef` und `*.NEF` getrennt. Unter Linux sind das verschiedene Dateien; Systeme, die Groß- und Kleinschreibung nicht unterscheiden, hätten für beide Muster dieselben Dateien geliefert. Die Suche führt jetzt jede Datei nur einmal.

### Intern
- Neue Prüfreihe `test_lightroom.py`: Begleitdatei und Erkennung, Lesen/Schreiben (Bewertung, Stichwörter, Kürzel bleiben), Überblenden von Zahlen, Weißabgleich, Kurven und Masken, Prüfsummen bleiben ungemischt, Schnelleinstellungen, und ein ganzer Ablauf: Pass 1 → Pass 2 Schritt 1 → nachgebauter Export mit Restflackern → Pass 2 Schritt 2 mit Video (Feinabgleich halbiert das Flackern mindestens), veralteter Export, fehlendes Bild, fehlende XMP.
- GitHub-Abläufe auf die Node-24-Fassungen umgestellt (`checkout@v5`, `setup-python@v6`, `upload-artifact@v6`).
- Pass 2: der Videobau ist als `_pass2_video()` herausgelöst und wird von RAW-Pass 2 und Lightroom gemeinsam genutzt.
- Neue Prüfreihe `test_dt5.py`: Belichtung 6/7 lesen und schreiben (Version und Nutzerfelder bleiben), Layouts der neuen Versionen, Weißabgleich 4 und gemischt 3+4 weich, Belichtung 6+7, Hochstufen der Dunstentfernung.
- Neue Prüfreihe `test_flatpak.py`: Erkennen in nachgebauten Flatpak-Ordnern, Aufruf mit `--command`, Ordnerfreigaben (ohne Doppelte, ohne Systemordner), Umgebungsvariablen.
- Modul-Layouts für darktable liegen jetzt je Version vor (`DT_LAYOUT_VERSIONEN`); Hochstufen nach `legacy_params()` von darktable (`DT_HOCHSTUFEN`).
- Neue Prüfreihe `test_windows.py` (läuft auf jedem System): Dateilisten ohne Doppelte, Engines in nachgebauten Installationsordnern, Teilen langer Befehlszeilen (keine Zeile zu lang, kein Bild verloren oder doppelt), Encoder je System, jeder Programmaufruf ohne Konsolenfenster.
- Prüfstand: Die nachgebauten Engines werden unter Windows über eine `.cmd`-Datei aufgerufen; Prüfungen, die `pgrep` oder Schreibschutz für Ordner brauchen, entfallen dort.

## [2.45.0-beta] – 2026-11-25

„Automatisch optimieren“ liefert jetzt ein gefälliges, fertiges Bild – mit wenigen Reglern, in allen drei Engines gleich. Dazu: Entflackern lässt sich abschalten, und bei 24-Stunden-Zeitraffern fällt die Nacht auf Wunsch aus dem Video.

**Hinweis:** Wer mit einer älteren Version einen Keyframe über die Schnelleinstellungen gespeichert hat, dessen Profil auf dem Weißabgleich der Kamera stand, hat dabei 6504 K als eigenen Weißabgleich gespeichert (siehe „Behoben“). Wurde das Bild dadurch orange oder blau: in der Engine für diesen Keyframe den Weißabgleich wieder auf „Kamera“ stellen – oder im Dialog eine passende Temperatur wählen.

### Neu
- **Grundschalter „Entflackern“ (Standard: an).** Ohne Haken baut Purelapse den Zeitraffer mit der Helligkeit, die die Kamera aufgenommen hat – Keyframes, Kamerafahrt, Stabilisierung, Telemetrie, Bewegungsunschärfe und Blenden wirken wie gewohnt.
  - JPG: kein Messen, kein Ausgleich.
  - RAW: Pass 1 heißt dann „Profile vorbereiten“ und misst nichts – jedes Bild bekommt sein vollständiges Profil mit Belichtung 0. Keyframes behalten, was an ihnen eingestellt ist; was ein früherer Pass 1 und die Nachkalibrierung beigesteuert hatten, wird herausgerechnet. Pass 2 entwickelt mit überblendeten Keyframes, ohne Nachkalibrierung, und kommt notfalls ohne Pass 1 aus.
  - Der Schalter wird je Ordner gemerkt. Pass 1 vermerkt, wie er lief (`Purelapse/purelapse_modus.json`): Der Schritt gilt nur als erledigt, wenn das zum Schalter passt, und ein Pass 2 mit Entflackern auf Profilen ohne bricht mit klarer Meldung ab, statt ein halb entflackertes Video zu liefern.
- **Nacht entfernen.** Für 24-Stunden-Zeitraffer: Bilder unterhalb einer einstellbaren Helligkeit kommen nicht ins Video.
  - Gemessen wird die Helligkeit der **Szene**: Bildhelligkeit verrechnet mit der Belichtung aus den EXIF-Daten (Zeit, Blende, ISO), in Blenden unter dem Tageslicht der Serie. So wird die Nacht auch erkannt, wenn die Kamera nachts länger belichtet hat und die Bilder kaum dunkler aussehen.
  - Im Diagramm stehen die Szenenhelligkeit und die Grenze als gestrichelte Linie, die sich mit der Maus verschieben lässt; die Nachtstrecken sind grau hinterlegt, ihre Kacheln in der Bildleiste abgeblendet. Unter dem Regler steht, wie viele Bilder wegfallen und wie lang das Video danach ist.
  - Damit es je Nacht genau einen Schnitt gibt, wird die Kurve vorher geglättet; kurze Ausreißer – ein Scheinwerfer in der Nacht, eine Wolke am Tag – gehen in ihrer Umgebung auf.
  - Mit Entflackern wird weiter die ganze Serie gemessen und entwickelt, damit der Verlauf in der Dämmerung stimmt; nur ins Video kommt die Nacht nicht. Ohne Entflackern wird die Nacht gar nicht erst entwickelt. Schnellvorschau, 5-Bilder-Vorschau und Rohfassung lassen sie ebenfalls aus.
  - Die Grenze wird je Ordner gemerkt.
- **Drei neue Schnelleinstellungen: „Lichter abdunkeln“, „Tiefen aufhellen“ und „Dynamik“.** Lichter und Tiefen wirken lokal: Ein heller Himmel bekommt wieder Zeichnung, ein dunkler Vordergrund öffnet sich, ohne dass der Kontrast im Kleinen verloren geht. Die Dynamik hebt blasse Farben stärker als satte und lässt Hauttöne und kräftige Farben nicht ins Grelle kippen. Jede Engine bekommt ihr eigenes Werkzeug:
  - ART: Tonwert-Equalizer (`[ToneEqualizer]`) und Dynamik in `[Saturation]`,
  - RawTherapee: `[Shadows & Highlights]` und `[Vibrance]`,
  - darktable: Modul „Schatten und Lichter“ (wird bei Bedarf angelegt, ohne eigene Wirkung, solange der Regler nicht bewegt ist) und die Dynamik der Farbbalance RGB.
  Die Werkzeuge packen verschieden stark zu; Purelapse rechnet die Reglerwerte je Engine so um, dass „Tiefen aufhellen 40“ überall ungefähr dasselbe bedeutet. Die Umrechnung stammt aus den Quelltexten der Programme.
- **Die Vorschau zeigt die neuen Regler sofort,** auch bevor die Engine ihr Bild geliefert hat. Die Näherung arbeitet wie die Engines mit einer kantenerhaltenden Maske – an harten Kanten (Zaunpfosten vor hellem Himmel) entstehen keine Höfe.

### Geändert
- **„Automatisch optimieren“ zielt auf ein gefälliges Ergebnis:** Erst werden die Lichter heruntergeholt und die Tiefen aufgehellt, dann bekommt der Mittelton mit etwas Kontrast wieder Biss, die Farbe kommt über die Dynamik statt über die Sättigung. Gemessen wird jeder Schritt an dem Bild, wie es nach den vorigen aussieht. Sicherungen für den Zeitraffer:
  - **Nachtszenen bleiben dunkel:** Ist der größte Teil des Bildes dunkel, hellt die Automatik die Tiefen nur wenig auf und nimmt den Kontrast zurück – ein Nachthimmel wird sonst grau und rauscht.
  - **Hohe ISO:** Ab ISO 1600 werden die Tiefen weniger aufgehellt, ab 3200 nur noch halb so stark.
  - Die Automatik rechnet einmal am Keyframe und schreibt feste Zahlen; zwischen den Keyframes wird überblendet. Nichts davon rechnet die Engine Bild für Bild neu – das würde flackern.
  - Der Weißabgleich bleibt wie bisher unberührt.
  Jede Entscheidung steht mit ihrer Messzahl im Tooltip des Hinweises.
- **darktable: Module, die nur in einem Keyframe stehen, werden weich überblendet.** Fehlte „Schatten und Lichter“ oder die Farbbalance RGB im Nachbar-Keyframe, schaltete das Modul bisher in der Mitte hart um – ein sichtbarer Sprung. Diese beiden Module lassen sich ohne Wirkung stellen; Purelapse blendet jetzt von dieser Nullstellung aus über. Die Warnung „nicht weich überblendbar“ entfällt dafür.

### Behoben
- **Echte Vorschau tieforange, Näherung normal – Weißabgleich der Kamera wurde überschrieben:** Steht im Profil der Weißabgleich der Kamera, ist die Temperatur in der Datei nur ein Platzhalter – RawTherapee schreibt dort immer 6504 K. Die Schnelleinstellungen hielten diesen Wert für eingestellt, weil er von 5500 K abweicht, hakten „Farbtemperatur“ an und schrieben ihn als eigenen Weißabgleich ins Profil. Ein Kunstlichtbild (rund 3000 K) wurde dadurch wie Tageslicht behandelt und tieforange, während die Näherung den Kamera-Weißabgleich zeigte. Jetzt ist der Weißabgleich nur angehakt, wenn das Profil wirklich einen eigenen hat. Ausgangswert des Reglers ist die Temperatur, die die Kamera eingestellt hatte: berechnet aus den Kanalfaktoren und der Farbmatrix im RAW, so wie die Engines es tun (Gegenprobe mit der Matrix der Nikon D750: Tageslicht 5500 K, Glühlampe 2900 K).
- **„Automatisch optimieren“ maß am falschen Bild:** Die Vorschläge wurden an der Näherung aus dem RAW gemessen. Die kennt weder die Belichtung aus dem Deflicker noch Tonkurve und Farben der Engine – im echten Bild gerieten die Vorschläge deshalb oft zu hell oder zu dunkel. Mit eingeschalteter echter Vorschau lässt die Automatik die Engine jetzt zuerst das Ausgangsbild entwickeln (ihre Regler auf neutral, Weißabgleich und Lichter-Rekonstruktion wie eingestellt) und misst daran. Ohne Engine bleibt es bei der Näherung. Die erste Zeile der Begründung nennt, woran gemessen wurde.
- **−, + und „neutral“ blieben grau:** Setzte „Automatisch optimieren“, „Von anderem Keyframe übernehmen“ oder „Zurücksetzen“ einen Regler, wurde zwar das Häkchen gesetzt und der Schieber frei, die drei Knöpfe daneben blieben aber gesperrt. Jetzt folgen Schieber und Knöpfe immer dem Häkchen.
- **„Automatisch optimieren“ hing vom vorigen Stand ab:** Regler, die die Automatik beurteilt, aber nicht verstellt – etwa die Sättigung neben der Dynamik –, blieben auf dem Wert stehen, den man vorher von Hand eingestellt hatte. Eine Sättigung von +100 blieb so neben dem Vorschlag stehen. Jetzt stellt die Automatik solche Regler auf neutral und sagt das im Hinweis; zweimal optimieren ergibt dasselbe. Weißabgleich und Grünabgleich bleiben wie bisher unberührt.

### Intern
- Neue Prüfreihe `test_nacht_entflackern.py`: Szenenhelligkeit mit fester Belichtung und mit Belichtungsautomatik, Nachtmaske samt Ausreißern; JPG ohne Entflackern (Flackern bleibt) und mit Nacht (fehlt im Video, Rest entflackert); RAW: Pass 1 ohne Entflackern (Keyframe behält seine eigene Belichtung, zweiter Lauf ändert nichts mehr), Pass 2 mit Entflackern auf Profilen ohne bricht ab, Pass 2 ohne entwickelt die Nacht nicht und läuft auch ohne Pass 1; Oberfläche: Schalter je Ordner, Schrittleiste, abgeblendete Kacheln, Grenzlinie und Regler gekoppelt.
- `test_echt.py`: Kamera-Weißabgleich bleibt unangehakt, Ausgangswert aus dem RAW; Temperatur aus Kanalfaktoren und Farbmatrix (Tageslicht, Glühlampe, Rückrechnung); Automatik misst am Bild der Engine – bei viel dunklerem Engine-Bild fällt die Helligkeit höher aus als an der Näherung.
- `test_echt.py`: Automatik im Dialog – Knöpfe passend zum Häkchen, von Hand verstellte Regler auf neutral, zweimal optimieren ergibt dasselbe, Zurücksetzen. Mit dem alten Stand schlagen 9 Prüfungen fehl.
- Neue Prüfreihe `test_tiefen_lichter.py`: Schlüssel und Umrechnung je Engine samt Rücklesen, die Nullstellung des neu angelegten darktable-Moduls Byte für Byte, weiches Überblenden eines Moduls, das nur in einem Keyframe steht, Richtung und Hoffreiheit der Näherung, Dynamik (blasse Farben gewinnen mehr als satte, Grau bleibt grau) und die Automatik (Nacht, hohe ISO, Grenzen, gesperrte Regler).
- `test_auto.py`, `test_keyframe.py`, `test_dt_b5.py`, `test_ablauf.py` auf die elf Regler umgestellt.
- Die nachgebauten Engines schreiben die neuen Sektionen wie die echten (ART 1.26, RawTherapee 5.10). Der Prüfstand verwirft beim Start Basisprofile früherer Läufe, damit nicht gegen einen alten Stand der nachgebauten Engine geprüft wird.

## [2.44.1-beta] – 2026-11-25

Korrektur zu 2.44.0: Die Entflackerung bleibt auch bei viel Ausgebranntem stabil – etwa bei Kerzenlicht oder Lampen im Bild, zumal mit Kamerafahrt.

### Behoben
- **Nachkalibrierung lief bei viel Ausgebranntem weg – Video flackerte trotz Entflackerung:** Brennt in einer Serie fast überall irgendwann etwas aus (Kerzen, Lampen, helle Flächen; bei einer Kamerafahrt wandern sie zudem durchs Bild), entschied bisher jedes Bild selbst, welche Bereiche es misst. Wurde ein Bild heller gemacht, brannte mehr aus, fiel aus der Messung heraus – und das Bild maß sich dunkler. Die Nachkalibrierung machte es daraufhin noch heller, bis zum Anschlag von ±0,5 EV. Gesehen in einem Kerzenlicht-Zeitraffer mit Slider: einzelne Bilder sprangen um fast eine Blende, mit einem oder zwei Keyframes gleichermaßen. Jetzt vergleicht die Messung in diesem Fall jeden Bereich mit demselben Bereich der Nachbarbilder und nimmt je Bild den Median dieser Verhältnisse. Ein heller gemachtes Bild misst sich damit heller, gleich welche Bereiche dabei ausbrennen.
- **Alte Nachkalibrierung wurde weitergetragen:** Die Korrekturen der Nachkalibrierung (`purelapse_calib.json`) blieben auch nach einem neuen Pass 1 stehen und wurden in jeden weiteren Lauf eingerechnet – fehlerhafte Werte wurde man so nicht mehr los. Pass 1 verwirft sie jetzt, denn sie gehören zur vorigen Messung, und meldet das im Protokoll.
- **Keyframes kurz doppelt gezählt:** Beim Neu-Einlesen der Bildleiste konnten Bilder des vorigen Ladelaufs noch nachträglich ankommen und wurden vor die neuen gehängt – aus 2 Keyframes wurden kurz 4, und Bildleiste und Diagramm passten nicht mehr zueinander. Jetzt nimmt die Bildleiste nur noch, was vom aktuellen Ladelauf stammt.
- **„Ordner öffnen“ nach einem Ordnerwechsel:** Der Knopf öffnete weiter den Ausgabeordner des letzten Laufs – auch wenn inzwischen ein anderer Bilderordner geladen war. Jetzt gehört der zuletzt erzeugte Ausgabeordner zum Bilderordner und wird beim Wechsel vergessen. Ohne Lauf öffnet der Knopf den Ordner `Purelapse` im Bilderordner, solange es ihn noch nicht gibt den Bilderordner selbst.

### Intern
- Neue Prüfreihe `test_messung_lichter.py`: Serie mit Kamerafahrt, in der kaum ein Bereich in allen Bildern frei bleibt – heller und dunkler gemachte Bilder müssen sich in die richtige Richtung messen, die Nachkalibrierung darf nicht weglaufen. Mit dem alten Stand schlagen 8 Prüfungen fehl.
- `test_kf_engine.py`: Nachzügler eines abgelösten Laders verändern weder Bildleiste noch Zähler noch Keyframe-Linien.
- `test_ordner.py`: Pass 1 verwirft eine vorhandene Nachkalibrierung; „Ordner öffnen“ nach einem Lauf, nach dem Wechsel in einen anderen Ordner und zurück.

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
