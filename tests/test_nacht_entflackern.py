# -*- coding: utf-8 -*-
"""Entflackern abschaltbar und Nacht entfernen.

1. Szenenhelligkeit: Bild und Belichtung zusammen - auch bei einer Kamera,
   die nachts laenger belichtet und deren Bilder deshalb kaum dunkler sind.
2. Nachtmaske: eine Grenze, geglaettet, ohne einzelne Ausreisser.
3. JPG ohne Entflackern: die Helligkeit bleibt; mit Nacht: die Nacht fehlt
   im Video, entflackert wird trotzdem die ganze Serie.
4. RAW ohne Entflackern: Pass 1 bereitet nur Profile vor, Keyframes behalten
   ihre eigene Einstellung, Pass 2 kommt ohne Pass 1 aus und laesst die
   Nacht gar nicht erst entwickeln. Pass 2 MIT Entflackern auf Profilen
   ohne verweigert mit klarer Meldung.
5. Oberflaeche: Schalter je Ordner gemerkt, Schrittleiste, Kacheln,
   Parameter, Grenzlinie im Diagramm."""
import os, sys, json, glob, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)
def O(name): return os.path.join(ARBEIT, name)
def meld(e): return (e.fehler or [""])[0]

print("=== 1. Szenenhelligkeit ===")
n = 120
licht = np.zeros(n)
licht[40:50] = np.linspace(0, -12, 10)          # Abend
licht[50:80] = -12.0                              # Nacht
licht[80:90] = np.linspace(-12, 0, 10)          # Morgen
def tonwert(ev_bild):
    lin = np.clip(0.18 * 2.0 ** ev_bild, 0, 1)
    s = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    return s * 255.0
# a) feste Belichtung: das Bild wird dunkel, EV bleibt
fest = pm.szenen_helligkeit(tonwert(licht), np.full(n, 12.0))
pruef(abs(fest[:40].mean()) < 0.3 and fest[60:70].mean() < -9, f"feste Belichtung: Tag {fest[:40].mean():.1f}, Nacht {fest[60:70].mean():.1f}")
# b) Belichtungsautomatik: das Bild bleibt fast gleich, die Kamera belichtet 10 Blenden laenger
ausgleich = np.clip(-licht, 0, 10)
auto_bild = tonwert(licht + ausgleich)
auto_ev = 12.0 - ausgleich
s_auto = pm.szenen_helligkeit(auto_bild, auto_ev)
pruef(s_auto[60:70].mean() < -9, f"Automatik: die Nacht muss trotzdem dunkel messen ({s_auto[60:70].mean():.1f})")
nur_bild = pm.szenen_helligkeit(auto_bild, [float('nan')] * n)
pruef(nur_bild[60:70].mean() > s_auto[60:70].mean() + 5,
      "ohne EXIF misst nur das Bild - das ist hier zu hell, also muss EXIF zaehlen")
luecken = auto_ev.copy(); luecken[55:58] = np.nan
s_l = pm.szenen_helligkeit(auto_bild, luecken)
pruef(np.all(np.isfinite(s_l)) and abs(s_l[56] - s_auto[56]) < 0.5, "fehlende EXIF-Werte werden aus den Nachbarn ergaenzt")
pruef(pm.szenen_helligkeit([], []).size == 0, "leere Serie")

print("=== 2. Nachtmaske ===")
m = pm.nacht_maske(fest, -7.0)
strecken = pm.nacht_strecken(m)
pruef(len(strecken) == 1, f"genau eine Nachtstrecke erwartet: {strecken}")
a, b = strecken[0]
pruef(42 <= a <= 48 and 82 <= b <= 88, f"Nacht von {a} bis {b}")
pruef(not m[:40].any() and not m[90:].any(), "Tag faellt weg")
# Ausreisser: Scheinwerfer in der Nacht, Wolke am Tag, Zappeln an der Grenze
stoer = fest.copy()
stoer[65:67] = 0.0          # zwei helle Nachtbilder
stoer[10:12] = -11.0        # zwei dunkle Tagbilder
rng = np.random.default_rng(3)
stoer[44:48] = -7.0 + rng.normal(0, 0.4, 4)
m2 = pm.nacht_maske(stoer, -7.0)
pruef(len(pm.nacht_strecken(m2)) == 1, f"Ausreisser zerstueckeln die Nacht: {pm.nacht_strecken(m2)}")
pruef(m2[65] and m2[66] and not m2[10] and not m2[11], "Inseln gehen nicht in ihrer Umgebung auf")
pruef(not pm.nacht_maske(fest, -14.0).any(), "Grenze unter allem: nichts faellt weg")
pruef(pm.nacht_maske(fest, None).sum() == 0, "ohne Grenze faellt nichts weg")
alles = pm.nacht_maske(np.full(20, -12.0), -7.0)
pruef(alles.all(), "eine Serie ganz aus Nacht bleibt Nacht")
pruef(pm.datei_stamm("/a/b/IMG_0001.NEF") == "IMG_0001" and pm.datei_stamm("x.y.jpg") == "x.y", "Dateistamm")
pruef(pm.ohne_nacht(["/a/IMG_1.NEF", "/a/IMG_2.NEF"], {"IMG_2"}) == ["/a/IMG_1.NEF"], "ohne_nacht")

