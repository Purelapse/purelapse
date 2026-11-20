# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""Darktable: kompletter Modulstapel der Keyframes wird verteilt und ueberblendet."""
import os, sys, re, shutil, struct, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
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

def desc_von(pfad):
    return ET.parse(pfad).getroot().find('.//' + R + 'Description')

def eintraege(pfad):
    d = desc_von(pfad)
    return [{k.replace(D, ''): v for k, v in li.attrib.items()}
            for li in d.find(D + 'history').find(R + 'Seq')]

def floats(hexs, n):
    return struct.unpack('<' + 'f' * n, bytes.fromhex(hexs)[:4 * n])

def mit_eintraegen(xmp, neue, rating=None):
    """Haengt rdf:li-Eintraege an und setzt history_end passend."""
    lis = re.findall(r'darktable:num="(\d+)"', xmp)
    n = max(int(x) for x in lis) + 1
    teile = []
    for op, mv, params in neue:
        teile.append(f'<rdf:li darktable:num="{n}" darktable:operation="{op}" darktable:enabled="1" '
                     f'darktable:modversion="{mv}" darktable:params="{params}" darktable:multi_name="" '
                     f'darktable:multi_name_hand_edited="0" darktable:multi_priority="0" '
                     f'darktable:blendop_version="13" darktable:blendop_params="{pe._DT_NEUTRAL_BLEND}"/>')
        n += 1
    xmp = xmp.replace('</rdf:Seq>\n   </darktable:history>', ''.join(teile) + '</rdf:Seq>\n   </darktable:history>')
    xmp = re.sub(r'darktable:history_end="\d+"', f'darktable:history_end="{n}"', xmp)
    if rating is not None:
        xmp = re.sub(r'xmp:Rating="\d"', f'xmp:Rating="{rating}"', xmp)
    return xmp

def cb_params(hue, sat):
    """colorbalancergb v5: 32 floats + 1 int; global_H (Feld 12) und saturation_global (Feld 20)."""
    werte = [0.0] * 32
    werte[12] = 1.0; werte[14] = 1.0; werte[28] = 0.1845; werte[30] = 0.1845
    werte[11] = hue; werte[10] = 0.2; werte[19] = sat
    return struct.pack('<' + 'f' * 32 + 'i', *werte, 1).hex()

def temp(r, b):
    return struct.pack('<ffff', r, 1.0, b, float('inf')).hex()

print("=== 1. Lesen der echten Keyframe-XMP ===")
o = os.path.join(ARBEIT, "dtstapel"); shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
k1 = os.path.join(o, "kf.NEF.xmp"); open(k1, "w").write(KF)
d = pe.read_arp_dict_dt(k1)
pruef(d['Exposure'].get('Compensation') == '0.700',
      f"wirksame Belichtung muss Darktables +0,7 (Eintrag 14) sein, nicht der verdeckte Purelapse-Eintrag: {d['Exposure']}")
pruef(d[pe.DT_STAPEL]['haupt'] == 'dt:exposure#0', d[pe.DT_STAPEL])
t = d.get('dt:temperature#0', {})
pruef(abs(float(t.get('red', 0)) - 0.5222) < 1e-3 and abs(float(t.get('blue', 0)) - 0.8713) < 1e-3,
      f"Weissabgleich falsch gelesen (letzter Eintrag 20 gilt): {t}")
pruef(d.get('dt:channelmixerrgb#0', {}).get('~enabled') == '0', "Farbkalibrierung ist im Keyframe aus")
pruef('dt:filmicrgb#0' in d and d['dt:filmicrgb#0'].get('white_point_source'), "Filmic nicht entschluesselt")
pruef('dt:colorin#0' in d and d['dt:colorin#0']['~params'].startswith('gz'), "gz-Parameter muessen roh erhalten bleiben")
pruef(len([s for s in d if s.startswith('dt:')]) == 11, f"Stapel hat {len([s for s in d if s.startswith('dt:')])} statt 11 Module")
n1 = os.path.join(o, "n.NEF.xmp"); open(n1, "w").write(NORMAL)
dn = pe.read_arp_dict_dt(n1)
pruef(dn['Exposure'].get('Compensation') == '0.672', dn['Exposure'])
pruef(dn[pe.DT_STAPEL]['haupt'] == 'dt:exposure#0', "eigene Instanz in frischer Datei")

