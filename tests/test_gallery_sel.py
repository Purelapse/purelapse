#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os  # fuer die Pfade der Pruefumgebung
"""
Pruefungen fuer die Auswahl in der Bildleiste.

Hintergrund: die Kacheln werden mit setItemWidget gesetzt. Ein solches
Widget verdeckt den Listeneintrag und faengt die Mausklicks ab - ohne
eigenes Zutun erfaehrt die Liste nichts davon, currentRow() bleibt -1,
und alles, was an der Auswahl haengt, bleibt tot.

Dazu ein allgemeiner Waechter gegen Namen, die in einer Funktion benutzt
werden, bevor sie zugewiesen sind. Genau so ein Fehler ist beim Einbau
dieser Auswahl entstanden.
"""
import io, ast, sys, builtins, collections

BASIS = os.environ.get("PURELAPSE_PROJEKT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
src = io.open(f"{BASIS}/purelapse_main.py", encoding="utf-8").read()

ok_n = fail_n = 0
def pruef(b, text):
    global ok_n, fail_n
    if b: ok_n += 1
    else:
        fail_n += 1
        print(f"  FEHLER: {text}")

def schnitt(txt, von, bis):
    return txt[txt.index(von):txt.index(bis)]


# ======================================================================
#  Waechter: Name benutzt, bevor er zugewiesen ist
# ======================================================================
def namen_vor_zuweisung(quelltext):
    """
    Sucht lokale Namen, die in einer Funktion gelesen werden, bevor sie
    dort zugewiesen werden.

    Bewusst vorsichtig, um Fehlalarme zu vermeiden: betrachtet werden nur
    Namen mit genau EINER Zuweisung in der Funktion, und nur Lesestellen
    ausserhalb von Schleifen - in einer Schleife darf eine Zuweisung am
    Ende des Rumpfes vor der Lesestelle des naechsten Durchlaufs liegen.
    """
    treffer = []
    baum = ast.parse(quelltext)

    def schleifenbereiche(fn):
        raum = []
        for k in ast.walk(fn):
            if isinstance(k, (ast.For, ast.While, ast.AsyncFor)):
                anfang = getattr(k, 'lineno', 0)
                ende = max((getattr(x, 'lineno', anfang) for x in ast.walk(k)),
                           default=anfang)
                raum.append((anfang, ende))
        return raum

    for fn in ast.walk(baum):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Namen, die als Parameter hereinkommen, sind immer da
        args = fn.args
        bekannt = {a.arg for a in list(args.args) + list(args.kwonlyargs)
                   + list(getattr(args, 'posonlyargs', []))}
        if args.vararg:
            bekannt.add(args.vararg.arg)
        if args.kwarg:
            bekannt.add(args.kwarg.arg)
        # globale und nicht-lokale Namen aussen vor lassen
        for k in ast.walk(fn):
            if isinstance(k, (ast.Global, ast.Nonlocal)):
                bekannt.update(k.names)
        zuweisungen = collections.defaultdict(list)
        for k in ast.walk(fn):
            ziele = []
            if isinstance(k, ast.Assign):
                ziele = k.targets
            elif isinstance(k, (ast.AugAssign, ast.AnnAssign)):
                ziele = [k.target]
            elif isinstance(k, (ast.For, ast.AsyncFor, ast.comprehension)):
                # Schleifen- und Abstraktionsvariablen zaehlen als immer
                # vorhanden. Ein mehrzeiliger Ausdruck wie
                #     [f(i) for i in liste]
                # liest i in einer frueheren Zeile als das "for", und eine
                # Schleife laeuft ohnehin mehrfach - beides sind keine
                # Hinweise auf den gesuchten Fehler, sondern Fehlalarme.
                for n in ast.walk(k.target):
                    if isinstance(n, ast.Name):
                        bekannt.add(n.id)
                ziele = []
            elif isinstance(k, ast.withitem):
                ziele = [k.optional_vars] if k.optional_vars else []
            elif isinstance(k, ast.ExceptHandler) and k.name:
                bekannt.add(k.name)
            elif isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef,
                                ast.ClassDef)) and k is not fn:
                bekannt.add(k.name)
            elif isinstance(k, (ast.Import, ast.ImportFrom)):
                for a in k.names:
                    bekannt.add((a.asname or a.name).split('.')[0])
            for z in ziele:
                for n in ast.walk(z):
                    if isinstance(n, ast.Name):
                        zuweisungen[n.id].append(n.lineno)
        schleifen = schleifenbereiche(fn)

        def in_schleife(zeile):
            return any(a <= zeile <= e for a, e in schleifen)

        for k in ast.walk(fn):
            if not (isinstance(k, ast.Name) and isinstance(k.ctx, ast.Load)):
                continue
            name = k.id
            if name in bekannt or name in dir(builtins):
                continue
            stellen = zuweisungen.get(name)
            if not stellen or len(stellen) != 1:
                continue
            if k.lineno < stellen[0] and not in_schleife(k.lineno):
                treffer.append((fn.name, name, k.lineno, stellen[0]))
    return treffer


