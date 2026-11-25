# -*- coding: utf-8 -*-
"""
Stellvertreter fuer rawpy.

Die Pruef-"RAWs" sind NumPy-Dateien mit linearen 16-Bit-Daten, nur mit
der Endung .NEF. postprocess() liefert daraus, was das echte rawpy fuer
die jeweiligen Schalter liefern wuerde.
"""
import numpy as np


class LibRawError(Exception):
    pass


class ThumbFormat:
    JPEG = 'jpeg'
    BITMAP = 'bitmap'


class _Raw:
    def __init__(self, pfad):
        try:
            with open(pfad, 'rb') as f:
                self.daten = np.load(f)
        except Exception as e:
            raise LibRawError(str(e))
        self.camera_whitebalance = [2.0, 1.0, 1.5, 0.0]
        # Farbmatrix XYZ -> Kamera-RGB (libraw cam_xyz, 4x3): die "Kamera"
        # sieht wie sRGB. Mit den Faktoren oben ergibt das Kunstlicht.
        self.rgb_xyz_matrix = np.array([[3.2404542, -1.5371385, -0.4985314],
                                        [-0.9692660, 1.8760108, 0.0415560],
                                        [0.0556434, -0.2040259, 1.0572252],
                                        [0.0, 0.0, 0.0]])

    white_level = 65535

    @property
    def raw_image_visible(self):
        """Sensordaten als Bayer-Mosaik (RGGB) aus dem linearen Bild."""
        d = self.daten
        m = d[..., 1].copy()
        m[0::2, 0::2] = d[0::2, 0::2, 0]
        m[1::2, 1::2] = d[1::2, 1::2, 2]
        return m

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def extract_thumb(self):
        raise LibRawError("kein eingebettetes Vorschaubild")

    def postprocess(self, **k):
        d = self.daten
        if k.get('output_bps', 8) == 16 and k.get('gamma') == (1, 1):
            return d.copy()
        # 8 Bit mit Anzeige-Kennlinie, wie rawpy es ohne Angaben liefert
        lin = d.astype(np.float64) / 65535.0
        if not k.get('no_auto_bright', False):
            lin = lin / max(1e-6, np.percentile(lin, 99))
        s = np.where(lin <= 0.0031308, 12.92 * lin,
                     1.055 * np.power(np.clip(lin, 0, 1), 1 / 2.4) - 0.055)
        return (np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8)


def imread(pfad):
    return _Raw(pfad)
