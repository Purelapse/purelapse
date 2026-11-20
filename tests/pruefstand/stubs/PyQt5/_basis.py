# -*- coding: utf-8 -*-
"""Gemeinsame Bausteine der Qt-Stellvertreter."""
PROTOKOLL = []          # alles, was Dialoge gemeldet haetten
ANTWORTEN = {}          # vorgegebene Antworten fuer Rueckfragen


class Sig:
    """Ein Signal: merkt sich die Empfaenger und ruft sie beim Senden."""
    def __init__(self):
        self.slots = []
        self.gesendet = []
        self.blockiert = False

    def connect(self, f):
        self.slots.append(f)

    def disconnect(self, *a):
        self.slots = []

    def emit(self, *a):
        self.gesendet.append(a)
        if self.blockiert:
            return
        for f in list(self.slots):
            try:
                f(*a)
            except TypeError:
                # Qt laesst ueberzaehlige Argumente weg
                f()


class pyqtSignal:
    def __init__(self, *typen, **kw):
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, owner):
        if obj is None:
            return self
        d = obj.__dict__.setdefault('_signale', {})
        if self.name not in d:
            d[self.name] = Sig()
        return d[self.name]


class Null:
    """Tut nichts, vertraegt alles, verhaelt sich wie 0 und wie leer."""
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return Null()
    def __getattr__(self, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        return Null()
    def __bool__(self): return False
    def __int__(self): return 0
    def __float__(self): return 0.0
    def __index__(self): return 0
    def __str__(self): return ""
    def __iter__(self): return iter(())
    def __len__(self): return 0
    def __add__(self, o): return o
    __radd__ = __add__
    def __sub__(self, o): return -o if isinstance(o, (int, float)) else Null()
    def __rsub__(self, o): return o
    def __mul__(self, o): return 0
    __rmul__ = __mul__
    def __truediv__(self, o): return 0
    def __rtruediv__(self, o): return 0
    def __floordiv__(self, o): return 0
    def __or__(self, o): return self
    __ror__ = __or__
    __and__ = __or__
    def __lt__(self, o): return 0 < o
    def __gt__(self, o): return 0 > o
    def __le__(self, o): return 0 <= o
    def __ge__(self, o): return 0 >= o
    def __eq__(self, o): return self is o
    def __hash__(self): return id(self)
    def __getitem__(self, k): return Null()
    def __setitem__(self, k, v): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _MarkenMeta(type):
    """Klassenattribute wie Qt.AlignCenter: je Name eine feste Marke."""
    def __getattr__(cls, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = Marke(f"{cls.__name__}.{n}")
        setattr(cls, n, m)
        return m


class Marke(Null):
    def __init__(self, name=""): self.name = name
    def __repr__(self): return f"<{self.name}>"
    def __bool__(self): return True
    def __eq__(self, o): return self is o
    def __hash__(self): return id(self)
