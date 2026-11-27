# Purelapse-Icon: exakte Geometrie (Einheit: 256er Raster), analytisch
# mit 16-fachem Ueberabtasten gerechnet - keine Saeume, saubere Alphakante.
# Die Horizontlinie liegt in jeder Groesse auf ganzen Bildpunkten, bis 24 px
# haben die Punkte mindestens 1,5 Bildpunkte Durchmesser.
# Benoetigt: numpy, Pillow.
import numpy as np
from PIL import Image

OBEN = np.array([106, 90, 198], float)    # #6A5AC6
UNTEN = np.array([241, 154, 58], float)   # #F19A3A
RADIUS = 56.0
PUNKTE = [(128.0, 82.0, 13.25),
          (98.1, 89.7, 11.05), (157.9, 89.7, 11.05),
          (73.1, 111.1, 8.85), (182.9, 111.1, 8.85),
          (56.6, 143.4, 6.65), (199.4, 143.4, 6.65)]
LINIE = (41.0, 215.0, 179.0, 4.0)         # x von, x bis, y, halbe Dicke (runde Enden)

def _masken(xs, ys, linie=LINIE, punkte=PUNKTE):
    X, Y = np.meshgrid(xs, ys)
    dx = np.maximum(np.maximum(RADIUS - X, X - (256 - RADIUS)), 0)
    dy = np.maximum(np.maximum(RADIUS - Y, Y - (256 - RADIUS)), 0)
    form = (dx * dx + dy * dy) <= RADIUS * RADIUS
    weiss = np.zeros_like(form)
    for px, py, r in punkte:
        weiss |= (X - px) ** 2 + (Y - py) ** 2 <= r * r
    x0, x1, ly, h = linie
    qx = np.clip(X, x0, x1)
    weiss |= (X - qx) ** 2 + (Y - ly) ** 2 <= h * h
    return form, weiss & form


def punkte_fuer(n):
    """Bei sehr kleinen Groessen (bis 24 px) wuerden die kleinsten Punkte zu
    blassem Grau verschwimmen: Mindestdurchmesser 1,5 Bildpunkte."""
    if n > 24:
        return PUNKTE
    rmin = 0.75 * 256.0 / n
    return [(x, y, max(r, rmin)) for x, y, r in PUNKTE]


def linie_fuer(n):
    """Die Horizontlinie auf ganze Bildpunkte gelegt: oben und unten eine
    harte Kante in jeder Groesse, statt einer halb deckenden Zeile."""
    x0, x1, ly, h = LINIE
    s = n / 256.0
    dicke = max(1, round(2 * h * s))
    oben = round((ly - h) * s)
    return (x0, x1, (oben + dicke / 2) / s, dicke / 2 / s)


def render(n, ss=16, dither=False):
    m = n * ss
    xs = (np.arange(m) + 0.5) * (256.0 / m)
    deck = np.zeros((n, n), np.float32)
    w = np.zeros((n, n), np.float32)
    schritt = max(1, 4096 // m)                   # Ausgabezeilen je Durchgang
    for z in range(0, n, schritt):
        z1 = min(n, z + schritt)
        ys = (np.arange(z * ss, z1 * ss) + 0.5) * (256.0 / m)
        form, weiss = _masken(xs, ys, linie_fuer(n), punkte_fuer(n))
        r = z1 - z
        deck[z:z1] = form.reshape(r, ss, n, ss).mean(axis=(1, 3))
        w[z:z1] = weiss.reshape(r, ss, n, ss).mean(axis=(1, 3))
    yy = ((np.arange(n) + 0.5) / n)[:, None, None]
    farbe = np.broadcast_to(OBEN + (UNTEN - OBEN) * yy, (n, n, 3)).copy()
    if dither and n >= 128:
        rng = np.random.default_rng(7)
        farbe += (rng.random((n, n, 1)) - rng.random((n, n, 1)))  # dreieckig, +-1 LSB
    anteil = np.divide(w, deck, out=np.zeros_like(w), where=deck > 0)[..., None]
    rgb = farbe * (1 - anteil) + 255.0 * anteil
    rgba = np.dstack([np.clip(np.round(rgb), 0, 255), np.round(deck * 255)]).astype(np.uint8)
    leer = rgba[..., 3] == 0
    rgba[leer, :3] = np.clip(np.round(farbe[leer]), 0, 255).astype(np.uint8)
    return Image.fromarray(rgba, 'RGBA')


def svg():
    teile = [f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}"/>' for x, y, r in PUNKTE]
    x0, x1, ly, h = LINIE
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="0" y2="256" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#6A5AC6"/>
      <stop offset="1" stop-color="#F19A3A"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="{RADIUS:g}" fill="url(#g)"/>
  <g fill="#FFFFFF">
    {chr(10).join("    " + t for t in teile).strip()}
    <path d="M{x0:g} {ly:g}H{x1:g}" stroke="#FFFFFF" stroke-width="{2*h:g}" stroke-linecap="round" fill="none"/>
  </g>
</svg>
'''

if __name__ == '__main__':
    # Aufruf im Projektordner:  python3 grafik/icon_bauen.py
    # Schreibt alle Icons an ihren Platz; dist/icon-<n>.png fuer andere Zwecke.
    import os
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    open('docs/assets/purelapse-icon.svg', 'w').write(svg())
    render(256).save('docs/assets/icon.png', optimize=True)
    render(64).save('docs/assets/favicon.png', optimize=True)
    render(256).save('appimage/purelapse.png', optimize=True)
    groessen = (16, 24, 32, 48, 64, 128, 256)
    bilder = {n: render(n) for n in groessen}
    bilder[256].save('docs/assets/purelapse.ico', sizes=[(n, n) for n in groessen],
                     append_images=[bilder[n] for n in groessen[:-1]])
    os.makedirs('dist', exist_ok=True)
    for n in (512, 1024):
        render(n).save(f'dist/icon-{n}.png', optimize=True)
    print('Icons geschrieben.')