print("=== 2. Nur Belichtung schreiben laesst den Verlauf stehen ===")
pe.set_exposure(d, 1.25); pe.write_arp_dict_dt(k1, d)
e = eintraege(k1)
pruef(len(e) == 21, f"Verlauf veraendert: {len(e)} Eintraege")
pruef(floats(e[14]['params'][16:24], 1)[0] == 1.25, "nicht in den wirksamen Eintrag 14 geschrieben")
pruef(floats(e[11]['params'][16:24], 1)[0] == 0.0, "verdeckter Eintrag 11 wurde angefasst")
pruef(pe.read_arp_dict_dt(k1)['Exposure']['Compensation'] == '1.250', "Rueckgelesen falsch")
pruef(e[14]['params'][-8:] == '01000000', "Belichtungsausgleich des Nutzers verloren")

print("=== 3. Aeltere Datei: eigene Instanz mit Prioritaet 1 ===")
alt = NORMAL.replace('darktable:multi_priority="0"', 'darktable:multi_priority="1"')
alt = mit_eintraegen(alt, [('exposure', 6, struct.pack('<iffffi', 0, 0, 0.5, 50, -4, 0).hex())])
a1 = os.path.join(o, "alt.NEF.xmp"); open(a1, "w").write(alt)
da = pe.read_arp_dict_dt(a1)
pruef(da[pe.DT_STAPEL]['haupt'] == 'dt:exposure#1' and da['Exposure']['Compensation'] == '0.672',
      f"Purelapses Instanz muss Ziel bleiben: {da[pe.DT_STAPEL]['haupt']} {da['Exposure']}")

print("=== 4. Leere History: Belichtung wird angelegt ===")
leer = re.sub(r'<rdf:li .*?/>', '', NORMAL).replace('history_end="1"', 'history_end="0"')
l1 = os.path.join(o, "leer.NEF.xmp"); open(l1, "w").write(leer)
pe._dt_write_ev(l1, 0.3)
pruef(pe.read_arp_dict_dt(l1)['Exposure'].get('Compensation') == '0.300', "nicht angelegt")

print("=== 5. Keyframe-Verteilung ueber den echten Worker ===")
o2 = os.path.join(ARBEIT, "dtvert"); shutil.rmtree(o2, ignore_errors=True); os.makedirs(o2)
n = 9
dateien = []
for i in range(n):
    f = os.path.join(o2, f"IMG_{i:03d}.NEF"); open(f, "wb").write(b"x"); dateien.append(f)
    open(f + ".xmp", "w").write(NORMAL)
import json
json.dump({os.path.basename(f): round(0.1 * i, 3) for i, f in enumerate(dateien)},
          open(os.path.join(o2, pm.DEFLICKER_DB), "w"))
# Keyframe A (Bild 1): echter Keyframe + Schaerfe + Farbbalance (Farbton 350, Saettigung 0)
ka = mit_eintraegen(KF, [('sharpen', 1, struct.pack('<fff', 2.0, 0.5, 0.5).hex()),
                         ('colorbalancergb', 5, cb_params(350.0, 0.0))], rating=5)
# Keyframe B (Bild 7): anderer Weissabgleich, mehr Schaerfe, Farbton 10, Saettigung 0.4, Farbkalibrierung an
kb = mit_eintraegen(KF, [('temperature', 3, temp(0.80, 0.60)),
                         ('sharpen', 1, struct.pack('<fff', 2.0, 1.5, 0.5).hex()),
                         ('colorbalancergb', 5, cb_params(10.0, 0.4)),
                         ('vibrance', 2, struct.pack('<f', 25.0).hex())], rating=5)
