# -*- coding: utf-8 -*-
"""
Purelapse - Texte der Oberflaeche (Deutsch/Englisch)

Teil von Purelapse. Copyright (C) 2026 slvobng.
Lizenz: GNU General Public License v3 oder spaeter (siehe LICENSE).
"""


# ==========================================================================
#  ZWEISPRACHIGKEIT
# ==========================================================================
TRANSLATIONS = {
    # Gruppen (siehe _build_ui). Die Reihenfolge zeigt die Schrittleiste,
    # deshalb tragen die Gruppen keine Nummern mehr.
    "Zeitraffer-Ordner": "Timelapse folder",
    "Format": "Format",
    "Helligkeit und Deflicker": "Brightness and deflicker",
    "Entflackern": "Deflicker",
    "Nacht entfernen": "Remove night",
    "Zu dunkle Bilder auslassen": "Leave out frames that are too dark",
    "Dunkler als:": "Darker than:",
    "Engine und Leistung": "Engine and performance",
    "Video": "Video",
    "Bild und Effekte": "Image and effects",
    "Speicherort und Dateinamen": "Location and file names",
    "Aktionen": "Actions",
    "Keyframes": "Keyframes",
    "Darstellung": "Appearance",
    "Aufnahmeort für die Sonnenstand-Kurve (optional)": "Location for the sun elevation curve (optional)",
    " Einstellungen…": " Settings…",
    " Schließen": " Close",
    " Bilder neu einlesen": " Re-read images",
    " Vorschau (5 Bilder)": " Preview (5 frames)",
    " Zur Warteschlange": " Add to queue",
    " Warteschlange…": " Queue…",
    " Weitere": " More",
    "Jeder Auftrag merkt sich Ordner, Schritt und alle Einstellungen. "
    "Neue Aufträge legst du im Hauptfenster mit „Zur Warteschlange“ an.":
        "Each job remembers its folder, step and all settings. "
        "Add new jobs in the main window with “Add to queue”.",
    " Entfernen": " Remove",
    " Leeren": " Clear",
    " Stapel abarbeiten": " Run queue",
    # Beschriftungen
    "Kein Ordner gewählt.": "No folder selected.",
    "Lichtverlauf:": "Light progression:",
    "Weitere Kurven:": "More curves:",
    "Breitengrad:": "Latitude:",
    "Längengrad:": "Longitude:",
    "Zeitzone (UTC+):": "Time zone (UTC+):",
    "Deflicker-Stärke:": "Deflicker strength:",
    "Belichtung (EV):": "Exposure (EV):",
    "CPU-Kerne:": "CPU cores:",
    "ART-Programm:": "ART program:",
    "ART-Basisprofil:": "ART base profile:",
    "RawTherapee-Programm:": "RawTherapee program:",
    "RawTherapee-Basisprofil:": "RawTherapee base profile:",
    "Entwicklungs-Engine:": "Development engine:",
    "Nachkalibrierung:": "Recalibration:",
    "Noch nicht gestartet.": "Not started yet.",
    "Framerate (fps):": "Frame rate (fps):",
    "16:9-Auflösung:": "16:9 resolution:",
    "Video-Codec:": "Video codec:",
    "Parallele Prozesse:": "Parallel processes:",
    "★ nur Keyframes": "★ keyframes only",
    # Motion Blur (MainWindow.blur_options)
    "Aus (1 Bild)": "Off (1 frame)",
    "3 Bilder": "3 frames",
    "4 Bilder": "4 frames",
    "5 Bilder": "5 frames",
    "6 Bilder": "6 frames",
    "7 Bilder": "7 frames",
    "8 Bilder": "8 frames",
    "9 Bilder": "9 frames",
    "10 Bilder": "10 frames",
    "12 Bilder": "12 frames",
    "15 Bilder": "15 frames",
    "18 Bilder": "18 frames",
    "20 Bilder": "20 frames",
    "25 Bilder": "25 frames",
    "Keyframe einstellen…": "Edit keyframe…",
    "Automatisch": "Automatic",
    "1 (seriell)": "1 (serial)",
    "Render-Qualität:": "Render quality:",
    "Motion Blur:": "Motion blur:",
    "Ein-/Ausblenden:": "Fade in / out:",
    "Aus": "Off",
    "0,5 Sekunden": "0.5 seconds",
    "1 Sekunde": "1 second",
    "2 Sekunden": "2 seconds",
    "3 Sekunden": "3 seconds",
    "Standard (Mitte)": "Default (centred)",
    "Statisch (Festgelegter 16:9 Crop)": "Static (fixed 16:9 crop)",
    "Dynamisch (Start \u2192 Ende)": "Dynamic (start \u2192 end)",
    "Bildausschnitt:": "Framing:",
    "Zum ersten Bild": "Go to first frame",
    "Benachrichtigung (Telegram)": "Notification (Telegram)",
    "Nach jedem Lauf eine Nachricht schicken (fertig oder Fehler)":
        "Send a message after every run (done or error)",
    " Chat-ID ermitteln": " Find chat ID",
    "Chat-ID:": "Chat ID:",
    "123456789:ABC\u2026  (von @BotFather)": "123456789:ABC\u2026  (from @BotFather)",
    "wird mit \u201eChat-ID ermitteln\u201c eingetragen": "filled in by \u201cFind chat ID\u201d",
    ("So geht es: in Telegram @BotFather anschreiben, /newbot senden und "
     "einen Namen vergeben - er antwortet mit dem Bot-Token. Dann dem "
     "neuen Bot eine beliebige Nachricht schicken und hier "
     "\u201eChat-ID ermitteln\u201c druecken."):
        ("How it works: in Telegram, message @BotFather, send /newbot and "
         "choose a name - it replies with the bot token. Then send any "
         "message to your new bot and press \u201cFind chat ID\u201d here."),
    " Testnachricht senden": " Send test message",
    " \u26a1 Schnellvorschau": " \u26a1 Quick preview",
    "\u21e4 Startbild": "\u21e4 Start frame",
    "Endbild \u21e5": "End frame \u21e5",
    "Zum letzten Bild": "Go to last frame",
    " 16:9 Kamerafahrt / Crop \u2026": " 16:9 camera move / crop \u2026",
    "Geschätzte Dateigröße: -- MB": "Estimated file size: -- MB",
    "Speichern in:": "Save to:",
    "Wenn Datei existiert:": "If file exists:",
    "Bereit.": "Ready.",
    "Sprache:": "Language:",
    "Design:": "Theme:",
    "Dunkel": "Dark",
    "Hell": "Light",
    "Sonnenstand": "Sun elevation",
    "GPS aus Bild": "GPS from image",
    # Schalter
    "Video erstellen": "Create video",
    "Optische Stabilisierung": "Optical stabilisation",
    "Denoise": "Denoise",
    "Rückwärts rendern": "Render in reverse",
    "Telemetrie-Overlay": "Telemetry overlay",
    "Astro-Clean (Satelliten entfernen)": "Astro clean (remove satellites)",
    "Tote / heiße Pixel entfernen": "Remove dead / hot pixels",
    "Weißabgleich": "White balance",
    "Belichtung (EXIF)": "Exposure (EXIF)",
    "Intervall": "Interval",
    "Clipping": "Clipping",
    "Restflackern": "Residual flicker",
    "Diagnose-Modus (Protokolldateien schreiben)": "Diagnostic mode (write log files)",
    "16-Bit-Zwischenbilder (TIFF) für höchste Qualität": "16-bit intermediate images (TIFF) for best quality",
    "JPG (Direkt-Workflow)": "JPG (direct workflow)",
    "NEF / RAW (RAW-Workflow)": "NEF / RAW (RAW workflow)",
    " Durchsuchen…": " Browse…",
    " Aktualisieren": " Refresh",
    " [+] Messbereich (ROI) festlegen": " [+] Set measuring area (ROI)",
    " [✔] Messbereich (ROI) ist AKTIV! (Klick = neu)": " [✔] Measuring area (ROI) ACTIVE! (click to redo)",
    " [✥] 16:9 Kamerafahrt / Crop": " [✥] 16:9 camera move / crop",
    " Zurücksetzen…": " Reset…",
    " Rohfassung": " Untouched",
    " Vergleich…": " Compare…",
    " Ordner öffnen": " Open folder",
    " Abbrechen": " Cancel",
    "Bitte Zeitraffer-Ordner wählen…": "Please select a timelapse folder…",
    "wird im Bilderordner gesucht": "searched for in the image folder",
    # Darktable-Hinweistext
    "Darktable braucht kein Basisprofil: Purelapse arbeitet mit den "
    "vorhandenen .xmp-Dateien. Es schreibt die Belichtung und überträgt "
    "die Module der Keyframes in die Bilder dazwischen.":
        "darktable doesn't need a base profile: Purelapse works with the "
        "existing .xmp files. It writes the exposure and carries the "
        "keyframes' modules into the frames in between.",
    # Lightroom-Hinweistext
    'Lightroom Classic hat keine Kommandozeile – Purelapse arbeitet mit den .xmp-Dateien. Ablauf: in Lightroom alle Bilder wählen → Metadaten in Datei speichern (Strg+S). Pass 1 und Pass 2 schreiben Belichtung und Keyframes hinein. Dann in Lightroom „Metadaten aus Dateien lesen“, nach Purelapse/Lightroom_Export exportieren und Pass 2 noch einmal starten: daraus entsteht das Video.':
        'Lightroom Classic has no command line – Purelapse works with the .xmp files. Workflow: in Lightroom select all frames → Save Metadata to File (Ctrl+S). Pass 1 and pass 2 write the exposure and keyframes into them. Then in Lightroom “Read Metadata from Files”, export to Purelapse/Lightroom_Export and start pass 2 again: the video is built from that export.',
    # Auswahllisten
    "Pass 1 – Anti-Flacker": "Pass 1 – anti-flicker",
    "Pass 2 – Rendern": "Pass 2 – render",
    "Sonnenaufgang (heller werdend)": "Sunrise (getting brighter)",
    "Sonnenuntergang (dunkler werdend)": "Sunset (getting darker)",
    "Gleichbleibend": "Constant",
    "Aus (1 Lauf)": "Off (1 run)",
    "1 Durchgang (2 Läufe)": "1 round (2 runs)",
    "2 Durchgänge (3 Läufe)": "2 rounds (3 runs)",
    "3 Durchgänge (4 Läufe)": "3 rounds (4 runs)",
    "720p (HD Ready)": "720p (HD Ready)",
    "1080p (FHD)": "1080p (FHD)",
    "Visuell Verlustfrei (CRF 16)": "Visually lossless (CRF 16)",
    "Hoch (CRF 20)": "High (CRF 20)",
    "Standard (CRF 23)": "Standard (CRF 23)",
    "Niedrig (CRF 28)": "Low (CRF 28)",
    "H.264 (CPU Standard)": "H.264 (CPU standard)",
    "1. Purelapse-Ordner im Bilderordner (empfohlen)": "1. Purelapse folder in the image folder (recommended)",
    "2. Übergeordneter Ordner": "2. Parent folder",
    "3. Programmverzeichnis (purelapse)": "3. Program directory (purelapse)",
    "4. Eigener Ordner wählen...": "4. Choose your own folder...",
    "Neue Version anlegen (_v1, _v2)": "Create new version (_v1, _v2)",
    "Datei überschreiben": "Overwrite file",
    # Hinweistexte
    "TT_FOLDER": "Ordner mit den Einzelbildern des Zeitraffers. JPG oder RAW, nicht gemischt.",
    "TT_REFRESH": "Liest den Ordner neu ein: Vorschaubilder, Helligkeitskurve und Keyframe-Markierungen.",
    "TT_BROWSE": "Ordner wählen …\nOrdner mit den Einzelbildern des Zeitraffers. JPG oder RAW, nicht gemischt.",
    "TT_IREFRESH": "Aktualisieren\nLiest den Ordner neu ein: Vorschaubilder, Helligkeitskurve und Keyframe-Markierungen.",
    "TT_IRESET": "Zurücksetzen …\nLöscht Arbeitsdateien im Bilderordner, um sauber neu zu beginnen.\nWas gelöscht wird, wählst du im nächsten Fenster.",
    "TT_ISETTINGS": "Einstellungen …\nEngine, Rechenkerne, Nachkalibrierung, Design und Sprache.",
    "TT_FORMAT": "JPG rechnet direkt und schnell. RAW gibt die Bilder an die Engine weiter und erlaubt Keyframes.",
    "TT_RAWSTEP": "Pass 1 misst die Helligkeit und legt die Korrektur in den Sidecar-Dateien ab.\nPass 2 laesst die Engine entwickeln, verteilt die Keyframe-Profile und baut das Video.",
    "TT_SCENE": "Gleichbleibend lässt den Lichtverlauf, wie er ist.\nSonnenaufgang und Sonnenuntergang erzwingen einen nie fallenden bzw. nie steigenden Verlauf.\nBei Sequenzen mit einem Buckel im Licht gehört das auf Gleichbleibend.",
    "TT_SETTINGS": "Engine, Rechenkerne, Nachkalibrierung, Design und Sprache.",
    "TT_QOPEN": "Zeigt die eingereihten Aufträge und arbeitet sie als Stapel ab.",
    "TT_LOG": "Blendet die ausführlichen Meldungen des Programms ein oder aus.\nBei einem Fehler öffnet sich das Protokoll von selbst.",
    "TT_MORE": "Rohfassung ohne Bearbeitung erzeugen oder zwei fertige Videos vergleichen.",
    "TT_SMOOTH": "Breite der Glaettung. Niedrig entfernt nur schnelles Flackern,\nhoch formt auch den Lichtverlauf um. Ab 85% blendet der Regler\nstufenlos in eine reine Ausgleichsgerade ueber.",
    "TT_EV": "Verschiebt die Zielhelligkeit der gesamten Sequenz.",
    "TT_ROI": "Beschraenkt die Helligkeitsmessung auf einen Bildbereich.\nSinnvoll, wenn Sonne, Lampen oder bewegte Objekte die Messung stoeren.",
    "TT_CORES": "Anzahl der Rechenkerne, die die Engine benutzen darf.",
    "TT_KFFILTER": ("Zeigt in der Bildleiste nur die als Keyframe\n"
                    "markierten Bilder. Praktisch, um die gesetzten\n"
                    "Stuetzstellen zu pruefen, ohne durch tausend\n"
                    "Vorschaubilder zu rollen.\n\n"
                    "Die Bilder werden nur ausgeblendet, nicht entfernt -\n"
                    "die Verbindung zum Diagramm bleibt dadurch erhalten."),
    "TT_PROCS": ("Wie viele Bilder gleichzeitig entwickelt werden.\n\n"
                 "ART und RawTherapee nutzen bei einem einzelnen Bild nur\n"
                 "vier bis acht Kerne sinnvoll aus. Auf einem vielkernigen\n"
                 "Rechner bringen mehrere Prozesse mit je wenigen Threads\n"
                 "deshalb deutlich mehr als ein Prozess mit allen Kernen.\n\n"
                 "Automatisch richtet sich nach Kernzahl und freiem\n"
                 "Arbeitsspeicher. Jede Instanz braucht rund 2 bis 3 GB.\n"
                 "Bei wenig Speicher auf 1 oder 2 stellen.\n\n"
                 "Bei Darktable hoechstens 4 Prozesse - darktable-cli braucht\n"
                 "mehr Speicher (rund 3 GB je Prozess), und mehr bringt auf\n"
                 "einer Grafikkarte nichts."),
    "TT_ARTCLI": "Ausfuehrbare Datei der Entwicklungs-Engine. Wird fuer Pass 2 benoetigt.",
    "TT_ENGINE": "ART, RawTherapee oder Darktable. ART und RawTherapee teilen sich\n"
                 "Kommandozeile und Profilformat (.arp bzw. .pp3). Darktable nutzt\n"
                 "die .xmp, die es selbst beim Import schreibt - Purelapse traegt die\n"
                 "Korrektur in die wirksame Belichtung ein und uebertraegt in Pass 2\n"
                 "den Modulstapel der Keyframes; eigene Bearbeitungen bleiben erhalten.\n"
                 "Pro Ordner muss man sich festlegen; liegen bereits Begleitdateien\n"
                 "vor, stellt Purelapse beim Einlesen selbst um.\n\n"
                 "Lightroom (XMP): Lightroom Classic hat keine Kommandozeile.\n"
                 "Purelapse schreibt Belichtung und Keyframe-Uebergaenge in die\n"
                 "XMP-Dateien; Lightroom liest sie ein und exportiert, aus dem\n"
                 "Export baut Purelapse das Video - mit Feinabgleich.",
    "TT_CALIB": "Purelapse misst das Ergebnis der Engine und schreibt die verbleibende\nAbweichung in die Sidecars zurueck, dann entwickelt die Engine erneut.\nAb Runde 2 nur noch die tatsaechlich geaenderten Bilder.\nEin Durchgang genuegt in aller Regel.",
    "TT_CAMPATH": "Legt den 16:9 Ausschnitt fuer das erste und das letzte Bild fest.\nDazwischen faehrt die Kamera weich von A nach B.",
    "TT_STAB": "Gleicht Verwacklungen zwischen den Bildern aus. Kostet etwas Bildrand.",
    "TT_ERSTES": "Zum ersten Bild",
    "TT_LETZTES": "Zum letzten Bild",
    "TT_STARTBILD": "Das gewaehlte Bild wird das erste des Arbeitsgangs. Alle Bilder\n"
                    "davor bleiben in Pass 1, Pass 2 und im Video aussen vor.\n"
                    "Zuruecknehmen: das allererste Bild waehlen und noch einmal klicken.\n"
                    "Danach Pass 1 neu laufen lassen.",
    "TT_ENDBILD": "Das gewaehlte Bild wird das letzte des Arbeitsgangs. Alle Bilder\n"
                  "danach bleiben aussen vor.\n"
                  "Zuruecknehmen: das allerletzte Bild waehlen und noch einmal klicken.\n"
                  "Danach Pass 1 neu laufen lassen.",
    "TT_ARPTPL": "Vollständiges, in der Engine gespeichertes Profil.\n"
                 "Purelapse setzt darin nur die Belichtung und lässt alles andere unangetastet.\n"
                 "Liegt bereits ein von der Engine geschriebenes Profil im Bilderordner,\n"
                 "wird das automatisch benutzt.",
    "TT_DIAG": "Legt im Ordner Purelapse Messprotokolle und Pruefberichte an:\n"
               "purelapse_pass1.csv, purelapse_pass2.csv, purelapse_profiles.csv,\n"
               "purelapse_arp_check.log und purelapse_art.log.\n\n"
               "Nur fuer die Fehlersuche gedacht. Im Normalbetrieb aus lassen -\n"
               "Warnungen erscheinen ohnehin im Log-Fenster.",
    "TT_TIFF16": "Die Engine entwickelt in Pass 2 nach 16-Bit-TIFF statt nach JPG, und\n"
                 "das Video wird durchgehend in 16 Bit gerechnet. Feine Verlaeufe im\n"
                 "Himmel bleiben dadurch frei von Stufen - vor allem zusammen mit\n"
                 "HEVC 10 Bit oder ProRes.\n\n"
                 "Braucht ein Vielfaches an Platz: bei 24 Megapixeln etwa 120 MB je\n"
                 "Bild, bei 1000 Bildern also rund 120 GB. Purelapse prueft vorher,\n"
                 "ob der Platz reicht.",
    "TT_SCHNELL": "Ein grobes Video in kurzer Zeit, aus den eingebetteten Vorschaubildern\n"
                  "der Kamera, mit der Glaettung aus dem Diagramm und dem eingestellten\n"
                  "Bildausschnitt.\n\n"
                  "Nur zur ersten Beurteilung: keine Engine, keine Keyframes, keine\n"
                  "Schnelleinstellungen, keine Effekte, hoechstens 1280 Pixel breit.\n"
                  "Das Video oeffnet sich nach dem Erstellen von selbst.",
    "TT_DENOISE": "Rauschminderung, staerker bei hohen ISO-Werten.",
    "TT_REVERSE": "Spielt die Sequenz rueckwaerts ab.",
    "TT_TEL": "Blendet Uhrzeit, ISO, Blende und Belichtungszeit ins Bild ein.",
    "TT_ASTRO": "Entfernt Satellitenspuren, indem jedes Bild mit seinen beiden Nachbarn verglichen wird.",
    "TT_HOTPIX": "Beseitigt defekte Sensorpixel.\nBei RAW uebernimmt das die Engine (bei Darktable das Modul \u201eHotpixel\u201c).\nBei JPG sucht Purelapse zuerst die Punkte, die in der ganzen Sequenz\nan derselben Stelle auffallen - Sterne und Motivdetails bleiben\ndadurch unangetastet.",
    "TT_RESET": "Loescht Arbeitsdateien im Bilderordner, um sauber neu zu beginnen.\nWas geloescht wird, waehlst du im naechsten Fenster.",
    "TT_LANG": "Sprache der Oberflaeche.",
    "TT_FADE": "Blendet den Videoanfang aus Schwarz auf und das Ende nach Schwarz ab.",
    "TT_BLUR": "Mittelt mehrere Bilder zu einem Videoframe. Erzeugt weiche Bewegung,\nkostet aber zeitliche Schaerfe.",
    "TT_START": "Startet den gewaehlten Arbeitsschritt.",
    "TT_PLAIN": "Erzeugt den Zeitraffer ohne jede Bildbearbeitung.\nNur Ordner, Bildrate, Aufloesung, Codec und Qualitaet werden beachtet.\nDeflicker, Keyframes, Motion Blur, Denoise und Stabilisierung bleiben aus.\nDient als Referenz zum Vergleich.",
    "TT_QADD": "Legt den aktuellen Ordner mit allen Einstellungen als Auftrag ab.\nDanach kannst du den naechsten Ordner einlesen und ebenfalls einreihen.",
    "TT_QRUN": "Arbeitet alle offenen Auftraege nacheinander ab.\nAbbrechen haelt den Stapel an; beim naechsten Start geht es an\nderselben Stelle weiter, bereits entwickelte Bilder bleiben erhalten.",
    "TT_PREVIEW": "Entwickelt fuenf ueber die Sequenz verteilte Bilder mit den\naktuellen Einstellungen und zeigt sie an. Bei RAW laeuft dafuer\ndie Engine, deshalb muss Pass 1 vorher gelaufen sein.\nSpart einen kompletten Fehldurchlauf.",
    "TT_OPENDIR": "Oeffnet den Ordner, in dem das fertige Video liegt,\nim Dateimanager des Systems.",
    "TT_ENTFLACKERN": "Grundschalter fuer den Helligkeitsausgleich.\nOhne Haken baut Purelapse den Zeitraffer mit der Helligkeit, die die\nKamera aufgenommen hat. Keyframes, Kamerafahrt, Telemetrie und Effekte\nwirken trotzdem. Bei RAW bereitet Pass 1 dann nur die Profile vor.",
    "TT_NACHT": "Laesst die Nacht eines 24-Stunden-Zeitraffers aus dem Video.\nGemessen wird die Helligkeit der Szene (Bild und Belichtung aus den\nEXIF-Daten) in Blenden unter dem Tageslicht der Serie. Die Grenze\nsteht auch als gestrichelte Linie im Diagramm und laesst sich dort\nverschieben. Entflackert wird weiter die ganze Serie, damit die\nDaemmerung stimmt.",
    "TT_COMPARE": "Stellt zwei fertige Videos gegenueber - nebeneinander oder\nals geteiltes Bild mit Schnitt durch die Mitte.",
    "TT_SUN": "Breiten- und Laengengrad des Aufnahmeortes plus Zeitzonen-Offset\n"
              "zur Aufnahmezeit (z.B. 2 fuer MESZ). Zeigt den Sonnenstand als\n"
              "Zusatzkurve - hilfreich, um Keyframes an den Daemmerungsgrenzen\n"
              "(gepunktete Linien: buergerlich/nautisch/astronomisch) zu setzen.\n"
              "Hat keinen Einfluss auf die Deflicker-Berechnung selbst.",
}
TRANSLATIONS_TT_EN = {
    "TT_ENTFLACKERN": "Master switch for the brightness correction.\nUnticked, Purelapse builds the timelapse with the brightness the\ncamera recorded. Keyframes, camera move, telemetry and effects still\nwork. For RAW, pass 1 then only prepares the profiles.",
    "TT_NACHT": "Leaves the night of a 24-hour timelapse out of the video.\nMeasured is the brightness of the scene (image and exposure from the\nEXIF data) in stops below the daylight of the series. The threshold\nis also shown as a dashed line in the chart and can be dragged there.\nThe whole series is still deflickered so the twilight is right.",
    "TT_SETTINGS": "Engine, CPU cores, recalibration, theme and language.",
    "TT_QOPEN": "Shows the queued jobs and runs them as a batch.",
    "TT_LOG": "Shows or hides the program's detailed messages.\nThe log opens by itself when an error occurs.",
    "TT_MORE": "Build an untouched version or compare two finished videos.",
    "TT_FOLDER": "Folder holding the timelapse frames. JPG or RAW, not mixed.",
    "TT_REFRESH": "Re-reads the folder: thumbnails, brightness curve and keyframe marks.",
    "TT_BROWSE": "Choose folder …\nFolder holding the timelapse frames. JPG or RAW, not mixed.",
    "TT_IREFRESH": "Refresh\nRe-reads the folder: thumbnails, brightness curve and keyframe marks.",
    "TT_IRESET": "Reset …\nDeletes working files in the image folder to start over cleanly.\nYou choose what to delete in the next window.",
    "TT_ISETTINGS": "Settings …\nEngine, CPU cores, recalibration, theme and language.",
    "TT_FORMAT": "JPG is processed directly and quickly. RAW is handed to the engine and allows keyframes.",
    "TT_RAWSTEP": "Pass 1 measures brightness and stores the correction in the sidecar files.\nPass 2 lets the engine develop, distributes the keyframe profiles and builds the video.",
    "TT_SCENE": "Constant leaves the light curve alone.\nSunrise and Sunset force a never-falling resp. never-rising curve.\nFor sequences with a hump in the light, use Constant.",
    "TT_SMOOTH": "Width of the smoothing. Low removes only fast flicker,\nhigh also reshapes the light curve. From 85% the slider fades\ncontinuously into a pure straight-line fit.",
    "TT_EV": "Shifts the target brightness of the whole sequence.",
    "TT_ROI": "Limits the brightness measurement to one area of the frame.\nUseful when sun, lamps or moving objects disturb the measurement.",
    "TT_CORES": "Number of CPU cores the engine may use.",
    "TT_KFFILTER": ("Shows only the images marked as keyframes in the\n"
                    "gallery. Handy for checking the chosen anchor\n"
                    "points without scrolling through a thousand\n"
                    "thumbnails.\n\n"
                    "The images are only hidden, not removed, so the\n"
                    "link to the graph stays intact."),
    "TT_PROCS": ("How many images are developed at the same time.\n\n"
                 "ART and RawTherapee only make good use of four to eight\n"
                 "cores on a single image. On a many-core machine several\n"
                 "processes with a few threads each are therefore much\n"
                 "faster than one process with every core.\n\n"
                 "Automatic follows core count and free memory. Each\n"
                 "instance needs roughly 2 to 3 GB. Set it to 1 or 2 if\n"
                 "memory is tight.\n\n"
                 "With Darktable at most 4 processes - darktable-cli needs\n"
                 "more memory (about 3 GB per process), and more brings\n"
                 "nothing on a single graphics card."),
    "TT_ARTCLI": "Executable of the development engine. Required for pass 2.",
    "TT_ENGINE": "ART, RawTherapee or Darktable. ART and RawTherapee share the\n"
                 "command line and profile format (.arp resp. .pp3). Darktable uses\n"
                 "the .xmp it writes itself on import - Purelapse writes the\n"
                 "correction into the effective exposure and, in pass 2, carries the\n"
                 "keyframes' module stack across; your own edits are kept.\n"
                 "You have to commit per folder; if sidecars are present already,\n"
                 "Purelapse switches automatically when reading the folder.\n\n"
                 "Lightroom (XMP): Lightroom Classic has no command line.\n"
                 "Purelapse writes the exposure and keyframe transitions into the\n"
                 "XMP files; Lightroom reads them and exports, and Purelapse builds\n"
                 "the video from the export - with fine adjustment.",
    "TT_CALIB": "Purelapse measures the engine's result and writes the remaining deviation\nback into the sidecars, then the engine develops again.\nFrom round 2 on, only the frames that actually changed.\nOne round is usually enough.",
    "TT_CAMPATH": "Defines the 16:9 crop for the first and the last frame.\nIn between the camera moves smoothly from A to B.",
    "TT_STAB": "Compensates camera shake between frames. Costs a little image border.",
    "TT_ERSTES": "Go to the first frame",
    "TT_LETZTES": "Go to the last frame",
    "TT_STARTBILD": "The selected frame becomes the first of the workflow. All frames\n"
                    "before it are left out of pass 1, pass 2 and the video.\n"
                    "To undo: select the very first frame and click again.\n"
                    "Then run pass 1 again.",
    "TT_ENDBILD": "The selected frame becomes the last of the workflow. All frames\n"
                  "after it are left out.\n"
                  "To undo: select the very last frame and click again.\n"
                  "Then run pass 1 again.",
    "TT_ARPTPL": "A complete profile saved by the engine.\n"
                 "Purelapse only sets the exposure in it and leaves everything else untouched.\n"
                 "If the image folder already holds a profile written by the engine,\n"
                 "that one is used automatically.",
    "TT_DIAG": "Writes measurement logs and check reports into the Purelapse folder:\n"
               "purelapse_pass1.csv, purelapse_pass2.csv, purelapse_profiles.csv,\n"
               "purelapse_arp_check.log and purelapse_art.log.\n\n"
               "Meant for troubleshooting only. Leave it off in normal use -\n"
               "warnings appear in the log window anyway.",
    "TT_TIFF16": "In pass 2 the engine develops to 16-bit TIFF instead of JPG, and the\n"
                 "video is computed in 16 bit throughout. Fine gradients in the sky\n"
                 "stay free of banding - especially together with HEVC 10 bit or ProRes.\n\n"
                 "Needs many times the space: with 24 megapixels about 120 MB per\n"
                 "frame, so roughly 120 GB for 1000 frames. Purelapse checks\n"
                 "beforehand whether there is enough space.",
    "TT_SCHNELL": "A rough video in little time, made from the camera's embedded\n"
                  "preview images, with the smoothing from the graph and the chosen\n"
                  "crop.\n\n"
                  "For a first impression only: no engine, no keyframes, no quick\n"
                  "settings, no effects, at most 1280 pixels wide.\n"
                  "The video opens by itself once it is ready.",
    "TT_DENOISE": "Noise reduction, stronger at high ISO values.",
    "TT_REVERSE": "Plays the sequence backwards.",
    "TT_TEL": "Overlays time, ISO, aperture and shutter speed onto the frame.",
    "TT_ASTRO": "Removes satellite trails by comparing each frame with its two neighbours.",
    "TT_HOTPIX": "Fixes defective sensor pixels.\nFor RAW this is handled by the engine (for darktable the \u201chot pixels\u201d module).\nFor JPG, Purelapse first locates the points that stand out at the same\nposition throughout the whole sequence - stars and image detail are\nleft untouched.",
    "TT_RESET": "Deletes working files in the image folder to start over cleanly.\nYou choose what to delete in the next window.",
    "TT_LANG": "Language of the user interface.",
    "TT_FADE": "Fades the start of the video in from black and the end out to black.",
    "TT_BLUR": "Averages several frames into one video frame. Creates smooth motion\nat the cost of temporal sharpness.",
    "TT_START": "Starts the selected step.",
    "TT_PLAIN": "Builds the timelapse without any image processing.\nOnly folder, frame rate, resolution, codec and quality apply.\nDeflicker, keyframes, motion blur, denoise and stabilisation stay off.\nUseful as a reference for comparison.",
    "TT_QADD": "Stores the current folder together with all settings as a job.\nYou can then load the next folder and queue it as well.",
    "TT_QRUN": "Works through all pending jobs one after another.\nCancel pauses the batch; the next start resumes at the same point,\nkeeping images that were already developed.",
    "TT_PREVIEW": "Develops five frames spread across the sequence using the current\nsettings and shows them. For RAW this runs the engine, so pass 1 must\nhave completed first.\nSaves a whole wasted run.",
    "TT_OPENDIR": "Opens the folder containing the finished video\nin the system file manager.",
    "TT_COMPARE": "Places two finished videos side by side, or as a split screen\ndivided down the middle.",
    "TT_SUN": "Latitude and longitude of the shooting location plus the UTC\n"
              "offset at capture time (e.g. 2 for CEST). Shows sun elevation as\n"
              "an extra curve - useful for placing keyframes at twilight\n"
              "boundaries (dotted lines: civil/nautical/astronomical).\n"
              "Has no effect on the deflicker calculation itself.",
}


