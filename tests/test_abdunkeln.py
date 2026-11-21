# -*- coding: utf-8 -*-
"""Abdunkeln des Hauptfensters, solange ein modales Fenster davor steht."""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand"))
from stand import *
from PyQt5 import QtWidgets, QtCore
OK = FEHL = 0
def pruef(b, t):
    global OK, FEHL
    if b: OK += 1
    else: FEHL += 1; print("  FEHLER:", t)

# Der Filter muss an der Anwendung haengen, sonst sieht er die Dialoge nicht.
app = QtWidgets.QApplication.instance()
angemeldet = []
app.installEventFilter = lambda o: angemeldet.append(o)
f = pm.MainWindow()
f.show()
ab = f.abdunkler
schleier = ab.schleier
print("=== 1. Anmeldung ===")
pruef(ab in angemeldet, "Abdunkler ist nicht als Ereignisfilter der Anwendung angemeldet")
pruef(not schleier.isVisible(), "Schleier ist schon beim Start sichtbar")

def fenster(modal=True, eigenes_fenster=True, modalitaet=None):
    d = QtWidgets.QDialog(f)
    d.isWindow = lambda: eigenes_fenster
    d.isModal = lambda: modal
    d.windowModality = lambda: modalitaet if modalitaet is not None else (
        QtCore.Qt.ApplicationModal if modal else QtCore.Qt.NonModal)
    return d

def zeigen(d): ab.eventFilter(d, QtCore.QEvent(QtCore.QEvent.Show))
def weg(d): ab.eventFilter(d, QtCore.QEvent(QtCore.QEvent.Hide))

print("=== 2. Ein Dialog ===")
a = fenster()
zeigen(a)
pruef(schleier.isVisible(), "modaler Dialog dunkelt nicht ab")
weg(a)
pruef(not schleier.isVisible(), "Schleier bleibt nach dem Schliessen stehen")

print("=== 3. Verschachtelt: Rueckfrage aus einem Dialog ===")
a, b = fenster(), fenster()
zeigen(a); zeigen(b); weg(b)
pruef(schleier.isVisible(), "Schleier verschwindet, obwohl der erste Dialog noch offen ist")
zeigen(a)   # doppelt gemeldet: darf nicht doppelt zaehlen
weg(a)
pruef(not schleier.isVisible(), "Schleier bleibt nach dem letzten Dialog stehen")

print("=== 4. Was nicht abdunkeln darf ===")
for name, d in (("nicht modales Fenster (Warteschlange)", fenster(modal=False)),
                ("Bedienelement im Fenster", fenster(eigenes_fenster=False))):
    zeigen(d)
    pruef(not schleier.isVisible(), f"{name} dunkelt ab")
    weg(d)
pruef(not ab._ist_modal(f), "das Hauptfenster selbst zaehlt als Dialog")
pruef(not ab._ist_modal(schleier), "der Schleier zaehlt als Dialog")
pruef(not ab._ist_modal(object()), "ein Nicht-Widget zaehlt als Dialog")
fenster_modal = fenster(modal=False, modalitaet=QtCore.Qt.WindowModal)
zeigen(fenster_modal)
pruef(schleier.isVisible(), "fenstermodaler Dialog dunkelt nicht ab")
weg(fenster_modal)

print("=== 5. Kein doppelter Schleier ueber dem Ladeschirm ===")
f.lade_schirm.show()
a = fenster(); zeigen(a)
pruef(not schleier.isVisible(), "Schleier liegt zusaetzlich ueber dem Ladeschirm")
f.lade_schirm.hide(); weg(a)
print("=== 6. Hauptfenster noch nicht sichtbar ===")
f.hide(); a = fenster(); zeigen(a)
pruef(not schleier.isVisible(), "Schleier ueber einem unsichtbaren Fenster")
weg(a); f.show()

print("=== 7. Native Dateidialoge: halten() ===")
with ab.halten():
    pruef(schleier.isVisible(), "halten() dunkelt nicht ab")
    a = fenster(); zeigen(a); weg(a)
    pruef(schleier.isVisible(), "Dialog innerhalb von halten() hebt den Schleier auf")
pruef(not schleier.isVisible(), "Schleier bleibt nach halten() stehen")
try:
    with ab.halten():
        raise ValueError("Test")
except ValueError:
    pass
pruef(not schleier.isVisible() and ab._halten == 0, "Ausnahme in halten() laesst den Schleier stehen")
src = open(os.path.join(PROJEKT, "purelapse_main.py"), encoding="utf-8").read()
for fn in ("_browse_art_cli", "_browse_arp_template"):
    rumpf = src.split(f"    def {fn}(self")[1].split("\n    def ")[0]
    pruef("getOpenFileName" in rumpf and "with self.abdunkler.halten():" in rumpf,
          f"{fn}: nativer Dateidialog ohne Abdunkeln")

print("=== 8. Farbe je Farbschema, weiches Einblenden ===")
for thema in ("light", "dark"):
    f._apply_theme(thema)
    farbe = pm.THEMES[thema]['schleier']
    pruef(schleier.farbe == tuple(farbe), f"{thema}: Schleierfarbe {schleier.farbe} statt {farbe}")
    pruef(len(farbe) == 4 and all(0 <= x <= 255 for x in farbe) and 60 <= farbe[3] <= 200,
          f"{thema}: Schleierfarbe unbrauchbar: {farbe}")
ab._anteil_setzen(0.5); pruef(abs(schleier.anteil - 0.5) < 1e-9, "Einblenden setzt den Anteil nicht")
ab._anteil_setzen(3); pruef(schleier.anteil == 1.0, "Anteil wird nicht begrenzt")
ab._anteil_setzen(None); pruef(schleier.anteil == 1.0, "unbrauchbarer Wert der Animation")
pruef("WA_TransparentForMouseEvents" in src.split("class Schleier")[1].split("class Abdunkler")[0],
      "Schleier faengt Mausklicks ab")

print(f"\n{OK} Pruefungen bestanden, {FEHL} fehlgeschlagen")
sys.exit(1 if FEHL else 0)
