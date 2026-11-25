# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""B5: Darktable - Hotpixel, Schnelleinstellungen, echte Vorschau."""
import os, sys, re, shutil, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
import numpy as np, cv2
import xml.etree.ElementTree as ET
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
PROBEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")
D = '{http://darktable.sf.net/}'; R = '{http://www.w3.org/1999/02/22-rdf-syntax-ns#}'
KF = open(os.path.join(PROBEN, "keyframe.xmp"), encoding="utf-8").read()
NORMAL = open(os.path.join(PROBEN, "normal.xmp"), encoding="utf-8").read()
pe.set_engine('dt')
o = os.path.join(ARBEIT, "dt_b5"); shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
def eintraege(p):
    d = ET.parse(p).getroot().find('.//' + R + 'Description')
    return d, [{k.replace(D, ''): v for k, v in li.attrib.items()} for li in d.find(D + 'history').find(R + 'Seq')]

print("=== Hotpixel ===")
f = os.path.join(o, "A.NEF"); open(f, "wb").write(b"x"); open(f + ".xmp", "w").write(NORMAL)
pe.write_arp_file(f, 0.42, None, hotpixel=True)
d, e = eintraege(f + ".xmp")
hp = [x for x in e if x['operation'] == 'hotpixels']
pruef(len(hp) == 1 and hp[0]['enabled'] == '1', f"Hotpixel-Modul fehlt: {[x['operation'] for x in e]}")
pruef(hp and struct.unpack('<ffii', bytes.fromhex(hp[0]['params'])) == (0.25, struct.unpack('<f', struct.pack('<f', 0.05))[0], 0, 0), "Grundwerte")
pruef(d.get(D + 'auto_presets_applied') == '0', "frische Datei: Grundeinstellungen muessen noch angewendet werden")
pruef(pe.read_arp_dict_dt(f + ".xmp")['Exposure']['Compensation'] == '0.420', "Belichtung")
# erneut: kein zweites Modul
pe.write_arp_file(f, 0.5, None, hotpixel=True)
pruef(len([x for x in eintraege(f + ".xmp")[1] if x['operation'] == 'hotpixels']) == 1, "doppelt")
# aus: Modul des Nutzers bleibt
pe.write_arp_file(f, 0.5, None, hotpixel=False)
pruef(len([x for x in eintraege(f + ".xmp")[1] if x['operation'] == 'hotpixels']) == 1, "ausschalten entfernt Modul")

print("=== Schnelleinstellungen ===")
k = os.path.join(o, "K.NEF"); open(k, "wb").write(b"x"); open(k + ".xmp", "w").write(KF)
prof = pe.read_arp_dict(k + ".xmp")
vorh, fehl = pe.quick_available(prof)
pruef(sorted(x['id'] for x in vorh) == ['brightness', 'contrast', 'highlights', 'saturation',
                                         'shadows', 'sharpen', 'vibrance'] and not fehl,
      f"{[x['id'] for x in vorh]}")
w0 = pe.quick_read(prof)
pruef(w0 == {'brightness': 0.0, 'contrast': 0.0, 'highlights': 0.0, 'shadows': 0.0,
             'vibrance': 0.0, 'saturation': 0.0, 'sharpen': 200.0}, f"Ausgangswerte: {w0}")
neu, geschrieben, _ = pe.schnell_profil(prof, {'brightness': 20, 'contrast': -10, 'saturation': 35, 'sharpen': 300})
pruef(len(geschrieben) == 4, f"{geschrieben}")
pruef(abs(float(neu['dt:colorbalancergb#0']['saturation_global']) - 0.35) < 1e-6, "Saettigung")
pruef(abs(float(neu['dt:sharpen#0']['amount']) - 0.75) < 1e-6, "Schaerfe")
pe.write_arp_dict(k + ".xmp", neu)
d, e = eintraege(k + ".xmp")
cb = [x for x in e if x['operation'] == 'colorbalancergb']
pruef(len(cb) == 1 and cb[0]['modversion'] == '5', "Farbbalance fehlt")
werte = struct.unpack('<' + 'f' * 32 + 'i', bytes.fromhex(cb[0]['params']))
pruef(abs(werte[24] - 0.2) < 1e-6 and abs(werte[31] + 0.1) < 1e-6 and abs(werte[19] - 0.35) < 1e-6 and werte[32] == 1,
      f"Farbbalance-Werte: brill {werte[24]} kontr {werte[31]} satt {werte[19]}")
pruef(d.get('{http://ns.adobe.com/xap/1.0/}Rating') == '1' or 'Rating' in str(d.attrib), "Bewertung verloren")
pruef(d.get(D + 'auto_presets_applied') == '1', "Keyframe: Grundeinstellungen sind schon drin")
w1 = pe.quick_read(pe.read_arp_dict(k + ".xmp"))
pruef(all(abs(w1[x] - y) < 1e-3 for x, y in (('brightness', 20), ('contrast', -10), ('saturation', 35), ('sharpen', 300))), f"Rueckgelesen: {w1}")
pruef(pe.read_arp_dict(k + ".xmp")['dt:temperature#0']['red'].startswith('0.522'), "Weissabgleich des Keyframes verloren")
pruef(pe.read_arp_dict(k + ".xmp")['Exposure']['Compensation'] == '0.700', "Belichtung veraendert")

print("=== Echte Vorschau ===")
fake = os.path.join(o, "darktable-cli")
open(fake, "w").write('''#!/usr/bin/env python3
import sys, numpy as np, cv2, os
a = sys.argv[1:]
xmp, out = a[1], a[2]
k = int(a[a.index("--width") + 1])
assert "--configdir" in a and os.path.exists(xmp) and "colorbalancergb" in open(xmp).read()
cv2.imwrite(out, np.full((k * 2 // 3, k, 3), 128, np.uint8))
''')
os.chmod(fake, 0o755)
fv = pm.EngineVorschau(fake, k, neu, "x", kante=300)
erg = []
fv.fertig.connect(erg.append)
fv.run()
pruef(erg and erg[0]['rgb'] is not None and erg[0]['rgb'].shape == (200, 300, 3), f"Vorschau: {erg[0] if erg else None}")
cmd, ziel = pe.dt_vorschau_befehl(fake, k, neu, o, 500, configdir="/tmp/x")
pruef("--hq" in cmd and cmd[cmd.index("--width") + 1] == "500", f"{cmd}")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef("wirkt bei der \"\n                          \"Engine Darktable aktuell nicht" not in src and "Darktable derzeit ohne Wirkung" not in src, "alter Hinweis")
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
