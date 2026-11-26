# -*- coding: utf-8 -*-
"""Engines als Flatpak: erkennen, aufrufen, Ordner freigeben."""
import os, sys, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
o = os.path.join(ARBEIT, "flatpak"); shutil.rmtree(o, ignore_errors=True)
nutzer = os.path.join(o, "home", ".local", "share", "flatpak")
system = os.path.join(o, "var")
os.makedirs(os.path.join(nutzer, "app", "com.rawtherapee.RawTherapee", "current"))
os.makedirs(os.path.join(system, "app", "org.darktable.Darktable", "current"))
os.makedirs(os.path.join(system, "app", "us.pixls.art.ART"))   # ohne current: unfertig
orte = [system, nutzer]

print("=== Erkennen ===")
pruef(pe.flatpak_suchen('rt', orte, nt=False) == "flatpak:com.rawtherapee.RawTherapee", "RT (Nutzer)")
pruef(pe.flatpak_suchen('dt', orte, nt=False) == "flatpak:org.darktable.Darktable", "dt (System)")
pruef(pe.flatpak_suchen('art', orte, nt=False) == "", "ART ohne current")
pruef(pe.engine_vorhanden("flatpak:com.rawtherapee.RawTherapee", orte), "vorhanden")
pruef(not pe.engine_vorhanden("flatpak:us.pixls.art.ART", orte), "nicht vorhanden")
pruef(not pe.engine_vorhanden("", orte) and not pe.engine_vorhanden(None, orte), "leer")
pruef(pe.engine_vorhanden(os.path.abspath(__file__)), "Datei")
pruef(pe.flatpak_suchen('rt', orte, nt=True) == "", "unter Windows gibt es kein Flatpak")
pruef(set(pe.FLATPAK_IDS) == {k for k, v in pe.ENGINES.items() if v['bin']},
      "jede Engine mit Programm hat eine App-ID")

print("=== Aufruf ===")
bilder = os.path.join(o, "bilder"); os.makedirs(bilder)
for n in ("a.NEF", "b.NEF"):
    open(os.path.join(bilder, n), "wb").write(b"x")
aus = os.path.join(bilder, "Purelapse", "jpg")
cmd = ["flatpak:com.rawtherapee.RawTherapee", "-S", "-Y", "-o", aus, "-c",
       os.path.join(bilder, "a.NEF"), os.path.join(bilder, "b.NEF")]
echt = pe.engine_befehl(cmd, {'OMP_NUM_THREADS': '4'})
pruef(echt[:3] == ["flatpak", "run", "--command=rawtherapee-cli"], f"{echt[:3]}")
i = echt.index("com.rawtherapee.RawTherapee")
pruef(echt[i + 1:] == cmd[1:], "Argumente unveraendert")
frei = [a for a in echt[:i] if a.startswith("--filesystem=")]
pruef(frei == [f"--filesystem={bilder}"], f"Freigaben: {frei}")
pruef("--env=OMP_NUM_THREADS=4" in echt[:i], "Threads")
# Arbeitsordner unter /tmp und Konfigurationsordner von darktable
tmp = os.path.join(o, "tmp"); slot = os.path.join(o, "slot1")
cmd = ["flatpak:org.darktable.Darktable", os.path.join(bilder, "a.NEF"), tmp + "/v.xmp",
       tmp + "/v.jpg", "--core", "--configdir", slot, "--conf", "a/b=1"]
echt = pe.engine_befehl(cmd)
pruef(echt[2] == "--command=darktable-cli", f"{echt[2]}")
frei = [a for a in echt if a.startswith("--filesystem=")]
pruef(f"--filesystem={bilder}" in frei and f"--filesystem={tmp}" in frei
      and f"--filesystem={slot}" in frei and len(frei) == 3, f"{frei}")
# Unterordner eines freigegebenen Ordners zaehlen nicht doppelt
frei = pe._flatpak_freigaben([bilder, os.path.join(bilder, "a.NEF"), aus])
pruef(frei == [bilder], f"{frei}")
pruef(not any(a.startswith("--env=") for a in echt), "ohne env keine Variablen")
# Systemordner werden nie freigegeben
echt = pe.engine_befehl(["flatpak:us.pixls.art.ART", "-p", "/usr/share/x.arp", "-c", "/etc/y"])
pruef(not any(a.startswith("--filesystem=") for a in echt) and "--command=ART-cli" in echt, f"{echt}")
# normaler Pfad bleibt, wie er ist
pruef(pe.engine_befehl(["/usr/bin/rawtherapee-cli", "-c", "x"]) == ["/usr/bin/rawtherapee-cli", "-c", "x"], "Datei")
pruef(pe.engine_befehl([]) == [], "leer")

print("=== Oberflaeche und Aufrufstellen ===")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef(src.count("engine_befehl(") >= 3, "Engine-Aufrufe ohne Flatpak-Umsetzung")
pruef("os.path.isfile(cli_pfad)" not in src and "os.path.isfile(art)" not in src, "alte Dateipruefung")
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