# Darktable liest .xmp-Dateien nur beim ersten Import. Wo Purelapse
# Sterne setzt, muss Darktable deshalb ausdruecklich nachladen.
DT_KEYFRAME_HINWEIS = {
    'de': ("Darktable und Keyframes: Purelapse uebertraegt alle Module der "
           "Keyframes in die Bilder dazwischen. Zahlenwerte - Weissabgleich, "
           "Schaerfe, Saettigung, Kontrast, Filmic/Sigmoid und viele mehr - "
           "werden weich ueberblendet; Schalter, Auswahllisten und Masken "
           "kommen vom naeheren Keyframe. Damit nichts springt, in allen "
           "Keyframes dieselben Module verwenden: am einfachsten den Verlauf "
           "des ersten Keyframes auf die anderen kopieren (Strg+Umschalt+C, "
           "dann Strg+Umschalt+V) und danach nur die Werte anpassen."),
    'en': ("darktable and keyframes: Purelapse carries all modules of the "
           "keyframes into the frames in between. Numeric values - white "
           "balance, sharpness, saturation, contrast, filmic/sigmoid and many "
           "more - are blended smoothly; switches, drop-downs and masks come "
           "from the nearer keyframe. To avoid jumps, use the same modules in "
           "all keyframes: the easiest way is to copy the history of the "
           "first keyframe to the others (Ctrl+Shift+C, then Ctrl+Shift+V) "
           "and only adjust the values afterwards."),
}

DT_STERNE_HINWEIS = {
    'de': ("Darktable und Sterne: Darktable liest die .xmp-Dateien nur beim "
           "ersten Import eines Bildes, danach gilt seine eigene Bibliothek. "
           "Damit die hier gesetzten Sterne in Darktable erscheinen: in "
           "Darktable unter Einstellungen \u2192 Speicherung \u201ebeim Start "
           "nach aktualisierten XMP-Dateien suchen\u201c einschalten, Darktable "
           "neu starten und bei der Abfrage \u201eXMP \u2192 Bibliothek\u201c "
           "waehlen. Einmalig geht es auch so: die Bilder im Leuchttisch "
           "entfernen (nicht loeschen) und den Ordner neu importieren."),
    'en': ("darktable and stars: darktable reads the .xmp files only when an "
           "image is first imported; after that its own library applies. To "
           "make the stars set here appear in darktable: enable \u201clook for "
           "updated XMP files on startup\u201d under preferences \u2192 storage, "
           "restart darktable and choose \u201cXMP \u2192 library\u201d when "
           "asked. As a one-off you can also remove the images from the "
           "library (not delete) and import the folder again."),
}
