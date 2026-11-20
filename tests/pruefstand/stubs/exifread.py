# -*- coding: utf-8 -*-
"""Stellvertreter fuer exifread: die Aufnahmedaten gibt der Pruefstand vor."""
DATEN = {}       # Dateiname -> {'zeit','belichtung','iso','blende'}


class _Bruch:
    def __init__(self, wert):
        from fractions import Fraction
        f = Fraction(wert).limit_denominator(100000)
        self.num, self.den = f.numerator, f.denominator


class _Tag:
    def __init__(self, werte, text=None):
        self.values = werte
        self._text = text
    def __str__(self):
        return self._text if self._text is not None else str(self.values)


def process_file(f, details=False, **k):
    import os
    d = DATEN.get(os.path.basename(getattr(f, 'name', '')))
    if not d:
        return {}
    return {
        'EXIF ExposureTime': _Tag([_Bruch(d['belichtung'])]),
        'EXIF ISOSpeedRatings': _Tag([d['iso']]),
        'EXIF FNumber': _Tag([_Bruch(d['blende'])]),
        'Image DateTime': _Tag([d['zeit']], d['zeit']),
    }