print("=== 3. JPG ===")
oj = O("nacht_jpg"); dj, _ = szene(oj, n=60, art="jpg", flackern=0.12, stufen=False, seed=11)
nacht = {pm.datei_stamm(f) for f in dj[20:36]}
e = lauf(parameter(oj, dj, entflackern=False))
pruef(e.ok(), f"JPG ohne Entflackern: {meld(e)[:120]}")
v = videos(oj)
roh_fl = flackern([helligkeit_ev(cv2.imread(f)) for f in dj])
fl_aus, n_aus = video_flackern(v[-1]) if v else (float('nan'), 0)
pruef(n_aus == 60, f"Video ohne Entflackern: {n_aus} Bilder")
pruef(fl_aus > roh_fl * 0.6, f"ohne Entflackern muss das Flackern bleiben: {fl_aus:.3f} gegen {roh_fl:.3f}")
pruef("OHNE Entflackern" in e.text and "Lese Daten" not in " ".join(e.status),
      "ohne Entflackern wird trotzdem gemessen")
for f in glob.glob(os.path.join(oj, "Purelapse", "*.mp4")):
    os.remove(f)
shutil.rmtree(pm.zwischen_ordner(oj), ignore_errors=True)
e = lauf(parameter(oj, dj, nacht_auslassen=sorted(nacht)))
pruef(e.ok(), f"JPG mit Nacht entfernen: {meld(e)[:120]}")
v = videos(oj)
fl_an, n_an = video_flackern(v[-1]) if v else (float('nan'), 0)
pruef(n_an == 60 - len(nacht), f"Video mit Nacht entfernen: {n_an} Bilder, erwartet {60 - len(nacht)}")
pruef(fl_an < fl_aus * 0.5, f"mit Entflackern muss es ruhiger sein: {fl_an:.3f} gegen {fl_aus:.3f}")
pruef("Nacht entfernt: 16 von 60" in e.text, "die Nacht steht nicht im Protokoll")
abgelegt = sorted(os.listdir(pm.zwischen_ordner(oj)))
pruef(len(abgelegt) == 44 and not any(pm.datei_stamm(x) in nacht for x in abgelegt),
      f"abgelegte Bilder: {len(abgelegt)}")
e = lauf(parameter(oj, dj, nacht_auslassen=[pm.datei_stamm(f) for f in dj[1:]]))
pruef(not e.ok() and "kein Video" in meld(e), f"alles Nacht: {meld(e)[:100]}")

