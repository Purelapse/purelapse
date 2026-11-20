# -*- coding: utf-8 -*-
from ._basis import Null, _MarkenMeta


class QImage(metaclass=_MarkenMeta):
    def __init__(self, *a, **k): self.args = a
    def copy(self, *a): return self
    def width(self): return 128
    def height(self): return 115
    def isNull(self): return False
    def scaled(self, *a, **k): return self


class QPixmap:
    def __init__(self, *a, **k): pass
    @staticmethod
    def fromImage(img, *a): return QPixmap()
    def scaled(self, *a, **k): return self
    def width(self): return 128
    def height(self): return 115
    def isNull(self): return False


def __getattr__(name):
    if name.startswith('__'):
        raise AttributeError(name)
    return type(name, (Null,), {})
