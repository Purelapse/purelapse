# -*- coding: utf-8 -*-
"""Stellvertreter fuer pyqtgraph: merkt sich die Kurvendaten, zeichnet nichts."""
from PyQt5._basis import Null, Sig

OPTIONEN = {}
def setConfigOptions(**k): OPTIONEN.update(k)


class _Stift(Null):
    def __init__(self, *a, **k):
        self.farbe = a[0] if a else k.get('color')
        self.breite = k.get('width', 1)
def mkPen(*a, **k): return _Stift(*a, **k)
def mkBrush(*a, **k): return Null()


class _Kurve(Null):
    def __init__(self, *a, **k):
        self.x, self.y = [], []
        self.sigPointsClicked = Sig()
        self.symbol = k.get('symbol')
    def setData(self, x=None, y=None, *a, **k):
        self.x = list(x) if x is not None else []
        self.y = list(y) if y is not None else []
    def setSymbol(self, s): self.symbol = s
PlotCurveItem = _Kurve


class InfiniteLine(Null):
    def __init__(self, *a, **k):
        self.pos = k.get('pos', a[0] if a else 0)
        self.label_text = k.get('label')
        self.sichtbar = True
    def setPos(self, p): self.pos = p
    def setVisible(self, b): self.sichtbar = bool(b)
    def value(self): return self.pos


class LinearRegionItem(Null):
    def __init__(self, *a, **k):
        self.bereich = tuple(k.get('values', (0, 1)))
        self.sichtbar = True
        self.beweglich = k.get('movable', True)
        self.pinsel = None
        self.z = 0
        self.lines = [InfiniteLine(), InfiniteLine()]
    def setRegion(self, r): self.bereich = (float(r[0]), float(r[1]))
    def getRegion(self): return self.bereich
    def setVisible(self, b): self.sichtbar = bool(b)
    def isVisible(self): return self.sichtbar
    def setBrush(self, b): self.pinsel = b
    def setZValue(self, z): self.z = z


class _Punkt:
    def __init__(self, x, y=0): self._x, self._y = x, y
    def x(self): return self._x
    def y(self): return self._y


class _Klick:
    """Ein Mausklick im Diagramm, an der Bildnummer x."""
    def __init__(self, x): self._p = _Punkt(x)
    def scenePos(self): return self._p


class _Ansicht(Null):
    def sceneBoundingRect(self):
        class R:
            def contains(self, p): return True
        return R()
    def mapSceneToView(self, p): return p
    def setDefaultPadding(self, *a): pass


class _Szene(Null):
    def __init__(self): self.sigMouseClicked = Sig()


class _PlotItem(Null):
    def __init__(self): self.vb = _Ansicht()


class PlotWidget(Null):
    def __init__(self, *a, **k):
        self.kurven, self.elemente, self.titel = [], [], k.get('title')
        self._szene = _Szene()
        self.plotItem = _PlotItem()
    def scene(self): return self._szene
    def getViewBox(self): return self.plotItem.vb
    def plot(self, *a, **k):
        c = _Kurve(*a, **k)
        self.kurven.append(c)
        return c
    def addItem(self, it, **k): self.elemente.append(it)
    def removeItem(self, it):
        if it in self.elemente:
            self.elemente.remove(it)
    def setTitle(self, t): self.titel = t


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    return type(name, (Null,), {})