print("=== 4. RAW ===")
pe.set_engine('rt')
orr = O("nacht_raw"); dr, _ = szene(orr, n=52, seed=6)
# Erst ein normaler Pass 1, dann ein Keyframe mit eigener Belichtung
e = lauf(parameter(orr, dr, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI))
pruef(e.ok(), f"Pass 1: {meld(e)[:100]}")
pruef(pm.modus_lesen(orr) is True, "Pass 1 mit Entflackern ist nicht vermerkt")
basis = pm.load_base_ev(orr)
kf = dr[20]
d = pe.read_arp_dict(pe.sidecar(kf))
d.setdefault('General', {})['Rank'] = '5'
eigene = 0.4
d['Exposure']['Compensation'] = f"{basis[os.path.basename(kf)] + eigene:.3f}"
pe.write_arp_dict(pe.sidecar(kf), d)
open(pm.pl_datei(orr, pm.CALIB_DB, anlegen=True), "w").write(json.dumps({os.path.basename(dr[3]): 0.2}))
e = lauf(parameter(orr, dr, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI, entflackern=False))
pruef(e.ok() and "OHNE Entflackern" in e.text, f"Pass 1 ohne: {meld(e)[:100]}")
pruef(pm.modus_lesen(orr) is False, "Pass 1 ohne Entflackern ist nicht vermerkt")
comp = [float(pe.read_arp_dict(pe.sidecar(f))['Exposure']['Compensation']) for f in dr]
pruef(all(abs(c) < 1e-6 for i, c in enumerate(comp) if i != 20), f"Belichtung nicht 0: {[c for c in comp if abs(c) > 1e-6][:5]}")
pruef(abs(comp[20] - eigene) < 0.002, f"der Keyframe verliert seine eigene Belichtung: {comp[20]}")
pruef(pe.read_arp_dict(pe.sidecar(kf))['General'].get('Rank') == '5', "Keyframe-Stern verloren")
pruef(all(v == 0.0 for v in pm.load_base_ev(orr).values()), "Basiswerte nicht 0")
pruef(not os.path.exists(pm.pl_datei(orr, pm.CALIB_DB)), "alte Nachkalibrierung nicht verworfen")
pruef("analyse" not in pm.ablauf_plan(parameter(orr, dr, raw_mode='pass1', entflackern=False)), "Ablaufplan misst")
# Zweimal hintereinander: nichts aendert sich mehr
e = lauf(parameter(orr, dr, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI, entflackern=False))
pruef(e.ok() and "0 davon angepasst" in e.text, f"zweiter Lauf aendert noch etwas: {[z for z in e.log if 'angepasst' in z]}")
# Pass 2 MIT Entflackern auf Profilen ohne: klare Meldung
e = lauf(parameter(orr, dr, raw_mode='pass2', art_cli_path=RT_CLI))
pruef(not e.ok() and "ohne Entflackern" in meld(e), f"Pass 2 mit Entflackern: {meld(e)[:120]}")
# Pass 2 ohne, mit Nacht: die Nacht wird gar nicht erst entwickelt
nacht_r = sorted(pm.datei_stamm(f) for f in dr[30:40])
e = lauf(parameter(orr, dr, raw_mode='pass2', art_cli_path=RT_CLI, entflackern=False,
                   nacht_auslassen=nacht_r, calib_rounds=2))
pruef(e.ok(), f"Pass 2 ohne: {meld(e)[:150]}")
entw = sorted(os.listdir(pm.zwischen_ordner(orr)))
entw = [x for x in entw if x.lower().endswith(".jpg")]
pruef(len(entw) == 42 and not any(pm.datei_stamm(x) in nacht_r for x in entw), f"entwickelt: {len(entw)}")
runden = [z for z in e.log + e.status if "Nachkalibrierung 1" in z or "Restflackern nach" in z]
pruef(not runden, f"ohne Entflackern lief eine Nachkalibrierung oder Messung: {runden[:3]}")
v = [x for x in videos(orr)]
pruef(v and video_flackern(v[-1])[1] == 42, f"Video: {video_flackern(v[-1])[1] if v else None} Bilder")
pruef(os.path.exists(pm.pl_datei(orr, pm.RESULT_DB)) and pm.load_residuals(orr) == [],
      "Restflackern eines frueheren Laufs bleibt im Diagramm stehen")
# Pass 2 ohne Pass 1 in einem frischen Ordner: bereitet selbst vor
of = O("nacht_raw_frisch"); df, _ = szene(of, n=52, seed=8)
e = lauf(parameter(of, df, raw_mode='pass2', art_cli_path=RT_CLI, entflackern=False))
pruef(e.ok(), f"Pass 2 ohne Pass 1: {meld(e)[:150]}")
pruef(all(os.path.exists(pe.sidecar(f)) for f in df), "Profile fehlen")
# Wieder mit Entflackern: Pass 1 setzt den Vermerk zurueck
e = lauf(parameter(orr, dr, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI))
pruef(e.ok() and pm.modus_lesen(orr) is True, "Pass 1 mit Entflackern setzt den Vermerk nicht zurueck")
comp = float(pe.read_arp_dict(pe.sidecar(kf))['Exposure']['Compensation'])
neu_basis = pm.load_base_ev(orr)[os.path.basename(kf)]
pruef(abs(comp - (neu_basis + eigene)) < 0.002, f"Keyframe nach dem Zurueckschalten: {comp:.3f} statt {neu_basis + eigene:.3f}")

