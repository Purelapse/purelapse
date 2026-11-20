# -*- coding: utf-8 -*-
"""Ein kompletter Arbeitsgang ueber das Hauptfenster."""
import sys, os, glob, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stand import *
from PyQt5 import _basis, QtWidgets

def schritt(name, fn):
    print(f"--- {name}")
    try:
        return fn()
    except Exception:
        print("   !! AUSNAHME:"); traceback.print_exc(limit=6); return None

def meldungen(seit=0):
    return [f"{a}: {t} / {x[:110]}" for a, t, x in _basis.PROTOKOLL[seit:]]

def log(f, *woerter, n=6):
    z = [x.strip() for x in f.txt_log._zeilen if any(w in x for w in woerter)]
    for x in z[-n:]: print("      ", x[:150])

ordner = os.path.join(ARBEIT, "O_ablauf")
dateien, _ = szene(ordner, n=56, sonne=True, luecke=30)
f = pm.MainWindow()

def einrichten():
    f.cmb_engine.setCurrentIndex(1)
    f.txt_art_path.setText(RT_CLI)
    f.rb_raw.setChecked(True)
    f._set_folder(ordner)
    print("   Zaehler:", f.lbl_count.text())
    print("   Kacheln:", len(f.tiles), "| Schritt:", f.step, "| Engine:", f.cmb_engine.currentText())
    print("   Luecken:", f.lbl_gaps.text(), "| sichtbar:", f.lbl_gaps.isVisible())
    print("   Lichter:", f.lbl_clip.text(), "| sichtbar:", f.lbl_clip.isVisible())
    print("   Farbstich:", f.lbl_farbstich.text(), "| sichtbar:", f.lbl_farbstich.isVisible())
schritt("1. Einrichten und Ordner einlesen", einrichten)

def pass1():
    n0 = len(_basis.PROTOKOLL)
    f._go_step('smooth')
    print("   Pass-Auswahl:", f.cmb_rawmode.currentText(), "| Startknopf:", f.btn_start.text(), "| frei:", f.btn_start.isEnabled())
    f._start()
    print("   Status:", f.lbl_status.text()[:90])
    print("   Rueckfragen:", meldungen(n0))
    print("   Profile:", len(glob.glob(ordner + "/*.pp3")), "| Knoepfe wieder frei:", f.btn_start.isEnabled(), "| Engine-Wahl frei:", f.cmb_engine.isEnabled())
    print("   Lichter jetzt:", f.lbl_clip.text())
    log(f, "Flackern", "Basisprofil:", "WARNUNG", "FEHLER")
schritt("2. Pass 1", pass1)

def keyframe():
    f.tiles[20]['chk'].setChecked(True)
    f.list_widget.setCurrentRow(20)
    print("   Knopf 'Keyframe einstellen' frei:", f.btn_kf_edit.isEnabled(), "|", f.btn_kf_edit.toolTip()[:60])
    def bedienen(dlg):
        print("      Dialog offen, Regler:", list(dlg.regler.keys()), "| Lichter waehlbar:", dlg.cmb_hl is not None)
        chk, sl, lbl, d = dlg.regler['saturation']; chk.setChecked(True); sl.setValue(22)
        chk, sl, lbl, d = dlg.regler['wb_temp']; chk.setChecked(True); sl.setValue(6400)
        if dlg.cmb_hl is not None: dlg.chk_hl.setChecked(True)
        print("      gewaehlt:", dlg.werte(), "| Lichter:", dlg.hl_wert())
    _basis.ANTWORTEN['QuickLookDialog'] = bedienen
    f._open_quick_dialog()
    d = pe.read_arp_dict(pe.sidecar(dateien[20]))
    print("   im Profil: Saettigung", d['Exposure'].get('Saturation'), "| WB", d['White Balance'].get('Setting'), d['White Balance'].get('Temperature'), "| Lichter", pe.hl_lesen(d), "| Belichtung", d['Exposure'].get('Compensation'))
    log(f, "Schnelleinstellungen", "Nachgelesen", "ACHTUNG")
schritt("3. Keyframe markieren und einstellen", keyframe)

def filter_():
    f.btn_kf_filter.setChecked(True)
    sichtbar = sum(1 for t in f.tiles if not t['item'].isHidden())
    print("   Filter an:", f.btn_kf_filter.text(), "| sichtbar:", sichtbar)
    f.btn_kf_filter.setChecked(False)
    print("   Filter aus: sichtbar", sum(1 for t in f.tiles if not t['item'].isHidden()))
schritt("4. Keyframe-Filter", filter_)

def pass2():
    n0 = len(_basis.PROTOKOLL)
    f._set_folder(ordner)       # neu einlesen, wie nach "Aktualisieren"
    print("   Engine nach dem Neueinlesen:", f.cmb_engine.currentText(), "| Schritt:", f.step, "| Keyframes:", f._kf_count)
    f._go_step('render')
    print("   Pass-Auswahl:", f.cmb_rawmode.currentText())
    f._start()
    print("   Status:", f.lbl_status.text()[:100])
    print("   Rueckfragen:", meldungen(n0))
    log(f, "Keyframes gefunden", "geprueft", "Restflackern", "ACHTUNG", "WARNUNG", "FEHLER", "in 0:")
    v = videos(ordner)
    if v:
        fl, n = video_flackern(v[0]); print(f"   Video: {os.path.basename(v[0])}, {n} Bilder, Flackern {fl:.4f} EV")
    else:
        print("   KEIN VIDEO")
schritt("5. Pass 2", pass2)

def codec():
    n0 = len(_basis.PROTOKOLL)
    f.cmb_codec.setCurrentIndex(1)         # NVIDIA - gibt es hier nicht
    print("   nach Wahl von NVENC steht die Liste auf:", f.cmb_codec.currentText())
    print("   Rueckfrage:", [m[:150] for m in meldungen(n0)])
schritt("6. Hardware-Codec waehlen, den es nicht gibt", codec)

def sprache():
    f._apply_language('en')
    print("   Englisch:", f.btn_kf_filter.text(), "|", f.btn_kf_edit.text(), "|", f.lbl_count.text()[:50], "|", f.lbl_clip.text()[:40])
    f._apply_language('de')
    print("   Deutsch: ", f.btn_kf_filter.text(), "|", f.btn_kf_edit.text())
    f._apply_theme('light'); f._apply_theme('dark')
    print("   Farbschema gewechselt, aktuell:", f.theme)
schritt("7. Sprache und Farbschema", sprache)

def schlange():
    f._go_step('render')
    n0 = len(_basis.PROTOKOLL)
    f._queue_add()
    print("   Auftraege:", len(f.queue), [j.get('label', '?')[:60] for j in f.queue])
    for v in videos(ordner): os.remove(v)
    f._queue_run() if hasattr(f, '_queue_run') else f.btn_q_run.click()
    print("   nach dem Stapel:", [j.get('status') for j in f.queue], "| Video da:", bool(videos(ordner)))
    print("   Rueckfragen:", meldungen(n0))
schritt("8. Warteschlange", schlange)
print("\nDialoge insgesamt:", len(_basis.PROTOKOLL))
