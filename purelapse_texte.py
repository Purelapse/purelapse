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
    "1. Quell-Ordner (Bilder)": "1. Source folder (images)",
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
    "TT_ENGINE": "ART, RawTherapee oder Darktable. ART und RawTherapee teilen sich\\n"
                 "Kommandozeile und Profilformat (.arp bzw. .pp3). Darktable nutzt\\n"
                 "die .xmp, die es selbst beim Import schreibt - Purelapse traegt die\\n"
                 "Korrektur in die wirksame Belichtung ein und uebertraegt in Pass 2\\n"
                 "den Modulstapel der Keyframes; eigene Bearbeitungen bleiben erhalten.\\n"
                 "Pro Ordner muss man sich festlegen; liegen bereits Begleitdateien\\n"
                 "vor, stellt Purelapse beim Einlesen selbst um.",
    "TT_CALIB": "Purelapse misst das Ergebnis der Engine und schreibt die verbleibende\nAbweichung in die Sidecars zurueck, dann entwickelt die Engine erneut.\nAb Runde 2 nur noch die tatsaechlich geaenderten Bilder.\nEin Durchgang genuegt in aller Regel.",
    "TT_CAMPATH": "Legt den 16:9 Ausschnitt fuer das erste und das letzte Bild fest.\nDazwischen faehrt die Kamera weich von A nach B.",
    "TT_STAB": "Gleicht Verwacklungen zwischen den Bildern aus. Kostet etwas Bildrand.",
    "TT_DENOISE": "Rauschminderung, staerker bei hohen ISO-Werten.",
    "TT_REVERSE": "Spielt die Sequenz rueckwaerts ab.",
    "TT_TEL": "Blendet Uhrzeit, ISO, Blende und Belichtungszeit ins Bild ein.",
    "TT_ASTRO": "Entfernt Satellitenspuren, indem jedes Bild mit seinen beiden Nachbarn verglichen wird.",
    "TT_HOTPIX": "Beseitigt defekte Sensorpixel.\\nBei RAW uebernimmt das die Engine (bei Darktable das Modul \u201eHotpixel\u201c).\\nBei JPG sucht Purelapse zuerst die Punkte, die in der ganzen Sequenz\\nan derselben Stelle auffallen - Sterne und Motivdetails bleiben\\ndadurch unangetastet.",
    "TT_RESET": "Loescht Arbeitsdateien im Bilderordner, um sauber neu zu beginnen.\nWas geloescht wird, waehlst du im naechsten Fenster.",
    "TT_LANG": "Sprache der Oberflaeche.",
    "TT_FADE": "Blendet den Videoanfang aus Schwarz auf und das Ende nach Schwarz ab.",
    "TT_BLUR": "Mittelt mehrere Bilder zu einem Videoframe. Erzeugt weiche Bewegung,\nkostet aber zeitliche Schaerfe.",
    "TT_START": "Startet den gewaehlten Arbeitsschritt.",
    "TT_PLAIN": "Erzeugt den Zeitraffer ohne jede Bildbearbeitung.\\nNur Ordner, Bildrate, Aufloesung, Codec und Qualitaet werden beachtet.\\nDeflicker, Keyframes, Motion Blur, Denoise und Stabilisierung bleiben aus.\\nDient als Referenz zum Vergleich.",
    "TT_QADD": "Legt den aktuellen Ordner mit allen Einstellungen als Auftrag ab.\\nDanach kannst du den naechsten Ordner einlesen und ebenfalls einreihen.",
    "TT_QRUN": "Arbeitet alle offenen Auftraege nacheinander ab.\\nAbbrechen haelt den Stapel an; beim naechsten Start geht es an\\nderselben Stelle weiter, bereits entwickelte Bilder bleiben erhalten.",
    "TT_PREVIEW": "Entwickelt fuenf ueber die Sequenz verteilte Bilder mit den\\naktuellen Einstellungen und zeigt sie an. Bei RAW laeuft dafuer\\ndie Engine, deshalb muss Pass 1 vorher gelaufen sein.\\nSpart einen kompletten Fehldurchlauf.",
    "TT_OPENDIR": "Oeffnet den Ordner, in dem das fertige Video liegt,\\nim Dateimanager des Systems.",
    "TT_COMPARE": "Stellt zwei fertige Videos gegenueber - nebeneinander oder\\nals geteiltes Bild mit Schnitt durch die Mitte.",
    "TT_SUN": "Breiten- und Laengengrad des Aufnahmeortes plus Zeitzonen-Offset\n"
              "zur Aufnahmezeit (z.B. 2 fuer MESZ). Zeigt den Sonnenstand als\n"
              "Zusatzkurve - hilfreich, um Keyframes an den Daemmerungsgrenzen\n"
              "(gepunktete Linien: buergerlich/nautisch/astronomisch) zu setzen.\n"
              "Hat keinen Einfluss auf die Deflicker-Berechnung selbst.",
}
TRANSLATIONS_TT_EN = {
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
    "TT_ENGINE": "ART, RawTherapee or Darktable. ART and RawTherapee share the\\n"
                 "command line and profile format (.arp resp. .pp3). Darktable uses\\n"
                 "the .xmp it writes itself on import - Purelapse writes the\\n"
                 "correction into the effective exposure and, in pass 2, carries the\\n"
                 "keyframes' module stack across; your own edits are kept.\\n"
                 "You have to commit per folder; if sidecars are present already,\\n"
                 "Purelapse switches automatically when reading the folder.",
    "TT_CALIB": "Purelapse measures the engine's result and writes the remaining deviation\nback into the sidecars, then the engine develops again.\nFrom round 2 on, only the frames that actually changed.\nOne round is usually enough.",
    "TT_CAMPATH": "Defines the 16:9 crop for the first and the last frame.\nIn between the camera moves smoothly from A to B.",
    "TT_STAB": "Compensates camera shake between frames. Costs a little image border.",
    "TT_DENOISE": "Noise reduction, stronger at high ISO values.",
    "TT_REVERSE": "Plays the sequence backwards.",
    "TT_TEL": "Overlays time, ISO, aperture and shutter speed onto the frame.",
    "TT_ASTRO": "Removes satellite trails by comparing each frame with its two neighbours.",
    "TT_HOTPIX": "Fixes defective sensor pixels.\\nFor RAW this is handled by the engine (for darktable the \u201chot pixels\u201d module).\\nFor JPG, Purelapse first locates the points that stand out at the same\\nposition throughout the whole sequence - stars and image detail are\\nleft untouched.",
    "TT_RESET": "Deletes working files in the image folder to start over cleanly.\nYou choose what to delete in the next window.",
    "TT_LANG": "Language of the user interface.",
    "TT_FADE": "Fades the start of the video in from black and the end out to black.",
    "TT_BLUR": "Averages several frames into one video frame. Creates smooth motion\nat the cost of temporal sharpness.",
    "TT_START": "Starts the selected step.",
    "TT_PLAIN": "Builds the timelapse without any image processing.\\nOnly folder, frame rate, resolution, codec and quality apply.\\nDeflicker, keyframes, motion blur, denoise and stabilisation stay off.\\nUseful as a reference for comparison.",
    "TT_QADD": "Stores the current folder together with all settings as a job.\\nYou can then load the next folder and queue it as well.",
    "TT_QRUN": "Works through all pending jobs one after another.\\nCancel pauses the batch; the next start resumes at the same point,\\nkeeping images that were already developed.",
    "TT_PREVIEW": "Develops five frames spread across the sequence using the current\\nsettings and shows them. For RAW this runs the engine, so pass 1 must\\nhave completed first.\\nSaves a whole wasted run.",
    "TT_OPENDIR": "Opens the folder containing the finished video\\nin the system file manager.",
    "TT_COMPARE": "Places two finished videos side by side, or as a split screen\\ndivided down the middle.",
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
