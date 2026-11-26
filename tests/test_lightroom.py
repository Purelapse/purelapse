# -*- coding: utf-8 -*-
"""Lightroom Classic als Engine: XMP lesen/schreiben, Keyframes ueberblenden,
Pass 1, Pass 2 in zwei Schritten, Feinabgleich des Exports."""
import os, sys, shutil, time, re, glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
import numpy as np, cv2
import xml.etree.ElementTree as ET
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

CRS = "http://ns.adobe.com/camera-raw-settings/1.0/"
def lr_xmp(pfad, temp=5200, kontrast="+10", ev="+0.00", sterne=0, kurve=None, maske=False,
           digest="12345678901234567890123456789012", wb="As Shot"):
    """Eine XMP, wie Lightroom Classic sie schreibt (gekuerzt, erfundene Werte)."""
    kurve = kurve or [(0, 0), (64, 60), (192, 200), (255, 255)]
    li = "".join(f"<rdf:li>{x}, {y}</rdf:li>" for x, y in kurve)
    m = ("<crs:MaskGroupBasedCorrections><rdf:Seq><rdf:li rdf:parseType=\"Resource\">"
         "<crs:LocalExposure2012>-0.5</crs:LocalExposure2012></rdf:li></rdf:Seq>"
         "</crs:MaskGroupBasedCorrections>") if maske else ""
    text = f'''<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 7.0">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:crs="{CRS}"
   xmp:Rating="{sterne}"
   crs:Version="15.0"
   crs:ProcessVersion="11.0"
   crs:WhiteBalance="{wb}"
   crs:Temperature="{temp}"
   crs:Tint="+8"
   crs:Exposure2012="{ev}"
   crs:Contrast2012="{kontrast}"
   crs:Highlights2012="-20"
   crs:Shadows2012="+15"
   crs:Vibrance="+5"
   crs:CameraProfile="Kamera Standard"
   crs:CameraProfileDigest="{digest}"
   crs:HasSettings="True">
   <dc:subject><rdf:Bag><rdf:li>Zeitraffer</rdf:li></rdf:Bag></dc:subject>
   <crs:ToneCurvePV2012><rdf:Seq>{li}</rdf:Seq></crs:ToneCurvePV2012>{m}
   <crs:Look><rdf:Description crs:Name="Landschaft" crs:Amount="1" crs:UUID="ABC123">
    <crs:Parameters><rdf:Description crs:Version="14.0" crs:ProcessVersion="6.7"
      crs:Exposure2012="+9.00" crs:ConvertToGrayscale="False"/></crs:Parameters>
   </rdf:Description></crs:Look>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
'''
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(text)

def attr(pfad, name):
    for d in ET.parse(pfad).getroot().iter('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description'):
        if '{' + CRS + '}' + name in d.attrib:
            return d.attrib['{' + CRS + '}' + name]
    return None

o = os.path.join(ARBEIT, "lightroom")
pe.set_engine('lr')

print("=== Begleitdatei, Erkennen ===")
shutil.rmtree(o, ignore_errors=True); os.makedirs(o)
pruef(pe.sidecar(os.path.join(o, "IMG_0001.NEF")) == os.path.join(o, "IMG_0001.xmp"), "Name")
lr_xmp(os.path.join(o, "IMG_0001.xmp"))
pruef(pe.xmp_herkunft(os.path.join(o, "IMG_0001.xmp")) == 'lr', "Herkunft lr")
pruef(pe.detect_engine(o) == 'lr', f"Erkennung: {pe.detect_engine(o)}")
pe.bewertung_schreiben(os.path.join(o, "IMG_0002.NEF.xmp"), 5)
pruef(pe.detect_engine(o) == 'lr', "Sternedatei stoert die Erkennung")
pruef(pe.lr_sidecar_bereit(os.path.join(o, "IMG_0002.NEF.xmp"))[0] is False, "Sternedatei ist keine LR-XMP")
pruef(pe.lr_sidecar_bereit(os.path.join(o, "fehlt.xmp")) == (False, "fehlt"), "fehlt")
pruef(pe.lr_sidecar_bereit(os.path.join(o, "IMG_0001.xmp")) == (True, ""), "bereit")

print("=== Lesen und Schreiben ===")
f = os.path.join(o, "IMG_0001.xmp")
lr_xmp(f, ev="+0.25", sterne=5)
d = pe.read_arp_dict(f)
pruef(d['Exposure']['Compensation'] == "0.250", f"Belichtung: {d['Exposure']}")
pruef(d['crs']['Temperature'] == "5200" and 'Exposure2012' not in d['crs'], "crs")
pruef('ToneCurvePV2012' in d['crs~elemente'] and 'Look' in d['crs~elemente'], "Kurve/Look")
pruef(d['crs']['ProcessVersion'] == "11.0" and 'Name' not in d['crs'] and 'Amount' not in d['crs'],
      f"Werte aus dem Look ins Bild gerutscht: {d['crs'].get('ProcessVersion')}")
