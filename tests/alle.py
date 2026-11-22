#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Laesst alle Pruefungen laufen:  python tests/alle.py  [Muster]

Gebraucht werden Python 3.9+, NumPy, SciPy, OpenCV und FFmpeg. Qt, rawpy,
exifread, pyqtgraph und die Engines sind in tests/pruefstand nachgebaut.
"""
import os, sys, glob, subprocess, time
hier = os.path.dirname(os.path.abspath(__file__))
# Die nachgebauten Engines muessen ausfuehrbar sein. Git uebernimmt das Recht
# nur, wenn es beim Einchecken gesetzt war - also hier sicherstellen.
for _name in ("ART-cli", "rawtherapee-cli", "fake_engine.py"):
    _p = os.path.join(hier, "pruefstand", _name)
    if os.path.exists(_p):
        os.chmod(_p, 0o755)
muster = sys.argv[1] if len(sys.argv) > 1 else "test_*.py"
fehler = []
for t in sorted(glob.glob(os.path.join(hier, muster))):
    t0 = time.time()
    r = subprocess.run([sys.executable, t], capture_output=True, text=True)
    letzte = (r.stdout.strip().splitlines() or [""])[-1]
    # Manche Reihen melden Fehler nur in der letzten Zeile ("... 2 fehlgeschlagen")
    gezaehlt = letzte.rsplit(",", 1)[-1].split()
    ok = r.returncode == 0 and not (gezaehlt[:1] != ["0"] and gezaehlt[-1:] == ["fehlgeschlagen"])
    print(f"{'OK    ' if ok else 'FEHLER'} {os.path.basename(t):24s} {time.time() - t0:5.0f} s  {letzte}")
    if not ok:
        fehler.append(t)
        print("\n".join((r.stdout + r.stderr).strip().splitlines()[-25:]))
print(f"\n{len(fehler)} von {len(glob.glob(os.path.join(hier, muster)))} Pruefreihen fehlgeschlagen")
sys.exit(1 if fehler else 0)