kb, n_ = re.subn(r'(darktable:num="19"\s+darktable:operation="channelmixerrgb"\s+darktable:enabled=)"0"', r'\1"1"', kb)
assert n_ == 1
open(dateien[1] + ".xmp", "w").write(ka)
open(dateien[7] + ".xmp", "w").write(kb)
pe.read_arp_dict_dt(dateien[1] + ".xmp")
params = parameter(o2, dateien, engine='dt')
w = pm.Worker(params)
logs = []; w.log.connect(logs.append)
w._prepare_keyframe_profiles(dateien)
alles = "\n".join(logs)
pruef("2 Keyframes" in alles, alles[:300])
pruef("Weissabgleich" in alles and "Schaerfen" in alles and "Farbbalance RGB" in alles,
      f"Uebersicht fehlt: {alles}")
pruef("ACHTUNG" in alles and "Farbkalibrierung" in alles and "Dynamik" in alles,
      f"Warnung fuer Ein/Aus und Modul nur in einem Keyframe fehlt: {alles}")
pruef("verschieden eingestellt und weich ueberblendet: Weissabgleich, Schaerfen, Farbbalance RGB." in alles,
      f"Liste der ueberblendeten Unterschiede: {alles}")
pruef("Entrastern" not in alles, "technische Module in der Uebersicht")
pruef("[Weissabgleich] red" not in alles and "Schaerfen]" not in alles,
      f"Zahlenwerte faelschlich als hart gemeldet: {alles}")

def stapel_von(i):
    return pe.read_arp_dict_dt(dateien[i] + ".xmp")

mitte = stapel_von(4)  # ratio 0.5
r_a, r_b = 0.52220720, 0.80
pruef(abs(float(mitte['dt:temperature#0']['red']) - (r_a + r_b) / 2) < 1e-4,
      f"Weissabgleich nicht ueberblendet: {mitte['dt:temperature#0']}")
pruef(mitte['dt:temperature#0']['various'] == 'inf', "Unendlich-Feld muss erhalten bleiben")
pruef(abs(float(mitte['dt:sharpen#0']['amount']) - 1.0) < 1e-6, f"Schaerfe: {mitte['dt:sharpen#0']['amount']}")
h = float(mitte['dt:colorbalancergb#0']['global_H'])
pruef(abs(h) < 1e-3 or abs(h - 360) < 1e-3, f"Farbton muss kurzen Weg ueber 0 gehen, nicht 180: {h}")
pruef(abs(float(mitte['dt:colorbalancergb#0']['saturation_global']) - 0.2) < 1e-6, "Saettigung")
pruef(mitte['dt:colorbalancergb#0']['saturation_formula'] == '1', "Ganzzahlfeld veraendert")
viertel = stapel_von(2)  # ratio 1/6
pruef(abs(float(viertel['dt:sharpen#0']['amount']) - (0.5 + 1.0 / 6)) < 1e-5, "Schaerfe 1/6")
h2 = float(viertel['dt:colorbalancergb#0']['global_H'])
pruef(abs(h2 - (350 + 20 / 6)) < 1e-3, f"Farbton 1/6: {h2}")
pruef('dt:vibrance#0' not in viertel and 'dt:vibrance#0' in stapel_von(5),
      "Modul nur in Keyframe B: vorn weglassen, ab der Mitte uebernehmen")
pruef(stapel_von(2)['dt:channelmixerrgb#0']['~enabled'] == '0'
      and stapel_von(5)['dt:channelmixerrgb#0']['~enabled'] == '1', "Ein/Aus vom naeheren Keyframe")
# Vor dem ersten / nach dem letzten Keyframe: Kopie
pruef(stapel_von(0)['dt:sharpen#0']['amount'] == stapel_von(1)['dt:sharpen#0']['amount'], "Bild 0 = Keyframe A")
pruef(stapel_von(8)['dt:sharpen#0']['amount'] == stapel_von(7)['dt:sharpen#0']['amount'], "Bild 8 = Keyframe B")

