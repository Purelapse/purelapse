# -*- coding: utf-8 -*-
"""darktable 5.x: neuere Modulversionen (exposure 7, temperature 4,
denoiseprofile 12, hazeremoval 3) lesen, schreiben und ueberblenden."""
import os, sys, shutil, struct
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
PROBEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten")
NORMAL = open(os.path.join(PROBEN, "normal.xmp"), encoding="utf-8").read()
pe.set_engine('dt')
o = os.path.join(ARBEIT, "dt5"); shutil.rmtree(o, ignore_errors=True); os.makedirs(o)

print("=== Belichtung Version 7 ===")
alt = "000000000000000031082c3f00004842000080c000000000"
v7 = struct.pack('<iffffii', 0, 0.01, 0.6, 50.0, -4.0, 1, 1).hex()
xmp7 = NORMAL.replace(f'darktable:modversion="6" darktable:params="{alt}"',
                      f'darktable:modversion="7" darktable:params="{v7}"')
pruef(xmp7 != NORMAL, "Probe nicht umgebaut")
pruef(pe._dt_decode_exposure(v7, 7)['compensate_hilite_pres'] == 1, "v7 lesen")
pruef(pe._dt_decode_exposure(v7, 6) is None, "v7 darf nicht als v6 gelten")
pruef(pe._dt_decode_exposure(alt, 7) is None, "v6 darf nicht als v7 gelten")
f = os.path.join(o, "A.NEF"); open(f, "wb").write(b"x"); open(f + ".xmp", "w").write(xmp7)
pruef(abs(float(pe.read_arp_dict_dt(f + ".xmp")['Exposure']['Compensation']) - 0.6) < 1e-3,
      "Belichtung aus darktable-5-XMP nicht gelesen")
pe.write_arp_file(f, 0.42, None)
inhalt = open(f + ".xmp", encoding="utf-8").read()
import re
m = re.search(r'darktable:operation="exposure"[^>]*darktable:modversion="(\d+)" darktable:params="([0-9a-f]+)"', inhalt)
pruef(m and m.group(1) == "7", f"Version muss 7 bleiben: {m and m.group(1)}")
w = struct.unpack('<iffffii', bytes.fromhex(m.group(2))) if m else None
pruef(w and abs(w[2] - 0.42) < 1e-5, f"Belichtung: {w}")
pruef(w and abs(w[1] - 0.01) < 1e-6 and w[5] == 1 and w[6] == 1,
      f"Schwarzwert/Ausgleich/Lichterschutz verloren: {w}")
# v6 bleibt v6
f6 = os.path.join(o, "B.NEF"); open(f6, "wb").write(b"x"); open(f6 + ".xmp", "w").write(NORMAL)
pe.write_arp_file(f6, 0.3, None)
pruef('darktable:modversion="6"' in open(f6 + ".xmp").read(), "v6 umgeschrieben")

print("=== Layouts ===")
for op, v, n in (('exposure', 7, 7), ('temperature', 4, 5), ('denoiseprofile', 12, 18),
                 ('hazeremoval', 3, 4), ('temperature', 3, 4), ('exposure', 6, 6)):
    felder = pe.dt_felder_fuer(op, v)
    pruef(felder is not None and len(felder) == n, f"{op} v{v}: {felder and len(felder)}")
pruef(pe.dt_felder_fuer('temperature', 9) is None, "unbekannte Version")

def sektion(op, v, roh):
    s = pe._dt_felder_lesen(op, str(v), roh)
    s.update({'~modversion': str(v), '~enabled': '1', '~params': roh.hex(),
              '~blendop_version': '13', '~blendop_params': 'x'})
    return s

print("=== Weissabgleich ueberblenden ===")
sek = pe.DT_SEK + "temperature#0"
a = sektion('temperature', 4, struct.pack('<ffffi', 2.0, 1.0, 1.5, 1.0, 2))
b = sektion('temperature', 4, struct.pack('<ffffi', 2.4, 1.0, 1.1, 1.0, 2))
m, harte = pe.dt_sektion_mischen(sek, a, b, 0.5)
pruef(not harte and abs(float(m['red']) - 2.2) < 1e-6 and m['preset'] == '2', f"v4 weich: {harte} {m.get('red')}")
pruef(m['~params'] == struct.pack('<ffffi', 2.2, 1.0, 1.3, 1.0, 2).hex(), "v4 gepackt")
# gemischt: Keyframe aus darktable 4 und darktable 5
c = sektion('temperature', 3, struct.pack('<ffff', 2.4, 1.0, 1.1, 1.0))
m, harte = pe.dt_sektion_mischen(sek, a, c, 0.25)
pruef(not harte and m['~modversion'] == '4' and abs(float(m['red']) - 2.1) < 1e-6,
      f"v3+v4 weich: {harte} {m.get('~modversion')} {m.get('red')}")
pruef(m['preset'] == '2', f"Anzeige vom neueren Keyframe: {m['preset']}")
m, harte = pe.dt_sektion_mischen(sek, c, a, 0.25)
pruef(not harte and m['~modversion'] == '4' and m['preset'] == '2', f"v3 naeher: {harte} {m.get('preset')}")

print("=== Belichtung ueberblenden 6 + 7 ===")
sek = pe.DT_SEK + "exposure#0"
e6 = sektion('exposure', 6, struct.pack('<iffffi', 0, 0.0, 0.2, 50.0, -4.0, 0))
e7 = sektion('exposure', 7, struct.pack('<iffffii', 0, 0.0, 0.6, 50.0, -4.0, 0, 1))
m, harte = pe.dt_sektion_mischen(sek, e6, e7, 0.5)
pruef(m['~modversion'] == '7' and len(bytes.fromhex(m['~params'])) == 28, f"{harte} {m.get('~modversion')}")

print("=== Hochstufen ===")
h = pe.dt_hochstufen('hazeremoval', sektion('hazeremoval', 1, struct.pack('<ff', 0.2, 0.2)), '3')
pruef(h and struct.unpack('<ffii', bytes.fromhex(h['~params'])) == (struct.unpack('<f', struct.pack('<f', 0.2))[0],) * 2 + (1, 0), f"{h}")
pruef(pe.dt_hochstufen('hazeremoval', h, '1') is None, "kein Herabstufen")
d = pe.dt_hochstufen('denoiseprofile', {'~modversion': '11'}, '12')
pruef(d is None, "unvollstaendige Sektion")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