print("=== 5. Oberflaeche ===")
fen = pm.MainWindow()
fen.cmb_engine.setCurrentIndex(1); fen.txt_art_path.setText(RT_CLI); fen.rb_raw.setChecked(True)
fen._set_folder(of)
pruef(fen.chk_entflackern.isChecked(), "Standard muss 'Entflackern an' sein")
fen._set_folder(orr)
pruef(fen.chk_entflackern.isChecked(), "Ordner mit Entflackern: Haken fehlt")
fen._go_step('smooth')
pruef(fen._step_done('smooth'), "Pass 1 mit Entflackern gilt nicht als erledigt")
fen.chk_entflackern.setChecked(False)
pruef(not fen.box_deflicker.isEnabled() and not fen.cmb_calib.isEnabled(), "Deflicker-Regler bleiben frei")
pruef("Profile vorbereiten" in fen.step_buttons['smooth'].text(), f"Schritt heisst: {fen.step_buttons['smooth'].text()}")
pruef(not fen._step_done('smooth'), "Pass 1 lief MIT Entflackern - darf jetzt nicht erledigt sein")
pruef("ohne Entflackern" in fen.lbl_summary.text(), f"Zusammenfassung: {fen.lbl_summary.text()}")
pruef(pm.ordner_optionen(orr)['entflackern'] is False, "nicht je Ordner gemerkt")
fen._set_folder(of)
pruef(fen.chk_entflackern.isChecked(), "der Schalter wandert in den naechsten Ordner mit")
fen._set_folder(orr)
pruef(not fen.chk_entflackern.isChecked(), "beim Zurueckkehren vergessen")
p = fen._collect_params()
pruef(p and p['entflackern'] is False and p['nacht_auslassen'] == [], f"Parameter: {p and p.get('entflackern')}")
fen.chk_entflackern.setChecked(True)
pruef(pm.ordner_optionen(orr) == {'entflackern': True, 'nacht': None}, "Standard wird nicht wieder geloescht")
# Nacht: die Kurve des Ordners kennt keine Nacht - Helligkeit nachstellen
nn = len(fen.tiles)
pruef(nn == 52 and len(fen.luma_history) == 52, f"Kacheln {nn}, Kurve {len(fen.luma_history)}")
fen.luma_history[25:37] = [2.0] * 12
fen.curves['ev'] = [float('nan')] * nn
fen.chk_nacht.setChecked(True)
pruef(len(fen._nacht_staemme) == 12, f"als Nacht erkannt: {len(fen._nacht_staemme)}")
pruef(sum(1 for t in fen.tiles if t.get('draussen')) == 12, "Nachtkacheln nicht abgeblendet")
pruef("12 von 52" in fen.lbl_nacht_info.text(), f"Hinweis: {fen.lbl_nacht_info.text()}")
pruef(fen.nacht_linie is not None and fen.nacht_linie.sichtbar and abs(fen.nacht_linie.value() - pm.NACHT_STANDARD) < 1e-6,
      "Grenzlinie im Diagramm fehlt")
pruef(fen.plot_szene is not None and len(fen.plot_szene.y) == 52, "Szenenkurve fehlt")
pruef(len(fen._nacht_baender) == 1 and fen._nacht_baender[0].getRegion() == (24.5, 36.5),
      f"Nachtstreifen: {[b.getRegion() for b in fen._nacht_baender]}")
p = fen._collect_params()
pruef(p and len(p['nacht_auslassen']) == 12 and len(p['files']) == 52,
      "die Nacht reist nicht als Parameter mit (oder die Dateien fehlen fuer die Messung)")
pruef(f"Nacht entfernt (12" in fen.lbl_summary.text() or fen.step != 'render', "")
fen._go_step('render'); fen._update_summary()
pruef("Nacht entfernt (12" in fen.lbl_summary.text(), f"Zusammenfassung: {fen.lbl_summary.text()}")
pruef("40 Bilder" in fen.lbl_size_est.text(), f"Videolaenge zaehlt die Nacht mit: {fen.lbl_size_est.text()}")
# Grenze im Diagramm ziehen -> Regler
fen.nacht_linie.setPos(-3.0); fen._nacht_linie_gezogen()
pruef(fen.slider_nacht.value() == -30, f"Regler folgt der Linie nicht: {fen.slider_nacht.value()}")
fen.nacht_linie.setPos(-40.0); fen._nacht_linie_gezogen()
pruef(fen.slider_nacht.value() == int(pm.NACHT_BEREICH[0] * 10), "Linie ausserhalb des Bereichs")
pruef(pm.ordner_optionen(orr)['nacht'] == pm.NACHT_BEREICH[0], f"Grenze nicht gemerkt: {pm.ordner_optionen(orr)}")
fen.slider_nacht.setValue(-70)
fen.chk_nacht.setChecked(False)
pruef(not fen._nacht_staemme and not any(t.get('draussen') for t in fen.tiles), "ausgeschaltet bleibt etwas abgeblendet")
pruef(not fen.nacht_linie.sichtbar and not fen._nacht_baender, "ausgeschaltet bleibt die Linie stehen")
pruef(fen._collect_params()['nacht_auslassen'] == [], "ausgeschaltet reist die Nacht mit")
pruef(pm.ordner_optionen(orr)['nacht'] is None, "ausgeschaltet noch gemerkt")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
