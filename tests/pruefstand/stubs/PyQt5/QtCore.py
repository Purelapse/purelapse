# -*- coding: utf-8 -*-
from ._basis import Sig, pyqtSignal, Null, Marke, _MarkenMeta


class Qt(metaclass=_MarkenMeta):
    pass


class QEvent(metaclass=_MarkenMeta):
    def __init__(self, typ=None): self._typ = typ
    def type(self): return self._typ


class QObject:
    def __init__(self, *a, **k): pass


class QThread(QObject):
    """Laeuft im Pruefstand im selben Faden: start() ruft run() direkt."""
    def __init__(self, *a, **k):
        super().__init__()
        self._laeuft = False

    def start(self):
        self._laeuft = True
        try:
            self.run()
        finally:
            self._laeuft = False

    def run(self): pass
    def isRunning(self): return self._laeuft
    def wait(self, *a): return True
    def quit(self): pass
    def terminate(self): pass


class QTimer(QObject):
    def __init__(self, *a, **k):
        self.timeout = Sig()
        self._aktiv = False
    def setSingleShot(self, b): pass
    def setInterval(self, ms): pass
    def start(self, *a):
        # sofort ausloesen - im Pruefstand gibt es keine Ereignisschleife
        self.timeout.emit()
    def stop(self): pass
    def isActive(self): return False
    @staticmethod
    def singleShot(ms, f):
        f()


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    return Null()
