# Pruefungen

Rund 3000 Pruefungen, die das ganze Programm durchlaufen: echte Messung,
echtes FFmpeg, echte Videos. Nachgebaut (in `pruefstand/`) sind nur Qt,
rawpy, exifread, pyqtgraph und die Engines ART und RawTherapee.

    pip install numpy scipy opencv-python-headless
    python tests/alle.py              # alle
    python tests/alle.py "test_dt*"   # nur einige

Arbeitsdateien landen in `$PURELAPSE_ARBEIT` (Standard: ein Ordner im
temporaeren Verzeichnis).