print("=== 1. Waechter prueft sich selbst ===")
# Der Fehler, der tatsaechlich passiert ist, nachgestellt
kaputt = '''
def baue_kachel(self, widget, chk):
    chk.toggled.connect(lambda c, z=zeile: self.style(widget, c, z))
    zeile = len(self.tiles)
    widget.setProperty("tile_row", zeile)
'''
gefunden = namen_vor_zuweisung(kaputt)
pruef(len(gefunden) == 1 and gefunden[0][1] == 'zeile',
      f"der Waechter findet den nachgestellten Fehler nicht: {gefunden}")
# Und schlaegt nicht bei harmlosem Code an
sauber = '''
def baue_kachel(self, widget, chk):
    zeile = len(self.tiles)
    chk.toggled.connect(lambda c, z=zeile: self.style(widget, c, z))
    for i in range(3):
        summe = summe + i if i else 0
'''
pruef(namen_vor_zuweisung(sauber) == [],
      f"Fehlalarm bei sauberem Code: {namen_vor_zuweisung(sauber)}")
# Mehrzeilige Abstraktion: haeufigster Fehlalarm, darf nicht anschlagen
mehrzeilig = """
def f(self, liste):
    teile = [self._t(f"Bild {i}: {v}",
                     f"frame {i}: {v}")
             for i, v in liste]
    return teile
"""
pruef(namen_vor_zuweisung(mehrzeilig) == [],
      f"Fehlalarm bei mehrzeiliger Abstraktion: {namen_vor_zuweisung(mehrzeilig)}")
# Schleife, deren Variable am Ende des Rumpfes gesetzt wird
schleife = """
def f(self, n):
    for i in range(n):
        if i:
            self.tu(vorher)
        vorher = i
"""
pruef(namen_vor_zuweisung(schleife) == [],
      f"Fehlalarm bei einer Schleife: {namen_vor_zuweisung(schleife)}")
# Aber der echte Fall mit einem Lambda-Standardwert bleibt erkannt
lam = """
def f(self, w):
    w.sig.connect(lambda c, z=nummer: self.tu(c, z))
    nummer = 7
"""
pruef(len(namen_vor_zuweisung(lam)) == 1,
      f"der echte Fall wird nicht mehr erkannt: {namen_vor_zuweisung(lam)}")

print("=== 2. Waechter laeuft ueber das Programm ===")
treffer = namen_vor_zuweisung(src)
for fn, name, gelesen, gesetzt in treffer:
    print(f"  {fn}(): '{name}' in Zeile {gelesen} gelesen, erst in {gesetzt} gesetzt")
pruef(not treffer, f"{len(treffer)} Name(n) vor ihrer Zuweisung benutzt")

print("=== 3. Kachel-Klicks ===")
ef = schnitt(src[src.index("class MainWindow"):], "    def eventFilter", "    def _toggle_keyframe_status")
pruef("MouseButtonPress" in ef, "Mausklicks werden nicht ausgewertet")
pruef("MouseButtonDblClick" in ef, "Doppelklick wird nicht ausgewertet")
pruef("setCurrentRow(row)" in ef, "der Klick setzt die Zeile nicht")
pruef("_row_of_widget(obj)" in ef, "Zuordnung Widget -> Zeile fehlt")
pruef("return super().eventFilter(obj, event)" in ef,
      "der Filter muss den Klick weiterreichen, sonst geht das Kaestchen nicht")
pruef("return True" not in ef.split("QEvent.Wheel")[-1].split("typ = event.type()", 1)[-1]
      and ef.count("return True") <= 1, "der Filter darf den Klick nicht schlucken")
pruef("self._update_kf_buttons()" in ef,
      "bei gleichbleibender Zeile wuerden die Knoepfe nicht nachgezogen")

bau = schnitt(src, "    def _on_image_ready", "    TILE_MIN =")
pruef('widget.setProperty("tile_row", zeile)' in bau,
      "die Kachel traegt keine Zeilennummer")
pruef("widget.installEventFilter(self)" in bau, "Kachel wird nicht abgehoert")
pruef("for kind in widget.findChildren(QtWidgets.QWidget):" in bau,
      "die Teile der Kachel werden nicht abgehoert - ein Klick auf das "
      "Vorschaubild kaeme nie an")
pruef(bau.index("zeile = len(self.tiles)") < bau.index("self.tiles.append("),
      "die Zeilennummer muss VOR dem Anhaengen bestimmt werden")