print("=== 6. Form der geschriebenen Dateien ===")
for i in (0, 2, 4, 6, 8):
    p = dateien[i] + ".xmp"
    de = desc_von(p); e = eintraege(p)
    pruef(de.get(D + 'auto_presets_applied') == '1', f"Bild {i}: Grundeinstellungen wuerden doppelt angewendet")
    pruef(int(de.get(D + 'history_end')) == len(e), f"Bild {i}: history_end")
    pruef([x['num'] for x in e] == [str(k) for k in range(len(e))], f"Bild {i}: Nummern")
    paare = [(x['operation'], x['multi_priority']) for x in e]
    pruef(len(paare) == len(set(paare)), f"Bild {i}: doppelte Instanz {paare}")
    pruef(de.get('{http://ns.adobe.com/xap/1.0/}Rating') == '1', f"Bild {i}: Bewertung uebernommen -> wuerde Keyframe")
    pruef(not pm.check_is_keyframe(p), f"Bild {i} ist ploetzlich Keyframe")
    pruef(de.get('{http://ns.adobe.com/xap/1.0/mm/}DerivedFrom') == '20220502_092400.NEF', "eigene Angaben verloren")
    pruef(de.get(D + 'history_current_hash') is None, "alter Hash bleibt stehen")
    pruef(de.find(D + 'masks_history') is not None, "Masken fehlen")
# Keyframes selbst unveraendert
pruef(len(eintraege(dateien[1] + ".xmp")) == 23 and len(eintraege(dateien[7] + ".xmp")) == 25,
      "Keyframe-Verlauf wurde umgeschrieben")
# Belichtung: Pass-1-Abstand bleibt erhalten
ev = [float(stapel_von(i)['Exposure']['Compensation']) for i in range(n)]
pruef(abs(ev[1] - 0.7) < 1e-6 and abs(ev[7] - 0.7) < 1e-6, f"Keyframe-Belichtung: {ev}")
pruef(all(abs(x - 0.7) < 1e-3 for x in ev[1:8]) and abs(ev[0] - 0.6) < 1e-3 and abs(ev[8] - 0.8) < 1e-3,
      f"Pass-1-Abstand + Keyframe-Aenderung: {ev}")
# Hex-Parameter einer ueberblendeten Datei entsprechen den Feldern
e4 = eintraege(dateien[4] + ".xmp")
tp = [x for x in e4 if x['operation'] == 'temperature'][0]
pruef(abs(floats(tp['params'], 1)[0] - (r_a + r_b) / 2) < 1e-4, "params-Hex passt nicht zu den Feldern")
ex = [x for x in e4 if x['operation'] == 'exposure']
pruef(len(ex) == 1 and ex[0]['multi_priority'] == '0', f"genau eine Belichtungsinstanz: {ex}")

print("=== 7. Zweiter Durchlauf und Nachregeln: nur noch Belichtung ===")
vorher = open(dateien[4] + ".xmp").read()
w._prepare_keyframe_profiles(dateien)
pruef(open(dateien[4] + ".xmp").read() == vorher, "zweiter Lauf schreibt den Stapel neu")
d4 = pe.read_arp_dict(dateien[4] + ".xmp")
pe.set_exposure(d4, 0.9); pe.write_arp_dict(dateien[4] + ".xmp", d4)
nachher = eintraege(dateien[4] + ".xmp")
pruef(len(nachher) == len(e4) and stapel_von(4)['Exposure']['Compensation'] == '0.900', "Nachregeln")

print("=== 8. Unbekanntes Layout wird nicht ueberblendet ===")
s = {'~modversion': '9', '~params': 'aa', '~enabled': '1'}
e_ = dict(s, **{'~params': 'bb'})
m, hart = pe.dt_sektion_mischen('dt:temperature#0', s, e_, 0.3)
pruef(m['~params'] == 'aa' and "Einstellungen" in hart, f"{m} {hart}")
m, hart = pe.dt_sektion_mischen('dt:temperature#0', s, e_, 0.7)
pruef(m['~params'] == 'bb', "naeherer Keyframe")
pruef(pe._dt_layout('temperature', 3, b'\0' * 12) is None, "Groessenpruefung")

print("=== 9. Hinweis im Programm ===")
src = "".join(open(os.path.join(PROJEKT, m), encoding="utf-8").read()
              for m in ("purelapse_main.py", "purelapse_texte.py"))
pruef("DT_KEYFRAME_HINWEIS['en' if self.lang == 'en' else 'de']" in src, "Hinweis nicht eingebunden")
pruef("Strg+Umschalt+C" in src and "Ctrl+Shift+C" in src, "Kopiertipp fehlt")
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
