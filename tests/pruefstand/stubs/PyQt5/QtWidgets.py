# -*- coding: utf-8 -*-
"""Bedienelemente ohne Bildschirm: sie merken sich ihren Zustand und
senden ihre Signale, zeichnen aber nichts."""
import sys
from ._basis import Sig, Null, Marke, _MarkenMeta, PROTOKOLL, ANTWORTEN

SIGNALE = {'clicked', 'toggled', 'valueChanged', 'currentIndexChanged',
           'currentRowChanged', 'textChanged', 'stateChanged', 'triggered',
           'accepted', 'rejected', 'itemClicked', 'sliderReleased',
           'editingFinished', 'currentTextChanged', 'finished',
           'buttonClicked', 'itemDoubleClicked', 'splitterMoved'}
ALLE = []      # jedes erzeugte Bedienelement, fuer findChildren


class QWidget(metaclass=_MarkenMeta):
    def __init__(self, *a, **k):
        self._enabled = True
        self._visible = True
        self._text = ""
        self._title = ""
        self._tip = ""
        self._props = {}
        self._style = ""
        self._checked = False
        self._checkable = False
        self._blockiert = False
        self._parent = a[0] if a and isinstance(a[0], QWidget) else None
        for x in a:
            if isinstance(x, str):
                self._text = x
                self._title = x
                break
        ALLE.append(self)

    # ---- Signale und alles Unbekannte --------------------------------
    def __getattr__(self, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        if n.startswith('_'):
            raise AttributeError(n)
        if n in SIGNALE:
            s = Sig()
            self.__dict__[n] = s
            return s
        return Null()

    def blockSignals(self, b):
        self._blockiert = bool(b)
        for v in self.__dict__.values():
            if isinstance(v, Sig):
                v.blockiert = bool(b)
        return False

    # ---- allgemeiner Zustand -----------------------------------------
    def setEnabled(self, b): self._enabled = bool(b)
    def isEnabled(self): return self._enabled
    def setDisabled(self, b): self._enabled = not b
    def setVisible(self, b): self._visible = bool(b)
    def isVisible(self): return self._visible
    def isHidden(self): return not self._visible
    def show(self): self._visible = True
    def hide(self): self._visible = False
    def setText(self, t): self._text = str(t)
    def text(self): return self._text
    def setTitle(self, t): self._title = str(t)
    def title(self): return self._title
    def setToolTip(self, t): self._tip = str(t)
    def toolTip(self): return self._tip
    def setStyleSheet(self, s): self._style = str(s)
    def styleSheet(self): return self._style
    def setProperty(self, k, v): self._props[k] = v
    def property(self, k): return self._props.get(k)
    def parentWidget(self): return self._parent if self._parent is not None else _ELTERN
    def parent(self): return self._parent
    def findChildren(self, *a): return list(ALLE)
    def width(self): return 900
    def height(self): return 600
    def setCheckable(self, b): self._checkable = bool(b)
    def isChecked(self): return self._checked
    def setChecked(self, b):
        b = bool(b)
        if b != self._checked:
            self._checked = b
            self.toggled.emit(b)
    def click(self):
        if self._checkable:
            self.setChecked(not self._checked)
        self.clicked.emit(self._checked)
    def setPlaceholderText(self, t): self._placeholder = str(t)
    def placeholderText(self): return getattr(self, '_placeholder', "")
    def installEventFilter(self, o): pass
    def eventFilter(self, o, e): return False
    def resizeEvent(self, e): pass
    def closeEvent(self, e): pass
    def close(self): return True


_ELTERN = QWidget.__new__(QWidget)
_ELTERN.__dict__.update(_parent=None, _enabled=True, _visible=True)


class QApplication(QWidget):
    _inst = None
    def __init__(self, *a, **k):
        super().__init__()
        QApplication._inst = self
    @staticmethod
    def instance(): return QApplication._inst
    @staticmethod
    def setOverrideCursor(*a): pass
    @staticmethod
    def restoreOverrideCursor(*a): pass
    @staticmethod
    def processEvents(*a): pass
    def exec_(self): return 0


class QCheckBox(QWidget): pass
class QRadioButton(QWidget):
    """Wie in Qt: von den Auswahlknoepfen desselben Elternteils ist
    immer nur einer gesetzt."""
    def setChecked(self, b):
        b = bool(b)
        if b:
            for w in ALLE:
                if (w is not self and isinstance(w, QRadioButton)
                        and w._parent is self._parent and w._checked):
                    w._checked = False
                    w.toggled.emit(False)
        if b != self._checked:
            self._checked = b
            self.toggled.emit(b)
class QPushButton(QWidget): pass
class QToolButton(QWidget): pass
class QLabel(QWidget):
    def setPixmap(self, p): self._pixmap = p
class QGroupBox(QWidget): pass
class QTextEdit(QWidget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._zeilen = []
    def append(self, t): self._zeilen.append(str(t))
    def appendPlainText(self, t): self._zeilen.append(str(t))
    def appendHtml(self, t):
        # was im Fenster zu lesen waere: ohne Auszeichnung
        import re, html
        klar = re.sub(r"<br\s*/?>", "\n", str(t))
        klar = html.unescape(re.sub(r"<[^>]+>", "", klar)).replace("\xa0", " ")
        self._zeilen.append(klar)
    def clear(self): self._zeilen = []
    def toPlainText(self): return "\n".join(self._zeilen)
    def setPlainText(self, t): self._zeilen = str(t).splitlines()
QPlainTextEdit = QTextEdit


class QLineEdit(QWidget):
    def setText(self, t):
        self._text = str(t)
        self.textChanged.emit(self._text)


class QComboBox(QWidget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._items = []      # [text, data, {role: wert}]
        self._idx = -1
    def addItem(self, text, data=None):
        self._items.append([str(text), data, {}])
        if self._idx < 0:
            self._idx = 0
    def addItems(self, texte):
        for t in texte:
            self.addItem(t)
    def count(self): return len(self._items)
    def currentIndex(self): return self._idx
    def setCurrentIndex(self, i):
        i = int(i)
        if 0 <= i < len(self._items) and i != self._idx:
            self._idx = i
            self.currentIndexChanged.emit(i)
    def currentText(self):
        return self._items[self._idx][0] if 0 <= self._idx < len(self._items) else ""
    def itemText(self, i): return self._items[i][0]
    def setItemText(self, i, t): self._items[i][0] = str(t)
    def currentData(self, *a):
        return self._items[self._idx][1] if 0 <= self._idx < len(self._items) else None
    def itemData(self, i, *a): return self._items[i][1]
    def setItemData(self, i, wert, rolle=None): self._items[i][2][rolle] = wert
    def findData(self, d):
        for i, it in enumerate(self._items):
            if it[1] == d:
                return i
        return -1
    def findText(self, t):
        for i, it in enumerate(self._items):
            if it[0] == t:
                return i
        return -1
    def clear(self):
        self._items = []
        self._idx = -1


class QSlider(QWidget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._wert, self._min, self._max = 0, 0, 99
    def setMinimum(self, v): self._min = int(v)
    def setMaximum(self, v): self._max = int(v)
    def setRange(self, a, b): self._min, self._max = int(a), int(b)
    def minimum(self): return self._min
    def maximum(self): return self._max
    def value(self): return self._wert
    def setValue(self, v):
        v = max(self._min, min(self._max, int(v)))
        if v != self._wert:
            self._wert = v
            self.valueChanged.emit(v)
QSpinBox = QSlider


class QProgressBar(QWidget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._wert, self._max = 0, 100
    def setValue(self, v): self._wert = int(v)
    def value(self): return self._wert
    def setMaximum(self, v): self._max = int(v)
    def maximum(self): return self._max
    def setRange(self, a, b): self._max = int(b)


class QListWidgetItem(metaclass=_MarkenMeta):
    def __init__(self, *a, **k):
        self._hidden = False
        self._text = next((x for x in a if isinstance(x, str)), "")
        self._data = {}
    def setHidden(self, b): self._hidden = bool(b)
    def isHidden(self): return self._hidden
    def text(self): return self._text
    def setText(self, t): self._text = str(t)
    def setData(self, rolle, wert): self._data[rolle] = wert
    def data(self, rolle): return self._data.get(rolle)
    def __getattr__(self, n):
        if n.startswith('_'):
            raise AttributeError(n)
        return Null()


class _Sichtfenster(QWidget):
    def width(self): return 360
    def height(self): return 400


class QListWidget(QWidget):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._eintraege = []
        self._zeile = -1
        self._rollwert = 0
        self._sicht = _Sichtfenster()
    def addItem(self, it):
        if isinstance(it, str):
            it = QListWidgetItem(it)
        if it not in self._eintraege:
            self._eintraege.append(it)
    def count(self): return len(self._eintraege)
    def item(self, i):
        return self._eintraege[i] if 0 <= i < len(self._eintraege) else None
    def clear(self):
        self._eintraege = []
        self._zeile = -1
        self._rollwert = 0
    def currentRow(self): return self._zeile
    def setCurrentRow(self, i):
        i = int(i)
        if i != self._zeile:
            self._zeile = i
            self.currentRowChanged.emit(i)
    def row(self, it):
        return self._eintraege.index(it) if it in self._eintraege else -1
    def takeItem(self, i):
        return self._eintraege.pop(i) if 0 <= i < len(self._eintraege) else None
    def viewport(self): return self._sicht
    def spacing(self): return 4
    def setItemWidget(self, it, w): it._widget = w

    # ---- Kachelraster und Rollen, wie die Bildleiste es zeigt ----------
    KACHEL_B, KACHEL_H, SICHT_B, SICHT_H = 110, 130, 360, 400

    def _raster(self):
        """Zeile im Raster je sichtbarem Eintrag (ausgeblendete zaehlen nicht)."""
        spalten = max(1, self.SICHT_B // self.KACHEL_B)
        lage, k = {}, 0
        for it in self._eintraege:
            if not it.isHidden():
                lage[id(it)] = k // spalten
                k += 1
        return lage, spalten

    def visualItemRect(self, it):
        lage, _ = self._raster()
        zeile = lage.get(id(it))
        if zeile is None:
            return _Rechteck(-10 ** 6, -10 ** 6)
        # wie in Qt: schrumpft der Inhalt, rutscht der Rollwert mit zurueck
        self._rollwert = min(getattr(self, '_rollwert', 0),
                             self.verticalScrollBar().maximum())
        oben = zeile * self.KACHEL_H - self._rollwert
        return _Rechteck(oben, oben + self.KACHEL_H - 1)

    def verticalScrollBar(self):
        if '_rollbalken' not in self.__dict__:
            self.__dict__['_rollbalken'] = _Rollbalken(self)
        return self.__dict__['_rollbalken']

    def scrollToItem(self, it, *a):
        r = self.visualItemRect(it)
        if r.top() < 0 or r.bottom() > self.SICHT_H:
            self.verticalScrollBar().setValue(getattr(self, '_rollwert', 0) + r.top())

    def doItemsLayout(self): pass


class _Rechteck:
    def __init__(self, oben, unten): self._o, self._u = oben, unten
    def top(self): return self._o
    def bottom(self): return self._u
    def height(self): return self._u - self._o + 1


class _Rollbalken:
    def __init__(self, liste):
        self._liste = liste
        self.valueChanged = Sig()
    def value(self): return getattr(self._liste, '_rollwert', 0)
    def maximum(self):
        lage, _ = self._liste._raster()
        zeilen = (max(lage.values()) + 1) if lage else 0
        return max(0, zeilen * self._liste.KACHEL_H - self._liste.SICHT_H)
    def setValue(self, v):
        v = max(0, min(self.maximum(), int(v)))
        if v != self.value():
            self._liste._rollwert = v
            self.valueChanged.emit(v)


class QDialog(QWidget):
    Accepted, Rejected = 1, 0
    def exec_(self):
        PROTOKOLL.append(('dialog', type(self).__name__, self._title))
        antwort = ANTWORTEN.get(type(self).__name__, QDialog.Accepted)
        if callable(antwort):
            # der Pruefstand "bedient" den Dialog
            ergebnis = antwort(self)
            return QDialog.Accepted if ergebnis is None else ergebnis
        return antwort
    def accept(self): pass
    def reject(self): pass
    def done(self, r): pass
    def setWindowTitle(self, t): self._title = str(t)
    def resize(self, *a): pass


class QDialogButtonBox(QWidget):
    def addButton(self, *a, **k): return QPushButton(*[x for x in a if isinstance(x, str)])
    def button(self, *a): return QPushButton()


class QMessageBox(QWidget):
    Yes, No, Ok, Cancel = Marke('Yes'), Marke('No'), Marke('Ok'), Marke('Cancel')

    @staticmethod
    def _melde(art, titel, text):
        PROTOKOLL.append((art, str(titel), str(text)))
        return ANTWORTEN.get(art, QMessageBox.Yes)

    @staticmethod
    def question(eltern, titel, text, *a, **k):
        return QMessageBox._melde('frage', titel, text)

    @staticmethod
    def warning(eltern, titel, text, *a, **k):
        return QMessageBox._melde('warnung', titel, text)

    @staticmethod
    def information(eltern, titel, text, *a, **k):
        return QMessageBox._melde('hinweis', titel, text)

    @staticmethod
    def critical(eltern, titel, text, *a, **k):
        return QMessageBox._melde('fehler', titel, text)


class QFileDialog(QWidget):
    @staticmethod
    def getExistingDirectory(*a, **k): return ANTWORTEN.get('ordner', "")
    @staticmethod
    def getOpenFileName(*a, **k): return (ANTWORTEN.get('datei', ""), "")
    @staticmethod
    def getSaveFileName(*a, **k): return (ANTWORTEN.get('speichern', ""), "")


def __getattr__(name):
    """Jede nicht eigens gebaute Klasse wird ein schlichtes Bedienelement."""
    if name.startswith('__'):
        raise AttributeError(name)
    kl = type(name, (QWidget,), {})
    setattr(sys.modules[__name__], name, kl)
    return kl