print("=== 4. Sichtbare Auswahl ===")
st = schnitt(src, "    def _style_tile", "    def _markiere_auswahl")
pruef("ausgewaehlt=False" in st, "_style_tile kennt keinen Auswahlzustand")
pruef("t['sel']" in st, "die Auswahl bekommt keinen eigenen Hintergrund")
pruef("t['accent']" in st, "die Auswahl bekommt keinen eigenen Rahmen")
ma = schnitt(src, "    def _markiere_auswahl", "    def _row_of_widget")
pruef("{vorher, row}" in ma,
      "es werden nicht genau die beiden betroffenen Kacheln umgefaerbt")
pruef("for i in range(len(self.tiles))" not in ma,
      "ein Durchlauf ueber alle Kacheln waere bei tausend Bildern traege")
pruef("self._markiere_auswahl(row)" in src, "Auswahl wird nie eingefaerbt")
pruef(src.count("self._sel_row = -1") == 2,
      "der Auswahlzustand wird nicht ueberall zurueckgesetzt")
# Alle Aufrufe von _style_tile passen zur Signatur
baum = ast.parse(src)
for k in ast.walk(baum):
    if (isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
            and k.func.attr == "_style_tile"):
        pruef(2 <= len(k.args) <= 3,
              f"_style_tile in Zeile {k.lineno} mit {len(k.args)} Argumenten")

print("=== 5. Knopf-Freigabe ===")
ub = schnitt(src, "    def _update_kf_buttons", "    def _open_quick_dialog")
pruef("_ziel_keyframe()" in ub, "der Knopf fragt nicht nach einem Ziel")
pruef("getattr(self, '_busy', False)" in ub, "_busy ungesichert")
pruef("eng('kind') in ('ini', 'darktable', 'lightroom', 'rapidraw')" in ub, "Knopf nicht fuer alle Engines freigegeben")
pruef("currentRow" not in ub,
      "der Knopf darf nicht mehr an der Auswahl haengen")
pruef(ub.count("setToolTip(") == 3,
      f"nicht jeder Fall erklaert sich ({ub.count('setToolTip(')} Hinweistexte)")
pruef("def _aktuelle_kachel" not in src,
      "die alte, auswahlabhaengige Hilfsmethode ist noch da")

# Die Zielbestimmung in Reinform nachstellen
class Haken:
    def __init__(self, an): self.an = an
    def isChecked(self): return self.an

class Liste:
    def __init__(self, row): self.row = row
    def currentRow(self): return self.row

ns = {}
exec("class M:\n"
     + schnitt(src, "    def _keyframe_zeilen", "    def _update_kf_buttons"), ns)
def mach(haken, row):
    m = ns["M"]()
    m.tiles = [{'chk': Haken(h), 'name': f"IMG_{i}"} for i, h in enumerate(haken)]
    m.list_widget = Liste(row)
    return m

pruef(mach([0, 0, 0], -1)._ziel_keyframe() is None, "ohne Keyframe kein Ziel")
pruef(mach([], -1)._ziel_keyframe() is None, "leere Galerie")
pruef(mach([0, 1, 0, 1], -1)._ziel_keyframe() == 1,
      "ohne Auswahl muss das erste Keyframe genommen werden")
pruef(mach([0, 1, 0, 1], 3)._ziel_keyframe() == 3,
      "ein ausgewaehltes Keyframe hat Vorrang")
pruef(mach([0, 1, 0, 1], 2)._ziel_keyframe() == 1,
      "ist die Auswahl kein Keyframe, faellt es auf das erste zurueck")
pruef(mach([1], 0)._ziel_keyframe() == 0, "einzelnes Keyframe, Zeile 0")
pruef(mach([1, 1], -1)._keyframe_zeilen() == [0, 1], "Zeilenliste falsch")
pruef(mach([0, 0], -1)._keyframe_zeilen() == [], "Zeilenliste nicht leer")
# Kacheln ohne Haken duerfen nicht stoeren
m = ns["M"]()
m.tiles = [{'name': 'ohne'}, {'chk': Haken(True), 'name': 'mit'}]
m.list_widget = Liste(-1)
pruef(m._ziel_keyframe() == 1, "Kachel ohne Haken bringt die Zaehlung durcheinander")

od = schnitt(src, "    def _open_quick_dialog", "    def _on_tile_selected")
pruef("_ziel_keyframe()" in od, "der Dialog arbeitet nicht mit dem Ziel")
pruef("setCurrentRow(ziel)" in od,
      "das bearbeitete Bild wird nicht sichtbar gemacht")
pruef("scrollToItem" in od, "es wird nicht zum bearbeiteten Bild gescrollt")

print(f"\n{'='*52}\n{ok_n} Pruefungen bestanden, {fail_n} fehlgeschlagen")
sys.exit(1 if fail_n else 0)