pruef(pe.profile_is_complete(d), "vollstaendig")
pruef(pe.check_is_keyframe(f), "Keyframe ueber xmp:Rating")
pe.write_arp_file(os.path.join(o, "IMG_0001.NEF"), -0.4321)
roh = open(f, encoding="utf-8").read()
pruef(attr(f, 'Exposure2012') == "-0.432", f"Exposure2012: {attr(f, 'Exposure2012')}")
pruef(attr(f, 'Contrast2012') == "+10" and attr(f, 'CameraProfileDigest') == "12345678901234567890123456789012", "Rest unveraendert")
pruef('xmp:Rating="5"' in roh and "<rdf:li>Zeitraffer</rdf:li>" in roh, "Bewertung/Stichwort verloren")
pruef("ns0:" not in roh and "crs:Temperature" in roh and not roh.startswith("<?xml"), f"Kuerzel/Kopf: {roh[:80]}")
pruef(pe.check_is_keyframe(f), "nach dem Schreiben noch Keyframe")
pruef('crs:Exposure2012="+9.00"' in roh and 'crs:ProcessVersion="6.7"' in roh, "Look-Parameter veraendert")
pe.write_arp_file(os.path.join(o, "IMG_0001.NEF"), 0.5)
pruef(attr(f, 'Exposure2012') == "+0.500", "positiv mit Vorzeichen")

print("=== Ueberblenden ===")
a_ = os.path.join(o, "A.xmp"); b_ = os.path.join(o, "B.xmp")
lr_xmp(a_, temp=5000, kontrast="+10", kurve=[(0, 0), (64, 60), (255, 255)], maske=True)
lr_xmp(b_, temp=6000, kontrast="+30", kurve=[(0, 0), (64, 80), (255, 255)],
       digest="99999999999999999999999999999999")
A, B = pe.strip_rank(pe.read_arp_dict(a_)), pe.strip_rank(pe.read_arp_dict(b_))
m = pe.interpolate_arp_dicts(A, B, 0.25)
pruef(m['crs']['Temperature'] == "5250" and m['crs']['WhiteBalance'] == "Custom", f"WB: {m['crs'].get('Temperature')} {m['crs'].get('WhiteBalance')}")
pruef(m['crs']['Contrast2012'] == "+15", f"Kontrast: {m['crs']['Contrast2012']}")
pruef(m['crs']['CameraProfileDigest'] == "12345678901234567890123456789012", "Pruefsumme darf nicht gemischt werden")
pruef("64, 65" in m['crs~elemente']['ToneCurvePV2012'], f"Kurve: {m['crs~elemente']['ToneCurvePV2012']}")
pruef('MaskGroupBasedCorrections' in m['crs~elemente'], "Maske vom naeheren Keyframe")
m2 = pe.interpolate_arp_dicts(A, B, 0.75)
pruef('MaskGroupBasedCorrections' not in m2['crs~elemente'], "Maske nur bis zur Mitte")
harte = pe.nicht_ueberblendbar(A, B)
pruef(('crs~elemente', 'MaskGroupBasedCorrections') in harte and ('crs', 'CameraProfileDigest') in harte
      and not any(k == 'Temperature' or k == 'WhiteBalance' for _s, k in harte), f"harte: {harte}")
z = os.path.join(o, "Z.xmp"); lr_xmp(z, sterne=0)
pe.set_exposure(m, 0.1)
pe.write_arp_dict(z, m)
d = pe.read_arp_dict(z)
pruef(d['crs']['Temperature'] == "5250" and 'MaskGroupBasedCorrections' in d['crs~elemente'], "Rundlauf")
pruef('xmp:Rating="0"' in open(z).read(), "Bewertung des Ziels bleibt")

print("=== Schnelleinstellungen ===")
q = pe.read_arp_dict(a_)
vorh, fehl = pe.quick_available(q, 'lr')
pruef({x['id'] for x in vorh} >= {'contrast', 'highlights', 'shadows', 'wb_temp'} and not fehl, f"{[x['id'] for x in fehl]}")
w = pe.quick_read(q, 'lr')
pruef(w['highlights'] == 20 and w['shadows'] == 15 and w['wb_temp'] == 5000, f"lesen: {w}")
pe.quick_apply(q, {'highlights': 35, 'wb_temp': 4800, 'sharpen': 200}, 'lr')
pruef(q['crs']['Highlights2012'] == "-35" and q['crs']['Temperature'] == "4800"
      and q['crs']['WhiteBalance'] == "Custom" and q['crs']['Sharpness'] == "40", f"{q['crs']}")
pruef(not pe.hl_optionen('lr'), "keine Lichter-Rekonstruktion")

