#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Pruefungen gegen das stille Entwickeln mit Standardwerten.

Der Fehlerfall, um den es geht: die Engine findet kein Profil, nimmt
ihre Standardwerte und liefert ein unentflackertes Video - ohne dass
irgendwo eine Fehlermeldung erscheint.
"""
import io, os, ast, sys, shutil, tempfile, subprocess, collections

BASIS = os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = io.open(f"{BASIS}/purelapse_main.py", encoding="utf-8").read()
SCRATCH = os.environ.get("PURELAPSE_ARBEIT", os.path.join(__import__("tempfile").gettempdir(), "purelapse_pruefung"))
sys.path.insert(0, BASIS)
import purelapse_engines as pe

ok_n = fail_n = 0
def pruef(b, text):
    global ok_n, fail_n
    if b: ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")

def schnitt(txt, von, bis):
    return txt[txt.index(von):txt.index(bis)]

# --- Umgebung fuer die Pruefmethode nachbauen ------------------------
ns = {"os": os, "subprocess": subprocess, "tempfile": tempfile,
      "ENGINES": pe.ENGINES, "read_arp_dict": pe.read_arp_dict}
for name in ("eng", "sidecar"):
    ns[name] = getattr(pe, name)
blk = schnitt(src, "    def _pruefe_sidecars", "    def _render_with_engine")
exec("class Sig:\n"
     "    def __init__(self): self.zeilen = []\n"
     "    def emit(self, t): self.zeilen.append(t)\n"
     "class W:\n"
     "    def __init__(self): self.log = Sig(); self.p = {}\n"
     "    def _t(self, de, en): return en if self.p.get('lang') == 'en' else de\n" + blk, ns)

def bau(ordner, n=6, endung=".pp3", ev=None, fehlend=0):
    """Legt n Bilder mit Profilen an. ev=None heisst: variierend."""
    shutil.rmtree(ordner, ignore_errors=True)
    os.makedirs(ordner)
    bilder = []
    for i in range(n):
        f = os.path.join(ordner, f"IMG_{i:03d}.NEF")
        io.open(f, "w").write("x")
        bilder.append(f)
        if i >= n - fehlend:
            continue
        wert = ev if ev is not None else -0.1 * i
        pe.write_arp_dict(f + endung, {
            'Version': {'Version': '346'},
            'Exposure': {'Enabled': 'true', 'Compensation': f"{wert:.3f}"},
            'White Balance': {'Setting': 'Camera'},
        })
    return bilder

print("=== 1. Alles in Ordnung ===")
pe.set_engine('rt')
ordner = os.path.join(SCRATCH, "sc_ok")
bilder = bau(ordner, 6)
w = ns["W"]()
w._pruefe_sidecars(bilder)
pruef(any("Profile geprueft" in z for z in w.log.zeilen),
      f"kein Bericht ueber die Profile: {w.log.zeilen}")
pruef(not any("WARNUNG" in z for z in w.log.zeilen),
      f"Warnung ohne Grund: {w.log.zeilen}")

print("=== 2. Gar keine Profile ===")
ordner = os.path.join(SCRATCH, "sc_leer")
bilder = bau(ordner, 6, fehlend=6)
w = ns["W"]()
try:
    w._pruefe_sidecars(bilder)
    pruef(False, "fehlende Profile werden nicht bemerkt")
except RuntimeError as e:
    t = str(e)
    pruef(".pp3" in t, f"die gesuchte Endung fehlt in der Meldung: {t}")
    pruef("ohne Entflackerung" in t or "Entflackerung" in t,
          f"die Folge wird nicht benannt: {t}")
    pruef("RawTherapee" in t, f"die Engine wird nicht benannt: {t}")

print("=== 3. Ordner wurde mit einer anderen Engine vorbereitet ===")
# genau der Fall: Pass 1 lief mit Darktable, eingestellt ist RawTherapee
ordner = os.path.join(SCRATCH, "sc_fremd")
bilder = bau(ordner, 6, endung=".xmp")
pe.set_engine('rt')
w = ns["W"]()
try:
    w._pruefe_sidecars(bilder)
    pruef(False, "der Engine-Wechsel wird nicht bemerkt")
except RuntimeError as e:
    t = str(e)
    pruef("Darktable" in t, f"die fremde Engine wird nicht genannt: {t}")
    pruef("RawTherapee" in t, f"die eingestellte Engine fehlt: {t}")
    pruef("Pass 1" in t, f"es wird nicht gesagt, was zu tun ist: {t}")
# Umgekehrt: ART-Profile, eingestellt RawTherapee
ordner = os.path.join(SCRATCH, "sc_fremd2")
bilder = bau(ordner, 6, endung=".arp")
w = ns["W"]()
try:
    w._pruefe_sidecars(bilder)
    pruef(False, "ART-Profile unter RawTherapee werden nicht bemerkt")
except RuntimeError as e:
    pruef("ART" in str(e), f"ART wird nicht genannt: {e}")

print("=== 4. Einzelne Profile fehlen ===")
ordner = os.path.join(SCRATCH, "sc_teil")
bilder = bau(ordner, 10, fehlend=3)
w = ns["W"]()
try:
    w._pruefe_sidecars(bilder)
    pruef(False, "teilweise fehlende Profile werden durchgelassen")
except RuntimeError as e:
    t = str(e)
    pruef("3 von 10" in t, f"die Zahl stimmt nicht: {t}")
    pruef("IMG_007.NEF" in t, f"kein Beispielname: {t}")

print("=== 5. Profile ohne Entflackerung ===")
ordner = os.path.join(SCRATCH, "sc_konstant")
bilder = bau(ordner, 8, ev=0.0)
w = ns["W"]()
w._pruefe_sidecars(bilder)
zeilen = " ".join(w.log.zeilen)
pruef("WARNUNG" in zeilen, f"konstante Korrektur wird nicht gemeldet: {zeilen}")
pruef("flackern" in zeilen.lower(), f"die Folge wird nicht benannt: {zeilen}")
pruef("Pass 1" in zeilen, f"die Ursache wird nicht genannt: {zeilen}")
# Auch bei einem konstanten Wert ungleich null
bilder = bau(os.path.join(SCRATCH, "sc_konst2"), 8, ev=-0.42)
w = ns["W"]()
w._pruefe_sidecars(bilder)
pruef(any("WARNUNG" in z for z in w.log.zeilen),
      "konstant -0.42 ist genauso unbrauchbar wie konstant 0")
# Eine echte Spanne darf nicht warnen
bilder = bau(os.path.join(SCRATCH, "sc_var"), 8)
w = ns["W"]()
w._pruefe_sidecars(bilder)
pruef(not any("WARNUNG" in z for z in w.log.zeilen), "Fehlalarm bei echter Spanne")

print("=== 6. Darktable bleibt aussen vor ===")
pe.set_engine('dt')
bilder = bau(os.path.join(SCRATCH, "sc_dt"), 4, fehlend=4)
w = ns["W"]()
w._pruefe_sidecars(bilder)   # darf nicht werfen
pruef(w.log.zeilen == [], f"Darktable wird geprueft, obwohl anders gebaut: {w.log.zeilen}")
pe.set_engine('rt')

print("=== 7. Der Aufruf der Engine ===")
rw = schnitt(src, "    def _render_with_engine", "    def _measure_and_correct")
pruef('"-S"' in rw, "es wird weiterhin mit -s aufgerufen")
# Im Befehl selbst darf kein -s mehr stehen (im Kommentar daneben schon)
befehl = rw[rw.index("grund = ["):rw.index("cmds = [")]
pruef('"-s"' not in befehl, f"das alte -s steht noch im Befehl: {befehl}")
pruef("self._pruefe_sidecars(files)" in rw, "die Pruefung wird nicht aufgerufen")
pruef(rw.index("_run_darktable_cli") < rw.index("_pruefe_sidecars"),
      "Darktable muss vor der Pruefung abgefangen werden")
pruef(rw.index("_pruefe_sidecars") < rw.index("prozess_anzahl"),
      "erst pruefen, dann Prozesse starten")

print("=== 8. Ausgabe der Engine wird immer mitgelesen ===")
rc = schnitt(src, "    def _run_engine_cli", "    def _run_darktable_cli")
pruef("if self._diag():" not in rc.split("for cmd in cmds:")[1].split("logs.append")[0],
      "die Ausgabe wird nur im Diagnose-Modus mitgelesen")
pruef("_engine_warnungen_melden" in rc, "die Ausgabe wird nicht ausgewertet")
wm = schnitt(src, "    def _engine_warnungen_melden", "    def _write_engine_log")
# Das blosse Wort "sidecar" darf KEIN Suchbegriff sein: die Engines
# schreiben bei jedem geladenen Profil "Merging sidecar procparams."
pruef('schluessel = ("not found", "error", "warning", "cannot", "failed")' in wm,
      "die Suchbegriffe treffen wieder die Erfolgsmeldung")
pruef("sidecar file requested but not found" in wm and "no sidecar procparams" in wm,
      "nach den echten Fehlermeldungen wird nicht gesucht")
pruef("nicht laden" in wm, "die Folge wird dem Nutzer nicht gesagt")
# Nachstellen: Erfolgsmeldungen duerfen keinen Alarm ausloesen
import tempfile as _tf
exec("class _S:\n    def __init__(self): self.z = []\n    def emit(self, t): self.z.append(t)\n"
     "class _W:\n    def __init__(self): self.log = _S(); self.p = {}\n"
     "    def _t(self, de, en): return de\n    def _l(self, label): return label\n" + wm, ns)
def _log(text):
    f = _tf.TemporaryFile(); f.write(text.encode()); return f
w = ns["_W"](); w._engine_warnungen_melden([_log("  Merging sidecar procparams.\n" * 50)], "Test")
pruef(w.log.z == [], f"Fehlalarm bei der Erfolgsmeldung: {w.log.z[:2]}")
w = ns["_W"]()
w._engine_warnungen_melden([_log("Warning: sidecar file requested but not found for: A.NEF.pp3\n"
                                 "Error: no sidecar procparams found for: A.NEF\n"
                                 "  Merging sidecar procparams.\n")], "Test")
pruef(any("ACHTUNG: 1 Profil" in z for z in w.log.z), f"ein fehlendes Profil wird nicht gezaehlt: {w.log.z}")
pruef("gezaehlt" in wm, "gleiche Meldungen wuerden hundertfach erscheinen")
# Die Protokolldatei bleibt dem Diagnose-Modus vorbehalten
wl = schnitt(src, "    def _write_engine_log", "    def _run_engine_cli")
pruef("if not self._diag()" in wl,
      "im Normalbetrieb entstuende jetzt eine Protokolldatei")

print("=== 9. Zusammenspiel mit den Schnelleinstellungen ===")
# Die eigentliche Frage des Nutzers: ueberleben die Deflicker-Werte das?
ordner = os.path.join(SCRATCH, "sc_quick")
bilder = bau(ordner, 5)
pe.set_engine('rt')
vorher = [float(pe.read_arp_dict(pe.sidecar(f))['Exposure']['Compensation'])
          for f in bilder]
# Schnelleinstellungen auf Bild 2, wie der Dialog es tut
prof = pe.read_arp_dict(pe.sidecar(bilder[2]))
pe.quick_apply(prof, {'brightness': 20, 'saturation': 15})
pe.hl_schreiben(prof, "Coloropp")
pe.write_arp_dict(pe.sidecar(bilder[2]), prof)
nachher = [float(pe.read_arp_dict(pe.sidecar(f))['Exposure']['Compensation'])
           for f in bilder]
pruef(vorher == nachher,
      f"die Schnelleinstellungen haben die Deflicker-Werte veraendert:\\n"
      f"  vorher  {vorher}\\n  nachher {nachher}")
w = ns["W"]()
w._pruefe_sidecars(bilder)
pruef(not any("WARNUNG" in z for z in w.log.zeilen),
      "nach den Schnelleinstellungen schlaegt die Pruefung an")
neu_prof = pe.read_arp_dict(pe.sidecar(bilder[2]))
pruef(neu_prof['Exposure']['Brightness'] == '20', "Helligkeit nicht gespeichert")
pruef(pe.hl_lesen(neu_prof) == "Coloropp", "Lichter nicht gespeichert")
pruef(neu_prof['Exposure']['Compensation'] == f"{vorher[2]:.3f}",
      "die Belichtung des Deflickers wurde ueberschrieben")

print("=== 10. Engine-Erkennung ===")
# Der eigentliche Ausloeser: Purelapse schreibt fuer jedes markierte
# Keyframe eine .xmp mit der Bewertung. Die darf nicht als
# Darktable-Sidecar gelten.
erk = os.path.join(SCRATCH, "sc_erkennung")
shutil.rmtree(erk, ignore_errors=True)
os.makedirs(erk)
bewertung = ('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
             '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n<rdf:RDF '
             'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
             '<rdf:Description rdf:about="" '
             'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="5">\n'
             '</rdf:Description>\n</rdf:RDF>\n</x:xmpmeta>\n')
for i in range(3):
    io.open(os.path.join(erk, f"IMG_{i}.NEF"), "w").write("x")
    io.open(os.path.join(erk, f"IMG_{i}.NEF.xmp"), "w").write(bewertung)
pruef(pe.detect_engine(erk) is None,
      f"Purelapses eigene Bewertungsdateien werden fuer Darktable gehalten: "
      f"{pe.detect_engine(erk)}")
pruef(all(pe.ist_reine_bewertung(os.path.join(erk, f"IMG_{i}.NEF.xmp"))
          for i in range(3)), "Bewertungsdatei nicht als solche erkannt")
# Eine echte Darktable-Sidecar dagegen schon
echt = os.path.join(SCRATCH, "sc_dt_echt")
shutil.rmtree(echt, ignore_errors=True)
os.makedirs(echt)
io.open(os.path.join(echt, "A.NEF"), "w").write("x")
io.open(os.path.join(echt, "A.NEF.xmp"), "w").write(
    '<x:xmpmeta xmlns:darktable="http://darktable.sf.net/">'
    '<darktable:history_end>12</darktable:history_end></x:xmpmeta>')
pruef(pe.detect_engine(echt) == 'dt',
      f"echte Darktable-Sidecar nicht erkannt: {pe.detect_engine(echt)}")
pruef(not pe.ist_reine_bewertung(os.path.join(echt, "A.NEF.xmp")),
      "echte Sidecar faelschlich als Bewertung eingestuft")
# .pp3 wird weiterhin erkannt
pp = os.path.join(SCRATCH, "sc_pp3")
bau(pp, 3)
pruef(pe.detect_engine(pp) == 'rt', f"pp3 nicht erkannt: {pe.detect_engine(pp)}")
# Gemischt -> keine Entscheidung
io.open(os.path.join(pp, "IMG_000.NEF.arp"), "w").write("[Version]\n")
pruef(pe.detect_engine(pp) is None, "bei mehreren Engines darf nichts kommen")
# engine_key liefert den laufenden Stand, nicht eine Kopie
pe.set_engine('rt'); pruef(pe.engine_key() == 'rt', "engine_key falsch")
pe.set_engine('dt'); pruef(pe.engine_key() == 'dt', "engine_key wechselt nicht")
pe.set_engine('rt')
# In purelapse_main darf die globale ENGINE nicht mehr gelesen werden
import re, ast
treffer = [k for k in ast.walk(ast.parse(src)) if isinstance(k, ast.Name) and k.id == 'ENGINE']
pruef(len(treffer) == 0, f"ENGINE wird in main noch {len(treffer)}x gelesen")
sf = schnitt(src, "    def _set_folder", "        jpg = glob.glob")
pruef("engine_key()" in sf, "_set_folder vergleicht nicht gegen den echten Stand")
pruef("not eigene" in sf, "es wird auch umgestellt, wenn eigene Profile da sind")

print("=== 11. Struktur ===")
tree = ast.parse(src)
for kn in ast.walk(tree):
    if isinstance(kn, (ast.ClassDef, ast.Module)):
        namen = [k.name for k in kn.body
                 if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))]
        d = [n for n, c in collections.Counter(namen).items() if c > 1]
        pruef(not d, f"{getattr(kn, 'name', 'Modul')}: doppelt -> {d}")

print(f"\n{'='*52}\n{ok_n} Pruefungen bestanden, {fail_n} fehlgeschlagen")
sys.exit(1 if fail_n else 0)
