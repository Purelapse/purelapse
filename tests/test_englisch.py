# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""D2: Protokoll eines Laufs in englischer Oberflaeche ohne deutsche Zeilen."""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
DEUTSCH = re.compile(r"\b(Bilder|Starte|Berechne|gefunden|ueber|über|fuer|für|nicht|wurde|werden|Profile geprueft|"
                     r"Restflackern|Entwicklung|Nachkalibrierung|Messung|keine|Keine|gleichzeitig|je Bild)\b")
for name, kw in (("jpg", dict(art="jpg")), ("raw", {})):
    o = os.path.join(ARBEIT, "en_" + name); d, _ = szene(o, n=24, sonne=True, **kw)
    zeilen = []
    if name == "jpg":
        e = lauf(parameter(o, d, lang='en')); zeilen += e.log
    else:
        pe.set_engine('rt')
        e1 = lauf(parameter(o, d, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI, lang='en', diag=True))
        for f in d[5], d[18]:
            open(f + ".xmp", "w").write('<x xmp:Rating="5"></x>')
        e2 = lauf(parameter(o, d, raw_mode='pass2', art_cli_path=RT_CLI, lang='en'))
        zeilen += e1.log + e2.log
        pruef(e1.ok() and e2.ok(), f"Lauf: {e1.fehler[:1]} {e2.fehler[:1]}")
    deutsch = [z for z in zeilen if DEUTSCH.search(z) and "-cli" not in z and "ffmpeg" not in z.lower()
               and not z.strip().startswith(("/", "[")) and "Deflickered_JPG" not in z]
    pruef(not deutsch, f"{name}: deutsche Zeilen: {deutsch[:6]}")
    print(f"   {name}: {len(zeilen)} Zeilen")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef('"Target reached"' in src and '"Residual flicker" in zeile' in src, "Faerbung/Telegram")
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