print("=== Ablauf: Pass 1, Pass 2 (zwei Schritte), Feinabgleich ===")
ordner = os.path.join(ARBEIT, "lightroom_lauf")
dateien, _ = szene(ordner, n=24, flackern=0.08)
for i, nef in enumerate(dateien):
    lr_xmp(pe.sidecar(nef), temp=5000 if i < 12 else 5000, sterne=5 if i in (0, 23) else 0)
lr_xmp(pe.sidecar(dateien[23]), temp=6000, kontrast="+30", sterne=5)
par = dict(engine='lr', art_cli_path='')
e = lauf(parameter(ordner, dateien, raw_mode='pass1', **par))
pruef(e.ok(), f"Pass 1: {e.fehler}")
evs = [float(attr(pe.sidecar(f), 'Exposure2012')) for f in dateien]
pruef(np.std(evs) > 0.05, f"Pass 1 hat keine Belichtung geschrieben: {evs[:4]}")
e = lauf(parameter(ordner, dateien, raw_mode='pass2', **par))
pruef(e.ok() and "Schritt 1" in e.fertig[0] and "Lightroom_Export" in e.fertig[0], f"Pass 2/1: {e.fehler} {e.fertig}")
mitte = pe.sidecar(dateien[12])
pruef(abs(float(attr(mitte, 'Temperature')) - 5522) < 2 and attr(mitte, 'WhiteBalance') == "Custom",
      f"Mitte: {attr(mitte, 'Temperature')} {attr(mitte, 'WhiteBalance')}")
pruef('xmp:Rating="0"' in open(mitte).read(), "Zwischenbild wurde Keyframe")
pruef(not pm.videos(ordner) if hasattr(pm, 'videos') else not videos(ordner), "noch kein Video")
# "Lightroom" entwickelt: Belichtung aus der XMP, dazu kleines Restflackern
exp_dir = pl(ordner, "Lightroom_Export")
rng = np.random.default_rng(5)
def exportieren(rest=0.05):
    for f in dateien:
        lin = np.load(open(f, 'rb')).astype(np.float64) / 65535.0
        ev = float(attr(pe.sidecar(f), 'Exposure2012')) + float(rng.normal(0, rest))
        bild = np.clip(lin * 2.0 ** ev, 0, 1) ** (1 / 2.2)
        cv2.imwrite(os.path.join(exp_dir, os.path.splitext(os.path.basename(f))[0] + ".jpg"),
                    (bild[..., ::-1] * 255 + 0.5).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 98])
time.sleep(0.05)
exportieren()
roh_flackern, n = ordner_flackern(exp_dir)
e = lauf(parameter(ordner, dateien, raw_mode='pass2', **par))
pruef(e.ok() and "Feinabgleich" in e.text, f"Pass 2/2: {e.fehler}")
v = videos(ordner)
pruef(len(v) == 1, f"Video: {v}")
if v:
    vf, frames = video_flackern(v[0])
    pruef(frames == 24, f"Bilder im Video: {frames}")
    pruef(vf < roh_flackern * 0.6, f"Feinabgleich wirkt nicht: Export {roh_flackern:.4f}, Video {vf:.4f}")
# Keyframe nachtraeglich geaendert -> Export veraltet -> wieder Schritt 1
time.sleep(0.05)
lr_xmp(pe.sidecar(dateien[23]), temp=6500, kontrast="+30", sterne=5)
e = lauf(parameter(ordner, dateien, raw_mode='pass2', **par))
pruef(e.ok() and "Schritt 1" in e.fertig[0] and "aelter als ihre XMP" in e.text, f"veraltet: {e.fertig}")
# ein Bild fehlt im Export
time.sleep(0.05)
exportieren(0.0)
os.remove(os.path.join(exp_dir, "IMG_0005.jpg"))
e = lauf(parameter(ordner, dateien, raw_mode='pass2', **par))
pruef(e.fehler and "IMG_0005" in e.fehler[0], f"fehlendes Bild: {e.fehler}")
# fehlende XMP
os.remove(pe.sidecar(dateien[3]))
e = lauf(parameter(ordner, dateien, raw_mode='pass1', **par))
pruef(e.fehler and "Metadaten in Datei speichern" in e.fehler[0], f"fehlende XMP: {e.fehler}")

print("=== Oberflaeche und Texte ===")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
pruef(pm.ENGINE_REIHE[:3] == ('art', 'rt', 'dt') and pm.ENGINE_REIHE[3] == 'lr', "Reihenfolge (gespeicherte Stellen)")
pruef(pm.ablauf_plan({'format': 'raw', 'raw_mode': 'pass2', 'engine': 'lr', 'stabilize': False}) == ['messung', 'video'], "Ablaufplan")
import purelapse_texte as tx
alle = {}
for n_ in dir(tx):
    w_ = getattr(tx, n_)
    if isinstance(w_, dict):
        alle.update({k: v for k, v in w_.items() if isinstance(k, str)})
pruef(pm.LR_HINWEIS_KURZ['de'] in alle, "Hinweistext ohne Uebersetzung")
pe.set_engine('rt')
print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
