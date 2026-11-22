#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Ablaufpruefung: das GANZE Programm, echte Arbeitsgaenge.

Echt sind purelapse_main, purelapse_engines, NumPy, SciPy, OpenCV und
FFmpeg. Nachgebaut sind Qt (ohne Bildschirm), rawpy, exifread, pyqtgraph
und die Engine - siehe ../pruefstand.

Jede Situation laeuft einmal. Gemessen wird am Ergebnis: am Flackern der
entwickelten Bilder und des fertigen Videos, nicht an Zwischenwerten.
"""
import os, sys, io, glob, threading, subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *                      # noqa: F401,F403
from PyQt5 import _basis

ok_n = fail_n = 0
def pruef(b, text):
    global ok_n, fail_n
    if b: ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")
def meld(e): return (e.fehler[0] if e.fehler else "")
def O(name): return os.path.join(ARBEIT, name)
N = 52

print("=== A. JPG: flackernde Sequenz -> Video ===")
oj = O("t_jpg"); dj, _ = szene(oj, n=N, art="jpg")
roh = flackern([helligkeit_ev(cv2.imread(f)) for f in dj])
e = lauf(parameter(oj, dj))
pruef(e.ok(), f"JPG-Lauf scheitert: {meld(e)[:120]}")
v = videos(oj)
pruef(len(v) == 1, f"nicht genau ein Video: {v}")
fl, n = video_flackern(v[0]) if v else (9, 0)
pruef(n == N, f"Video hat {n} statt {N} Bilder")
pruef(roh > 0.05, f"das Rohmaterial flackert gar nicht ({roh:.3f})")
pruef(fl < 0.012, f"Video flackert noch: {fl:.4f} EV (roh {roh:.4f})")
print(f"   {roh:.4f} -> {fl:.4f} EV")

print("=== B. RAW mit RawTherapee: Pass 1, Pass 2 ===")
ob = O("t_raw"); db, _ = szene(ob, n=N)
pe.set_engine('rt')
e1 = lauf(parameter(ob, db, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI))
pruef(e1.ok(), f"Pass 1 scheitert: {meld(e1)[:120]}")
pruef(len(glob.glob(ob + "/*.pp3")) == N, "Pass 1 schreibt nicht fuer jedes Bild ein Profil")
pruef(not videos(ob), "Pass 1 darf noch kein Video bauen")
pruef(e1.clip, "Pass 1 meldet die Lichter nicht")
basis = [float(pe.read_arp_dict(pe.sidecar(f))['Exposure']['Compensation']) for f in db]
pruef(max(basis) - min(basis) > 0.2, "Pass 1 schreibt keine Korrektur")
erst = pe.read_arp_dict(pe.sidecar(db[0]))
pruef(list(erst.keys())[0] == 'Version', "[Version] nicht an erster Stelle")
e2 = lauf(parameter(ob, db, raw_mode='pass2', art_cli_path=RT_CLI))
pruef(e2.ok(), f"Pass 2 scheitert: {meld(e2)[:120]}")
fl, n = ordner_flackern(os.path.join(ob, "Purelapse", "Deflickered_JPG"))
pruef(n == N and fl < 0.005, f"entwickelte Bilder: {n} Stueck, Flackern {fl:.4f}")
flv, nv = video_flackern(videos(ob)[0])
pruef(nv == N and flv < 0.005, f"Video: {nv} Bilder, Flackern {flv:.4f}")
print(f"   Bilder {fl:.4f} EV, Video {flv:.4f} EV")
pruef(not any("ACHTUNG" in z for z in e2.log),
      "Warnung bei einem fehlerfreien Lauf: " + str([z for z in e2.log if 'ACHTUNG' in z][:1]))
pruef(any("Profile geprueft" in z for z in e2.log), "die Profilpruefung berichtet nicht")
pruef(sum("Profile geprueft" in z for z in e2.log) == 1, "die Profilpruefung berichtet mehrfach")
pruef(any('"-S"' in z or " -S " in z for z in e2.log), "die Engine wird nicht mit -S aufgerufen")
reste = sorted(x for x in os.listdir(ob) if x.startswith("purelapse") and x.endswith((".csv", ".log")))
pruef(not reste, f"ohne Diagnose-Modus entstehen Protokolldateien: {reste}")

print("=== C. Keyframes mit Schnelleinstellungen ===")
for i, hell in ((10, 0), (40, 30)):
    d = pe.read_arp_dict(pe.sidecar(db[i]))
    d.setdefault('General', {})['Rank'] = '5'
    pe.quick_apply(d, {'saturation': 20, 'brightness': hell})
    pe.hl_schreiben(d, "Coloropp")
    pe.write_arp_dict(pe.sidecar(db[i]), d)
    io.open(db[i] + ".xmp", "w").write('<x xmp:Rating="5"></x>')
pruef(pe.detect_engine(ob) == 'rt', f"Bewertungsdateien verwirren die Erkennung: {pe.detect_engine(ob)}")
e = lauf(parameter(ob, db, raw_mode='pass2', art_cli_path=RT_CLI))
pruef(e.ok(), f"Pass 2 mit Keyframes scheitert: {meld(e)[:120]}")
prof = [pe.read_arp_dict(pe.sidecar(f)) for f in db]
pruef(all(p['Exposure'].get('Saturation') == '20' for p in prof), "Saettigung nicht verteilt")
hell = [float(prof[i]['Exposure']['Brightness']) for i in (0, 10, 25, 40, N - 1)]
pruef(hell[0] == 0 and hell[1] == 0 and 10 < hell[2] < 20 and hell[3] == 30 and hell[4] == 30,
      f"Helligkeit nicht weich uebergeblendet: {hell}")
pruef(all(pe.hl_lesen(p) == "Coloropp" for p in prof), "Lichter-Rekonstruktion nicht verteilt")
jp = sorted(glob.glob(os.path.join(ob, "Purelapse", "Deflickered_JPG", "*.jpg")))
ev = [helligkeit_ev(cv2.imread(x)) for x in jp]
pruef(ev[40] - ev[10] > 0.3, f"die Helligkeit des Keyframes kommt im Bild nicht an: {ev[40]-ev[10]:.2f}")
pruef(flackern(ev) < 0.005, f"mit Keyframes flackert es: {flackern(ev):.4f}")
pruef(float(np.abs(np.diff(ev)).max()) < 0.05, "Sprung zwischen zwei Bildern")

print("=== D. Falsche Engine / F. kein Pass 1 ===")
od = O("t_falsch"); dd, _ = szene(od, n=N)
pe.set_engine('art')
lauf(parameter(od, dd, raw_mode='pass1', make_video=False, art_cli_path=ART_CLI, engine='art'))
e = lauf(parameter(od, dd, raw_mode='pass2', art_cli_path=RT_CLI, engine='rt'))
pruef(not e.fertig and "ART" in meld(e) and "RawTherapee" in meld(e),
      f"der Engine-Wechsel wird nicht benannt: {meld(e)[:200]}")
pruef("unvollst" not in meld(e), "irrefuehrende Meldung 'unvollstaendig'")
pruef(not videos(od), "trotz falscher Engine entstand ein Video")
of = O("t_ohne"); df, _ = szene(of, n=N)
e = lauf(parameter(of, df, raw_mode='pass2', art_cli_path=RT_CLI, engine='rt'))
pruef(not e.fertig and "Pass 1" in meld(e), f"ohne Pass 1: {meld(e)[:160]}")

print("=== H. Ein nicht ladbares Profil, dann Reparatur ===")
oh = O("t_kaputt"); dh, _ = szene(oh, n=N)
lauf(parameter(oh, dh, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI, engine='rt'))
gut = io.open(dh[7] + ".pp3", encoding="utf-8").read()
io.open(dh[7] + ".pp3", "w", encoding="utf-8").write(gut.replace("Green=0;1000;0;", "Green=0;999.5;0;"))
e = lauf(parameter(oh, dh, raw_mode='pass2', art_cli_path=RT_CLI, engine='rt'))
pruef(not e.fertig, "ein Video mit fehlendem Bild wird als fertig gemeldet")
pruef("IMG_0007" in meld(e), f"das betroffene Bild wird nicht genannt: {meld(e)[:160]}")
pruef(not videos(oh), "es entstand ein Video mit einem fehlenden Bild")
pruef(any("nicht laden" in z for z in e.log), "der Grund steht nicht im Protokoll")
io.open(dh[7] + ".pp3", "w", encoding="utf-8").write(gut)
e = lauf(parameter(oh, dh, raw_mode='pass2', art_cli_path=RT_CLI, engine='rt'))
pruef(e.ok(), f"nach der Reparatur: {meld(e)[:120]}")
pruef(any(f"Fortsetzung: {N-1} von {N}" in z for z in e.log), "die fertigen Bilder werden nicht uebernommen")
pruef(any("Entwicklung: 1 Bilder" in z for z in e.log), "es wird mehr als das eine Bild neu entwickelt")

print("=== I. Fremdes Bild im Ausgabeordner ===")
cv2.imwrite(os.path.join(oh, "Purelapse", "Deflickered_JPG", "ALT_9999.jpg"), np.full((200, 300, 3), 255, np.uint8))
for x in videos(oh): os.remove(x)
e = lauf(parameter(oh, dh, raw_mode='pass2', art_cli_path=RT_CLI, engine='rt'))
fl, n = video_flackern(videos(oh)[0])
pruef(n == N, f"das fremde Bild ist im Film gelandet: {n} statt {N}")
pruef(fl < 0.005, f"Flackern mit fremdem Bild im Ordner: {fl:.4f}")

print("=== J. Abbruch, dann Fortsetzung ===")
ojb = O("t_abbruch"); djb, _ = szene(ojb, n=N)
lauf(parameter(ojb, djb, raw_mode='pass1', make_video=False, art_cli_path=RT_CLI, engine='rt'))
os.environ["FAKE_VERZOEGERUNG"] = "0.08"
e = lauf(parameter(ojb, djb, raw_mode='pass2', art_cli_path=RT_CLI, engine='rt', procs=2),
         vor_start=lambda w: threading.Timer(1.5, lambda: setattr(w, '_abort', True)).start())
os.environ["FAKE_VERZOEGERUNG"] = "0"
pruef(not e.fertig and "abgebrochen" in meld(e).lower(), f"Abbruch nicht gemeldet: {meld(e)[:80]}")
n_teil = len(glob.glob(os.path.join(ojb, "Purelapse", "Deflickered_JPG", "*.jpg")))
pruef(0 < n_teil < N, f"unbrauchbarer Abbruchzeitpunkt: {n_teil}")
def eigene_engines():
    # Nur die nachgebaute Engine dieses Pruefstands zaehlen - ein echtes
    # RawTherapee, das nebenher fuer ein offenes Purelapse arbeitet, gehoert
    # nicht zu dieser Pruefung.
    return [z for z in subprocess.run(["pgrep", "-af", "rawtherapee-cli"], capture_output=True,
                                      text=True).stdout.splitlines()
            if "pgrep" not in z and RT_CLI in z]
laufend = eigene_engines()
pruef(not laufend, f"nach dem Abbruch laufen noch Engine-Prozesse: {len(laufend)}")
e = lauf(parameter(ojb, djb, raw_mode='pass2', art_cli_path=RT_CLI, engine='rt'))
pruef(e.ok(), f"Fortsetzung scheitert: {meld(e)[:100]}")
pruef(any(f"Fortsetzung: {n_teil} von {N}" in z for z in e.log),
      f"die {n_teil} fertigen Bilder werden nicht uebernommen")
pruef(any(f"Entwicklung: {N - n_teil} Bilder" in z for z in e.log), "es wird zu viel neu entwickelt")
fl, n = ordner_flackern(os.path.join(ojb, "Purelapse", "Deflickered_JPG"))
pruef(n == N and fl < 0.005, f"nach der Fortsetzung: {n} Bilder, {fl:.4f} EV")
print(f"   {n_teil} uebernommen, {N - n_teil} neu, Flackern {fl:.4f} EV")

print("=== K. Rohfassung ===")
e = lauf(parameter(ojb, djb, mode='plain', name_suffix='_Original'))
vo = [x for x in videos(ojb) if "Original" in x]
pruef(e.ok() and len(vo) == 1, f"Rohfassung: {meld(e)[:80]}")
pruef(video_flackern(vo[0])[0] > 0.04, "die Rohfassung ist bearbeitet")

print("=== L. ART, Keyframe, drei Prozesse, Diagnose-Modus ===")
ol = O("t_art"); dl, _ = szene(ol, n=N, seed=4)
pe.set_engine('art')
e = lauf(parameter(ol, dl, raw_mode='pass1', make_video=False, art_cli_path=ART_CLI, engine='art', diag=True))
pruef(e.ok(), f"ART Pass 1: {meld(e)[:100]}")
d = pe.read_arp_dict(pe.sidecar(dl[25])); d.setdefault('General', {})['Rank'] = '5'
pruef(len(pe.quick_available(d)[0]) == 8 and pe.hl_verfuegbar(d), "ART-Profil: Regler fehlen")
pe.quick_apply(d, {'saturation': 18, 'wb_temp': 6200}); pe.hl_schreiben(d, "Color")
pe.write_arp_dict(pe.sidecar(dl[25]), d)
e = lauf(parameter(ol, dl, raw_mode='pass2', art_cli_path=ART_CLI, engine='art', procs=3, cores=8, diag=True))
pruef(e.ok(), f"ART Pass 2: {meld(e)[:100]}")
pruef(any("Prozesse parallel" in z for z in e.log), "es wird nicht parallel entwickelt")
fl, n = ordner_flackern(os.path.join(ol, "Purelapse", "Deflickered_JPG"))
pruef(n == N and fl < 0.005, f"ART: {n} Bilder, {fl:.4f} EV")
p0 = pe.read_arp_dict(pe.sidecar(dl[0]))
pruef(p0['White Balance'].get('Setting') == 'CustomTemp', f"ART-WB: {p0['White Balance'].get('Setting')}")
pruef(p0['Exposure'].get('HLRecovery') == 'Color', "ART-Lichter nicht verteilt")
dateien_diag = set(os.listdir(os.path.join(ol, "Purelapse")))
for erwartet in ("purelapse_art.log", "purelapse_pass1.csv", "purelapse_pass2.csv"):
    pruef(erwartet in dateien_diag, f"Diagnose-Modus schreibt {erwartet} nicht")
logtext = io.open(os.path.join(ol, "Purelapse", "purelapse_art.log"), encoding="utf-8").read()
pruef("Prozess 1/" in logtext and "Rueckgabewert 0" in logtext, "Engine-Protokoll unvollstaendig")

print("=== M-R. Vorschau, Vergleich, Effekte, ProRes ===")
pe.set_engine('rt')
e = lauf(parameter(ob, db, mode='preview', preview_count=5, luma_curve=[0.2] * N, raw_mode='pass2', art_cli_path=RT_CLI))
pruef(e.ok(), f"Vorschau RAW: {meld(e)[:100]}")
e = lauf(parameter(oj, dj, mode='preview', preview_count=5, luma_curve=[0.2] * N))
pruef(e.ok(), f"Vorschau JPG: {meld(e)[:100]}")
for stil in ('side', 'split'):
    out = O(f"t_vergleich_{stil}.mp4")
    e = lauf({'mode': 'compare', 'target_dir': oj, 'video_a': videos(oj)[0], 'video_b': videos(oj)[0],
              'compare_style': stil, 'compare_out': out, 'diag': False})
    pruef(e.ok() and os.path.exists(out) and os.path.getsize(out) > 1000, f"Vergleich {stil}: {meld(e)[:80]}")
for x in videos(oj): os.remove(x)
e = lauf(parameter(oj, dj, reverse_play=True, stabilize=True, denoise=True, astro_clean=True,
                   hotpixel=True, fade_sec=1.0, telemetry=True, max_blur=3))
pruef(e.ok(), f"alle Effekte (JPG): {meld(e)[:120]}")
e = lauf(parameter(ob, db, raw_mode='pass2', art_cli_path=RT_CLI, reverse_play=True, stabilize=True,
                   astro_clean=True, hotpixel=True, fade_sec=0.5, telemetry=True, max_blur=3))
pruef(e.ok(), f"alle Effekte (RAW): {meld(e)[:120]}")
e = lauf(parameter(oj, dj, codec_idx=4))
mov = [x for x in videos(oj) if x.endswith(".mov")]
pruef(e.ok() and len(mov) == 1 and os.path.getsize(mov[0]) > 10000, f"ProRes: {meld(e)[:80]}")
for szen in (1, 2, 3):
    for staerke in (0, 100):
        e = lauf(parameter(oj, dj, scene_int=szen, smooth_val=staerke, ev_val=0.5, versioning=True))
        pruef(e.ok(), f"Szenario {szen} bei Staerke {staerke}: {meld(e)[:80]}")

print("=== S. Oberflaeche: Engine bleibt stehen ===")
os_ = O("t_gui"); ds, _ = szene(os_, n=N, sonne=True, luecke=30)
f = pm.MainWindow()
f.cmb_engine.setCurrentIndex(1); f.txt_art_path.setText(RT_CLI); f.rb_raw.setChecked(True)
f._set_folder(os_)
pruef(len(f.tiles) == N, f"Galerie: {len(f.tiles)} Kacheln")
pruef(f.step == 'smooth', f"nach dem Einlesen steht der Schritt auf {f.step}")
pruef("fehlen" in f.lbl_gaps.text() and f.lbl_gaps.isVisible(), f"Luecke nicht gemeldet: {f.lbl_gaps.text()}")
pruef("ausgefressen" in f.lbl_clip.text(), f"Lichter nicht gemeldet: {f.lbl_clip.text()}")
pruef("verfärbt" in f.lbl_farbstich.text() and f.lbl_farbstich.isVisible(),
      f"Farbstich nicht gemeldet: {f.lbl_farbstich.text()}")
f.tiles[20]['chk'].setChecked(True)
pruef(os.path.exists(ds[20] + ".xmp"), "Keyframe-Markierung schreibt keine Bewertung")
f._set_folder(os_)
pruef(f.cmb_engine.currentText() == "RawTherapee" and pe.engine_key() == 'rt',
      f"die Engine wurde umgestellt: {f.cmb_engine.currentText()} / {pe.engine_key()}")
pruef(f._kf_count == 1, f"Keyframe nach dem Neueinlesen nicht erkannt: {f._kf_count}")

print("=== T. Oberflaeche: kompletter Arbeitsgang ===")
n0 = len(_basis.PROTOKOLL)
f._go_step('smooth'); f._start()
pruef("Fertig" in f.lbl_status.text(), f"Pass 1 ueber die Oberflaeche: {f.lbl_status.text()}")
pruef(f.btn_start.isEnabled() and f.cmb_engine.isEnabled(), "nach dem Lauf bleibt die Oberflaeche gesperrt")
pruef("ausgefressen" in f.lbl_clip.text() and "vorlaeufig" not in f.lbl_clip.text(),
      f"Pass 1 ersetzt die vorlaeufige Lichtermeldung nicht: {f.lbl_clip.text()}")
pruef(any("freiwillig" in x for a, t, x in _basis.PROTOKOLL[n0:]), "Abschlussmeldung von Pass 1 veraltet")
f._set_folder(os_); f.list_widget.setCurrentRow(20)
pruef(f.btn_kf_edit.isEnabled(), "'Keyframe einstellen' ist gesperrt")
def bedienen(dlg):
    pruef(len(dlg.regler) == 8 and dlg.cmb_hl is not None, "Dialog unvollstaendig")
    for kid, wert in (('saturation', 22), ('wb_temp', 6400)):
        chk, sl, lbl, d = dlg.regler[kid]; chk.setChecked(True); sl.setValue(wert)
    dlg.chk_hl.setChecked(True)
_basis.ANTWORTEN['QuickLookDialog'] = bedienen
vorher = pe.read_arp_dict(pe.sidecar(ds[20]))['Exposure']['Compensation']
f._open_quick_dialog()
d = pe.read_arp_dict(pe.sidecar(ds[20]))
pruef(d['Exposure'].get('Saturation') == '22', "Dialog: Saettigung nicht geschrieben")
pruef(d['White Balance'].get('Setting') == 'Custom' and d['White Balance'].get('Temperature') == '6400',
      f"Dialog: Weissabgleich {d['White Balance']}")
pruef(pe.hl_lesen(d) == 'Coloropp', "Dialog: Lichter nicht geschrieben")
pruef(d['Exposure']['Compensation'] == vorher, "der Dialog hat die Deflicker-Belichtung veraendert")
f.btn_kf_filter.setChecked(True)
pruef(sum(1 for t in f.tiles if not t['item'].isHidden()) == 1, "Filter zeigt nicht genau das Keyframe")
f.btn_kf_filter.setChecked(False)
pruef(all(not t['item'].isHidden() for t in f.tiles), "Filter laesst Bilder verschwunden")
f._go_step('render'); f._start()
pruef("Fertig" in f.lbl_status.text(), f"Pass 2 ueber die Oberflaeche: {f.lbl_status.text()}")
v = videos(os_)
fl, n = video_flackern(v[0]) if v else (9, 0)
# Diese Szene hat eine ausgebrannte Sonne. Die steht am Anschlag und macht
# das Flackern nicht mit; die Helligkeitsmessung wird dadurch gedaempft
# und das Ergebnis rund zehnmal ungenauer als ohne (0.006 statt 0.0005).
# Das ist kein Programmfehler, sondern der Grund fuer die Lichterwarnung -
# deshalb hier eine eigene, weitere Grenze: sichtbar wird Flackern erst
# ab etwa 0.01 bis 0.02 EV.
pruef(n == N and fl < 0.010, f"Video ueber die Oberflaeche: {n} Bilder, {fl:.4f} EV")
pruef(fl > 0.002, "mit ausgebrannter Sonne waere ein so gutes Ergebnis verdaechtig - "
                  "misst die Pruefung noch das Richtige?")
print(f"   Video ueber die Oberflaeche, mit ausgebrannter Sonne: {fl:.4f} EV")
n0 = len(_basis.PROTOKOLL)
# Ob NVIDIA wirklich da ist, haengt vom Rechner ab - hier fest: nicht verfuegbar
f._codec_probe[1] = (False, "Driver does not support the required nvenc API version")
f.cmb_codec.setCurrentIndex(1)
pruef(f.cmb_codec.currentIndex() == 0, "nicht verfuegbarer Codec bleibt gewaehlt")
pruef(any(a == 'frage' and "NVIDIA" in x for a, t, x in _basis.PROTOKOLL[n0:]), "keine Rueckfrage zum Codec")
f._apply_language('en')
pruef(f.btn_kf_edit.text() == "Edit keyframe…" and "Found" in f.lbl_count.text(), "Englisch unvollstaendig")
f._apply_language('de')
pruef(f.btn_kf_edit.text() == "Keyframe einstellen…", "zurueck auf Deutsch klappt nicht")
f._queue_add()
for x in videos(os_): os.remove(x)
f._queue_run() if hasattr(f, '_queue_run') else f.btn_q_run.click()
pruef([j.get('status') for j in f.queue][-1:] == ['done'] and videos(os_), "Warteschlange laeuft nicht durch")

print("=== U. Oberflaeche: Fehlerweg und JPG ===")
g = pm.MainWindow(); g.rb_raw.setChecked(True); g._set_folder(od)
pruef(g.cmb_engine.currentText() == "ART", f"ART-Ordner nicht erkannt: {g.cmb_engine.currentText()}")
pruef(any("umgestellt" in z and "RawTherapee" in z and "ART" in z for z in g.txt_log._zeilen),
      "die Umstellung wird nicht mit beiden Namen protokolliert")
g.cmb_engine.setCurrentIndex(1); g.txt_art_path.setText(RT_CLI); g._go_step('render')
n0 = len(_basis.PROTOKOLL); g._start()
pruef(any(a == 'fehler' and "ART" in x for a, t, x in _basis.PROTOKOLL[n0:]), "kein Fehlerdialog bei falscher Engine")
pruef(g.btn_start.isEnabled() and not g.btn_cancel.isEnabled(), "nach dem Fehler bleibt die Oberflaeche haengen")
h = pm.MainWindow(); h._set_folder(oj)
pruef(h.rb_jpg.isChecked() and h.step == 'smooth', f"JPG-Ordner: Schritt {h.step}")
pruef(not h.step_buttons['keys'].isVisible(), "bei JPG ist der Keyframe-Schritt sichtbar")

print("=== V. Farbe je Arbeitsschritt ===")
from PyQt5 import QtWidgets
app = QtWidgets.QApplication.instance()
f.rb_raw.setChecked(True)
for thema in ('dark', 'light'):
    f._apply_theme(thema)
    gesehen = []
    for key in pm.MainWindow.STEPS:
        f._go_step(key)
        t = f._farben()
        gesehen.append(t['accent'])
        pruef(t['accent'] == pm.THEMES[thema]['steps'][key], f"{thema}/{key}: falsche Farbe")
        pruef(f"QPushButton#primary {{ background: {t['accent']}" in app._style,
              f"{thema}/{key}: der Hauptknopf traegt die Schrittfarbe nicht")
        pruef(f"QFrame#stepline {{ background: {t['accent']}" in app._style, f"{thema}/{key}: Streifen")
        pruef(pm.kontrast(t['accent'], t['accent_text']) >= 4.5,
              f"{thema}/{key}: Knopfschrift zu kontrastarm ({pm.kontrast(t['accent'], t['accent_text']):.1f})")
        pruef(pm.kontrast(t['accent'], t['panel']) >= 4.0,
              f"{thema}/{key}: Farbe hebt sich nicht von der Flaeche ab")
    pruef(len(set(gesehen)) == 4, f"{thema}: Schrittfarben nicht alle verschieden")
    for a in range(4):
        for b in range(a + 1, 4):
            pruef(pm.kontrast(gesehen[a], gesehen[b]) > 1.0 and gesehen[a] != gesehen[b], "zwei Schritte gleich")
    for key in pm.MainWindow.STEPS:
        pruef(f'[schritt="{key}"]' in app._style, f"{thema}: Legende fuer {key} fehlt")
    for sem in ('warn', 'ok'):
        pruef(pm.THEMES[thema][sem] not in pm.THEMES[thema]['steps'].values(),
              f"{thema}: Schrittfarbe gleicht der Bedeutung '{sem}'")
pruef(pm.kontrast("#000000", "#ffffff") > 20.9 and abs(pm.kontrast("#777777", "#777777") - 1) < 1e-9,
      "Kontrastrechnung falsch")
pruef(pm.kontrast_text("#f2c230") == "#0d1117" and pm.kontrast_text("#6a3fc4") == "#ffffff",
      "Schriftfarbe wird nicht passend gewaehlt")

print("=== W. Sichtbereich der Bildleiste im Diagramm ===")
import pyqtgraph as _pg
ow = O("t_band"); dw, _ = szene(ow, n=60, art="jpg")
b = pm.MainWindow(); b._set_folder(ow)
band, lw = b.sicht_band, b.list_widget
sb = lw.verticalScrollBar()
pruef(band is not None and band in b.graph.elemente, "kein Streifen im Diagramm")
pruef(band.beweglich is False, "der Streifen laesst sich mit der Maus verschieben")
pruef(band.z < 0, "der Streifen liegt vor den Kurven statt dahinter")
pruef(band.sichtbar and band.getRegion() == (-0.5, 11.5),
      f"nach dem Einlesen: {band.sichtbar} {band.getRegion()}")
vorher = band.getRegion()
sb.setValue(260)
pruef(band.getRegion() == (5.5, 17.5), f"nach dem Rollen: {band.getRegion()}")
pruef(band.getRegion()[0] > vorher[0], "der Streifen wandert beim Rollen nicht nach rechts")
breite = band.getRegion()[1] - band.getRegion()[0]
sb.setValue(sb.maximum())
pruef(band.getRegion() == (47.5, 59.5), f"am Ende: {band.getRegion()}")
pruef(abs((band.getRegion()[1] - band.getRegion()[0]) - breite) < 1e-9,
      "die Breite des Streifens aendert sich beim Rollen")
sb.setValue(0)
pruef(band.getRegion() == (-0.5, 11.5), "zurueckrollen bringt den Streifen nicht zurueck")
b.tiles[7]['chk'].setChecked(True); b.tiles[41]['chk'].setChecked(True)
b.btn_kf_filter.setChecked(True)
pruef(band.getRegion() == (6.5, 41.5), f"mit Keyframe-Filter: {band.getRegion()}")
b.btn_kf_filter.setChecked(False)
pruef(band.getRegion() == (-0.5, 11.5), f"Filter aus: {band.getRegion()}")
# Klick ins Diagramm - auch ohne Punktsymbole (lange Sequenz)
b.graph.scene().sigMouseClicked.emit(_pg._Klick(47.3))
pruef(lw.currentRow() == 47, f"Klick ins Diagramm waehlt Zeile {lw.currentRow()} statt 47")
lo, hi = band.getRegion()
pruef(lo <= 47 <= hi, f"nach dem Klick liegt Bild 47 nicht im Streifen: {band.getRegion()}")
b.graph.scene().sigMouseClicked.emit(_pg._Klick(-50))
pruef(lw.currentRow() == 0, "Klick links vom ersten Bild")
b.graph.scene().sigMouseClicked.emit(_pg._Klick(5000))
pruef(lw.currentRow() == 59, "Klick rechts vom letzten Bild")
b._apply_theme('light')
pruef(band.pinsel is not None, "der Streifen bekommt keine Farbe")
leer = O("t_leer"); os.makedirs(leer, exist_ok=True)
b._set_folder(leer)
pruef(len(b.tiles) == 0 and not band.sichtbar, "im leeren Ordner bleibt der Streifen stehen")

print("=== X. Gleichzeitiges Messen: dieselben Zahlen ===")
import time as _zeit
jp = sorted(glob.glob(os.path.join(ob, "Purelapse", "Deflickered_JPG", "*.jpg")))
einzeln = [pm.measure_jpg_linear(x, None) for x in jp]
for th in (1, 2, 4, 8):
    zugleich = pm.parallel_messen(pm.measure_jpg_linear, [(x, None) for x in jp], th)
    pruef(zugleich == einzeln, f"JPG-Messung mit {th} Threads weicht vom Einzellauf ab")
roi = (0.2, 0.3, 0.5, 0.4)
pruef(pm.parallel_messen(pm.measure_jpg_linear, [(x, roi) for x in jp], 4)
      == [pm.measure_jpg_linear(x, roi) for x in jp], "mit Messbereich weicht es ab")
roh_einzeln = [pm.measure_nef(x, None) for x in db]
roh_zugleich = pm.parallel_messen(pm.measure_nef, [(x, None) for x in db], 4)
pruef(roh_zugleich == roh_einzeln, "RAW-Messung weicht vom Einzellauf ab")
pruef(pm.parallel_messen(lambda v: v * 2, [(i,) for i in range(200)], 8) == [i * 2 for i in range(200)],
      "die Reihenfolge der Ergebnisse stimmt nicht")
pruef(pm.parallel_messen(lambda v: v, [], 4) == [], "leere Liste")
gemeldet = []
pm.parallel_messen(lambda v: v, [(i,) for i in range(20)], 4, melde=lambda a, b: gemeldet.append((a, b)))
pruef(gemeldet == [(i + 1, 20) for i in range(20)], "Fortschritt nicht lueckenlos und in Reihenfolge")
# Abbruch: schnell, und nicht begonnene Messungen laufen nicht mehr los
gestartet = []
def langsam(i):
    gestartet.append(i); _zeit.sleep(0.2); return i
zaehler = {'n': 0}
def abbruch():
    zaehler['n'] += 1
    if zaehler['n'] > 3:
        raise RuntimeError("Vom Benutzer abgebrochen.")
t0 = _zeit.time()
try:
    pm.parallel_messen(langsam, [(i,) for i in range(100)], 4, pruefe_abbruch=abbruch)
    pruef(False, "der Abbruch wird nicht durchgereicht")
except RuntimeError:
    pass
pruef(_zeit.time() - t0 < 3.0, f"der Abbruch dauert {_zeit.time() - t0:.1f}s")
pruef(len(gestartet) < 30, f"nach dem Abbruch liefen noch Messungen los: {len(gestartet)}")
# Fehler in einer Messung gehen nicht verloren
def kaputt(i):
    if i == 5: raise OSError("Datei weg")
    return i
try:
    pm.parallel_messen(kaputt, [(i,) for i in range(10)], 4)
    pruef(False, "ein Lesefehler wird verschluckt")
except OSError:
    pass
# Thread-Zahl: Kerne, Obergrenze, Speicher
pruef(pm.mess_threads(16, 64.0) == 8 and pm.mess_threads(4, 64.0) == 4 and pm.mess_threads(1, 64.0) == 1,
      "Thread-Zahl folgt nicht Kernen und Obergrenze")
pruef(pm.mess_threads(16, 2.0) == 2 and pm.mess_threads(16, 0.3) == 1, "Speicher begrenzt die Threads nicht")
pruef(pm.mess_threads(0, 64.0) == 1 and pm.mess_threads(None, 64.0) == 1, "Unsinn-Eingabe")

print("=== Y. Unveraenderte Bilder werden nicht erneut vermessen ===")
w = e2.worker                         # der Worker aus Abschnitt B
w.log.gesendet.clear() if hasattr(w.log, 'gesendet') else None
aufrufe = {'n': 0}
echt = pm.jpg_bloecke
def gezaehlt(pfad, roi=None):
    aufrufe['n'] += 1
    return echt(pfad, roi)
pm.jpg_bloecke = gezaehlt
try:
    w.__dict__.pop('_mess_merker', None)
    r1 = w._measure_and_correct(jp, db, apply_correction=False)
    n1 = aufrufe['n']
    r2 = w._measure_and_correct(jp, db, apply_correction=False)
    n2 = aufrufe['n'] - n1
    # drei Bilder "neu entwickeln": Datei neu schreiben
    for x in jp[5:8]:
        bild = cv2.imread(x); _zeit.sleep(0.01); cv2.imwrite(x, bild, [cv2.IMWRITE_JPEG_QUALITY, 100])
    r3 = w._measure_and_correct(jp, db, apply_correction=False)
    n3 = aufrufe['n'] - n1 - n2
finally:
    pm.jpg_bloecke = echt
pruef(n1 == len(jp), f"erster Durchgang misst {n1} statt {len(jp)} Bilder")
pruef(n2 == 0, f"zweiter Durchgang misst {n2} unveraenderte Bilder noch einmal")
pruef(n3 == 3, f"nach drei neu geschriebenen Bildern wurden {n3} vermessen")
pruef(r1[0] == r2[0], "uebernommene Messwerte fuehren zu einem anderen Restflackern")
# und das Ergebnis ist dasselbe wie ganz ohne Merker
w.__dict__.pop('_mess_merker', None)
r4 = w._measure_and_correct(jp, db, apply_correction=False)
pruef(r3[0] == r4[0], f"mit Merker {r3[0]!r}, ohne {r4[0]!r} - das muss gleich sein")
print(f"   Messungen: {n1} / {n2} / {n3}")

print(f"\n{'='*52}\n{ok_n} Pruefungen bestanden, {fail_n} fehlgeschlagen")
sys.exit(1 if fail_n else 0)
