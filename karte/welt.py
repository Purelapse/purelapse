# Erzeugt docs/assets/welt.svg: Landflaechen als Punkteraster, abstandstreue
# Zylinderprojektion (x = Laenge, y = Breite), Breiten 80 N bis 56 S.
import json, numpy as np
from matplotlib.path import Path
import sys
QUELLE = sys.argv[1] if len(sys.argv) > 1 else 'dist/land-110m.json'
ZIEL = sys.argv[2] if len(sys.argv) > 2 else 'docs/assets/welt.svg'
t = json.load(open(QUELLE))
sx, sy = t['transform']['scale']; tx, ty = t['transform']['translate']
arcs = []
for a in t['arcs']:
    p = np.cumsum(np.array(a, dtype=np.float64), axis=0)
    arcs.append(np.c_[p[:, 0] * sx + tx, p[:, 1] * sy + ty])
def ring(idx):
    pts = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return np.array(pts)
polys = []
for poly in t['objects']['land']['geometries'][0]['arcs']:
    polys.append([ring(r) for r in poly])
NORD, SUED, SCHRITT = 80.0, -56.0, 2.0
W = 360.0 / SCHRITT; H = (NORD - SUED) / SCHRITT
lons = np.arange(-180 + SCHRITT / 2, 180, SCHRITT)
lats = np.arange(NORD - SCHRITT / 2, SUED, -SCHRITT)
LO, LA = np.meshgrid(lons, lats)
pkt = np.c_[LO.ravel(), LA.ravel()]
land = np.zeros(len(pkt), bool)
def innen(r):
    # Ringe ueber die Datumsgrenze: Laengen stetig machen und auch um
    # +-360 Grad verschoben pruefen, sonst entsteht ein Streifen um die Welt.
    r = np.c_[np.unwrap(r[:, 0], period=360), r[:, 1]]
    treffer = np.zeros(len(pkt), bool)
    for v in (-360, 0, 360):
        treffer |= Path(r + [v, 0]).contains_points(pkt)
    return treffer
for poly in polys:
    aussen = innen(poly[0])
    for loch in poly[1:]:
        aussen &= ~innen(loch)
    land |= aussen
# Einheiten: 1 Einheit = 1 Grad; viewBox 0 0 360 136
xs = (pkt[land, 0] + 180).round(2); ys = (NORD - pkt[land, 1]).round(2)
d = "".join(f"M{x:g} {y:g}h0" for x, y in zip(xs, ys))
svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 136">'
       f'<path d="{d}" stroke="#485268" stroke-width="1.2" stroke-linecap="round" fill="none"/></svg>\n')
open(ZIEL, 'w').write(svg)
print(land.sum(), 'Punkte,', len(svg), 'Bytes')
