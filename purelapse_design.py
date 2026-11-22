# -*- coding: utf-8 -*-
"""
Purelapse - Erscheinungsbild: Farbschemata, Stylesheet, Symbole

Teil von Purelapse. Copyright (C) 2026 slvobng.
Lizenz: GNU General Public License v3 oder spaeter (siehe LICENSE).
"""
import os
import math
import shutil
import tempfile

import cv2
import numpy as np


# ==========================================================================
#  ERSCHEINUNGSBILD
# ==========================================================================
THEMES = {
    'dark': {
        # Nach dem Vorbild von DaVinci Resolve: rein neutrale Grautoene ohne
        # Blaustich, in drei Stufen - Fenster, Flaeche, Bedienelement. Die
        # Trennlinien sind DUNKLER als die Flaechen: Bereiche wirken dadurch
        # eingelassen statt umrandet, und viele Knoepfe bleiben ruhig.
        # Weiss ist fuer Wichtiges reserviert, Beschriftungen sind gedaempft.
        # Farbe tragen nur schmale Linien, der Hauptknopf und die Zustaende.
        'bg': "#1a1a1a", 'panel': "#222222", 'panel2': "#2b2b2b",
        'hover': "#343434", 'border': "#121212", 'border2': "#3b3b3b",
        'text': "#d4d4d4", 'dim': "#8e8e8e", 'faint': "#646464",
        'accent': "#5b9cf6", 'accent_hi': "#7db1f8", 'accent_text': "#0d1117",
        'warn': "#e0a04a", 'ok': "#5bb67a", 'err': "#e8787a",
        # Eine Farbe je Arbeitsschritt (siehe thema_mit_schritt) -
        # etwas gedaempft, damit sie neben dem Grau nicht schreien.
        'steps': {'load': "#649ce6", 'smooth': "#3aa697",
                  'keys': "#d4a73e", 'render': "#a28fea"},
        # Eingabefelder liegen dunkler als ihre Flaeche - eingelassen wie
        # die Felder in DaVinci, statt weiss umrandet.
        'feld': "#171717",
        'log_bg': "#141414", 'log_fg': "#c4c4c4",
        'graph_bg': "#1c1c1c", 'gallery': "#1d1d1d", 'sel': "#3a3a3a",
        # Schleier ueber dem Hauptfenster, solange ein Dialog davor steht
        # (Rot, Gruen, Blau, Deckkraft 0..255)
        'schleier': (0, 0, 0, 140),
        'curves': {'raw': "#a8b0bb", 'target': "#ff9800", 'wb': "#4fc3f7",
                   'ev': "#f06fd0", 'interval': "#66d97e", 'clip': "#ff5252",
                   'residual': "#ffffff", 'kf': "#ffee58", 'sun': "#ba68c8"},
    },
    'light': {
        # Weisser Hintergrund, graue Gruppen, weisse Eingabefelder -
        # dadurch treten die Gruppen als Flaeche hervor.
        'bg': "#ffffff", 'panel': "#eef1f6", 'panel2': "#ffffff",
        'hover': "#f3f6fa", 'border': "#d5dbe5", 'border2': "#b9c2cf",
        'text': "#1b2027", 'dim': "#5f6975", 'faint': "#8b95a2",
        'accent': "#1f7ad4", 'accent_hi': "#2f8ae4", 'accent_text': "#ffffff",
        'warn': "#a55f00", 'ok': "#1f7a45", 'err': "#b3261e",
        'steps': {'load': "#1b6fc2", 'smooth': "#0b7d73",
                  'keys': "#8a6400", 'render': "#6a3fc4"},
        'log_bg': "#f7f9fc", 'log_fg': "#27303b",
        'graph_bg': "#ffffff", 'gallery': "#f4f6fa", 'sel': "#cfe2f7",
        'schleier': (16, 22, 32, 100),
        'curves': {'raw': "#6b7480", 'target': "#e65100", 'wb': "#0277bd",
                   'ev': "#9c27b0", 'interval': "#2e7d32", 'clip': "#c62828",
                   'residual': "#37474f", 'kf': "#b28704", 'sun': "#7b1fa2"},
    },
}

# ==========================================================================
#  FARBE JE ARBEITSSCHRITT
#
#  Jeder Schritt der Schrittleiste hat seine eigene Farbe. Sie ersetzt die
#  Akzentfarbe des Farbschemas - alles, was bisher blau war (Hauptknopf,
#  aktiver Schritt, Rahmen des angeklickten Feldes, Fortschrittsbalken),
#  traegt dann die Farbe des Schritts. So sieht man ohne zu lesen, ob man
#  bei "Bilder laden" oder bei "Helligkeit glaetten" steht.
#
#    Bilder laden          Blau     wie bisher
#    Helligkeit glaetten   Tuerkis
#    Keyframes             Gold     dieselbe Farbe wie die Keyframe-Sterne
#    Video rendern         Violett
#
#  Gruen und Orange bleiben frei: sie bedeuten im Programm bereits
#  "erledigt" und "Warnung".
# ==========================================================================
def _rgb(hexfarbe):
    h = str(hexfarbe).lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def farbe_mischen(a, b, anteil):
    """Mischt Farbe a mit dem Anteil 'anteil' von Farbe b."""
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{int(round(x + (y - x) * anteil)):02x}"
                         for x, y in zip(ra, rb))


def leuchtdichte(hexfarbe):
    """Relative Leuchtdichte nach WCAG, 0 (schwarz) bis 1 (weiss)."""
    werte = []
    for v in _rgb(hexfarbe):
        c = v / 255.0
        werte.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * werte[0] + 0.7152 * werte[1] + 0.0722 * werte[2]


def kontrast(a, b):
    """Kontrastverhaeltnis zweier Farben nach WCAG, 1 bis 21."""
    la, lb = leuchtdichte(a), leuchtdichte(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def kontrast_text(hintergrund):
    """Dunkle oder helle Schrift - je nachdem, was besser lesbar ist."""
    dunkel, hell = "#0d1117", "#ffffff"
    return dunkel if kontrast(hintergrund, dunkel) >= kontrast(hintergrund, hell) else hell


def thema_mit_schritt(thema, schritt):
    """
    Das Farbschema mit der Farbe des Arbeitsschritts als Akzent.

    Die Schriftfarbe auf dem Akzent wird gerechnet und nicht aus der
    Tabelle genommen: Gold braucht dunkle Schrift, Violett helle, und das
    soll nicht davon abhaengen, dass jemand beim Aendern einer Farbe an
    die zweite denkt.
    """
    t = dict(THEMES.get(thema, THEMES['dark']))
    farbe = t.get('steps', {}).get(schritt)
    if farbe:
        t['accent'] = farbe
        t['accent_hi'] = farbe_mischen(farbe, "#ffffff", 0.18)
        t['accent_text'] = kontrast_text(farbe)
    return t


# ==========================================================================
#  KLEINE BILDER FUER BEDIENELEMENTE
#
#  Ein Stylesheet kann weder einen Pfeil noch einen Haken zeichnen - es
#  kann nur Bilddateien einbinden. Der Pfeil der Auswahlfelder war bisher
#  ein Trick mit Rahmenlinien, den Qt als kleinen Balken darstellt, und
#  ein angekreuztes Kaestchen war nur eine gefuellte Flaeche.
#
#  Die Bilder entstehen beim Start in einem eigenen Arbeitsordner, in den
#  Farben des Schemas, und verschwinden beim Beenden wieder.
# ==========================================================================
_UI_BILD_ORDNER = None


def _ui_ordner():
    global _UI_BILD_ORDNER
    if _UI_BILD_ORDNER is None or not os.path.isdir(_UI_BILD_ORDNER):
        import atexit
        _UI_BILD_ORDNER = tempfile.mkdtemp(prefix="purelapse_ui_")
        atexit.register(shutil.rmtree, _UI_BILD_ORDNER, True)
    return _UI_BILD_ORDNER


def ui_bild(form, farbe):
    """
    Pfad zu einem kleinen Bild in der gewuenschten Farbe.

    form: 'pfeil_ab', 'pfeil_auf', 'haken', 'punkt'
    Gezeichnet wird achtfach vergroessert und dann verkleinert - das
    ergibt glatte Kanten. Rueckgabe "" wenn es nicht gelingt; das
    Bedienelement bleibt dann einfach ohne Bild.
    """
    masse = {'pfeil_ab': (10, 6), 'pfeil_auf': (10, 6),
             'haken': (11, 11), 'punkt': (7, 7),
             'stern_voll': (18, 18), 'stern_leer': (18, 18)}
    if form not in masse:
        return ""
    try:
        pfad = os.path.join(_ui_ordner(),
                            f"{form}_{str(farbe).lstrip('#')}.png")
        if os.path.exists(pfad):
            return pfad.replace("\\", "/")
        b, h = masse[form]
        f = 8
        maske = np.zeros((h * f, b * f), dtype=np.uint8)
        def pkt(*xy):
            return np.array([[int(round(x * f)), int(round(y * f))]
                             for x, y in xy], dtype=np.int32)
        if form == 'pfeil_ab':
            cv2.polylines(maske, [pkt((1.2, 1.2), (5.0, 4.8), (8.8, 1.2))],
                          False, 255, int(1.5 * f), cv2.LINE_AA)
        elif form == 'pfeil_auf':
            cv2.polylines(maske, [pkt((1.2, 4.8), (5.0, 1.2), (8.8, 4.8))],
                          False, 255, int(1.5 * f), cv2.LINE_AA)
        elif form == 'haken':
            cv2.polylines(maske, [pkt((2.2, 5.8), (4.6, 8.0), (8.8, 3.0))],
                          False, 255, int(1.7 * f), cv2.LINE_AA)
        elif form in ('stern_voll', 'stern_leer'):
            ecken = []
            for i in range(10):
                radius = 7.6 if i % 2 == 0 else 3.3
                winkel = math.pi * (i / 5.0 - 0.5)
                ecken.append((9.0 + radius * math.cos(winkel),
                              9.6 + radius * math.sin(winkel)))
            if form == 'stern_voll':
                cv2.fillPoly(maske, [pkt(*ecken)], 255, cv2.LINE_AA)
            else:
                cv2.polylines(maske, [pkt(*ecken)], True, 255,
                              int(1.2 * f), cv2.LINE_AA)
        else:
            cv2.circle(maske, (b * f // 2, h * f // 2), int(3.0 * f), 255,
                       -1, cv2.LINE_AA)
        klein = cv2.resize(maske, (b, h), interpolation=cv2.INTER_AREA)
        r, g, bl = _rgb(farbe)
        bild = np.zeros((h, b, 4), dtype=np.uint8)
        bild[..., 0], bild[..., 1], bild[..., 2] = bl, g, r
        bild[..., 3] = klein
        ok, daten = cv2.imencode(".png", bild)
        if not ok:
            return ""
        daten.tofile(pfad)
        return pfad.replace("\\", "/")
    except Exception:
        return ""


IKON_PX = 36          # gezeichnet in doppelter Groesse: scharf auf HiDPI
IKON_GROESSE = 18     # angezeigt in logischen Pixeln


def _ikon_bogen(mx, my, r, von, bis, schritte=48):
    """Punkte eines Kreisbogens (Grad, im Uhrzeigersinn - y zeigt nach unten)."""
    return [(mx + r * math.cos(math.radians(von + (bis - von) * i / schritte)),
             my + r * math.sin(math.radians(von + (bis - von) * i / schritte)))
            for i in range(schritte + 1)]


def ui_ikon(form, farbe):
    """
    Symbol fuer einen Knopf, als PNG in der gewuenschten Farbe.

    form: 'ordner', 'neu_lesen', 'zuruecksetzen', 'einstellungen'
    Gezeichnet in einem 24er-Raster mit 2er Strichstaerke (wie die
    ueblichen Linien-Symbolsaetze), achtfach ueberabgetastet und auf
    IKON_PX verkleinert. Rueckgabe "" wenn es nicht gelingt; der Knopf
    zeigt dann seinen Text.
    """
    if form not in ('ordner', 'neu_lesen', 'zuruecksetzen', 'einstellungen'):
        return ""
    try:
        pfad = os.path.join(_ui_ordner(),
                            f"ikon_{form}_{str(farbe).lstrip('#')}.png")
        if os.path.exists(pfad):
            return pfad.replace("\\", "/")
        f = IKON_PX * 8 / 24.0                 # Bildpunkte je Rastereinheit
        g = IKON_PX * 8
        maske = np.zeros((g, g), dtype=np.uint8)
        dick = int(round(2.0 * f))

        def pkt(punkte):
            return np.array([[int(round(x * f)), int(round(y * f))]
                             for x, y in punkte], dtype=np.int32)

        def linie(punkte, zu=False):
            cv2.polylines(maske, [pkt(punkte)], zu, 255, dick, cv2.LINE_AA)

        def spitze(x, y, dx, dy, laenge=5.4, breite=3.6):
            """Gefuellte Pfeilspitze bei (x, y) in Richtung (dx, dy)."""
            n = math.hypot(dx, dy) or 1.0
            ux, uy = dx / n, dy / n
            sx, sy = x + ux * laenge * 0.55, y + uy * laenge * 0.55
            bx, by = x - ux * laenge * 0.45, y - uy * laenge * 0.45
            cv2.fillPoly(maske, [pkt([(sx, sy), (bx - uy * breite, by + ux * breite),
                                      (bx + uy * breite, by - ux * breite)])],
                         255, cv2.LINE_AA)

        if form == 'ordner':
            linie([(3, 6), (3.6, 4.6), (4.6, 4.2), (8.8, 4.2), (10.9, 6.6),
                   (19.4, 6.6), (20.4, 7.0), (21, 8), (21, 18.2), (20.4, 19.4),
                   (19.2, 19.8), (4.8, 19.8), (3.6, 19.4), (3, 18.2)], zu=True)
            linie([(3, 10), (21, 10)])
        elif form == 'neu_lesen':
            bogen = _ikon_bogen(12, 12.5, 8, 30, 312)
            linie(bogen)
            (x1, y1), (x2, y2) = bogen[-2], bogen[-1]
            spitze(x2, y2, x2 - x1, y2 - y1)
        elif form == 'zuruecksetzen':
            # Pfeil, der umkehrt: zurueck auf Anfang
            bogen = _ikon_bogen(14.5, 13, 6, -90, 90, 32)
            linie([(8, 7)] + bogen + [(7, 19)])
            spitze(5.2, 7, -1, 0)
        else:
            zaehne, aussen, innen = 8, 10.6, 7.9
            kranz = []
            for k in range(zaehne):
                mitte = 360.0 * k / zaehne
                for winkel, radius in ((-17, innen), (-9, aussen), (9, aussen), (17, innen)):
                    a = math.radians(mitte + winkel)
                    kranz.append((12 + radius * math.cos(a), 12 + radius * math.sin(a)))
            cv2.polylines(maske, [pkt(kranz)], True, 255, int(round(1.8 * f)), cv2.LINE_AA)
            cv2.circle(maske, (g // 2, g // 2), int(round(3.2 * f)), 255,
                       int(round(1.8 * f)), cv2.LINE_AA)
        klein = cv2.resize(maske, (IKON_PX, IKON_PX), interpolation=cv2.INTER_AREA)
        r, gr, bl = _rgb(farbe)
        bild = np.zeros((IKON_PX, IKON_PX, 4), dtype=np.uint8)
        bild[..., 0], bild[..., 1], bild[..., 2] = bl, gr, r
        bild[..., 3] = klein
        ok, daten = cv2.imencode(".png", bild)
        if not ok:
            return ""
        daten.tofile(pfad)
        return pfad.replace("\\", "/")
    except Exception:
        return ""


def _ikon_regeln(t):
    """Stylesheet-Regeln fuer die Symbolknoepfe. Ueber das Stylesheet,
    damit die Symbole beim Wechsel des Farbschemas mitwechseln."""
    regeln = [f"QPushButton[ikon=\"true\"] {{ padding: 5px 8px; min-width: 20px;"
              f" qproperty-iconSize: {IKON_GROESSE}px {IKON_GROESSE}px; }}"]
    for name, form in (('ikon_ordner', 'ordner'), ('ikon_neu', 'neu_lesen'),
                       ('ikon_reset', 'zuruecksetzen'), ('ikon_einst', 'einstellungen')):
        bild = ui_ikon(form, t['text'])
        if bild:
            regeln.append(f"QPushButton#{name} {{ qproperty-icon: url({bild}); }}")
    return "\n".join(regeln)


def _schritt_regeln(t):
    """
    Schrittknoepfe: das untere Fuenftel in der Farbe des Schritts. Vorher
    war es nur ein 3 px breiter Rand. Der aktive Schritt ist ganz gefuellt.
    Die Regeln stehen je Schritt einzeln, weil eine Regel mit [schritt=..]
    sonst die allgemeine :hover- bzw. :checked-Regel ueberstimmt.
    """
    regeln = []
    for key, farbe in t.get('steps', {}).items():
        # Wie die Seitenreiter in DaVinci: der Schritt bleibt grau, nur
        # eine schmale Linie unten traegt seine Farbe. Der aktive Schritt
        # wird heller und bekommt eine kraeftigere Linie - statt ganz
        # eingefaerbt zu werden.
        sel = f'QPushButton#step[schritt="{key}"]'
        regeln.append(f"{sel} {{ background: {t['panel']};"
                      f" border-bottom: 2px solid {farbe_mischen(t['panel'], farbe, 0.55)}; }}")
        regeln.append(f"{sel}:hover {{ background: {t['panel2']}; }}")
        regeln.append(f"{sel}:checked {{ background: {t['panel2']}; color: {t['text']};"
                      f" border: 1px solid {t['border']}; border-bottom: 3px solid {farbe}; }}")
    return "\n".join(regeln)


def build_stylesheet(t):
    """Flaches, ruhiges Erscheinungsbild fuer beide Farbschemata."""
    pfeil_ab = ui_bild('pfeil_ab', t['dim'])
    pfeil_auf = ui_bild('pfeil_auf', t['accent'])
    haken = ui_bild('haken', t['accent_text'])
    punkt = ui_bild('punkt', t['accent_text'])
    stern_voll = ui_bild('stern_voll', t['curves']['kf'])
    stern_leer = ui_bild('stern_leer', t['dim'])
    aktiv_bg = farbe_mischen(t['panel2'], t['accent'], 0.10)
    aktiv_rand = farbe_mischen(t['border'], t['accent'], 0.45)
    warn_bg = farbe_mischen(t['panel'], t['warn'], 0.16)
    feld = t.get('feld', t['panel2'])
    return f"""
    QWidget {{ background: {t['bg']}; color: {t['text']};
               font-size: 12px; }}
    QLabel {{ background: transparent; }}
    QGroupBox {{ background: {t['panel']}; border: 1px solid {t['border']};
                 border-radius: 4px; margin-top: 0px;
                 padding: 24px 6px 6px 6px; }}
    QGroupBox::title {{ subcontrol-origin: padding;
                        subcontrol-position: top left;
                        left: 15px; top: 9px; color: {t['dim']}; }}
    QLineEdit, QComboBox, QAbstractSpinBox {{
        background: {feld}; border: 1px solid {t['border']};
        border-radius: 3px; padding: 4px 7px; min-height: 18px;
        selection-background-color: {t['accent']};
        selection-color: {t['accent_text']}; }}
    QPlainTextEdit, QListWidget {{
        background: {feld}; border: 1px solid {t['border']};
        border-radius: 3px; padding: 4px 7px;
        selection-background-color: {t['accent']};
        selection-color: {t['accent_text']}; }}
    QListWidget#ordnerraster {{ padding: 2px; }}
    QListWidget#ordnerraster::item {{ background: {t['panel2']}; margin: 3px;
                                      border-radius: 2px; }}
    QListWidget#ordnerraster::item:hover {{ background: {t['hover']}; }}
    QLineEdit:hover, QComboBox:hover {{ border: 1px solid {t['border2']}; }}
    QLineEdit:focus, QComboBox:focus {{ border: 1px solid {t['accent']}; }}
    QLineEdit:read-only {{ color: {t['dim']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox::down-arrow {{ image: url({pfeil_ab}); width: 10px; height: 6px;
                             margin-right: 10px; }}
    QComboBox::down-arrow:on {{ image: url({pfeil_auf}); }}
    QComboBox:disabled, QLineEdit:disabled {{ color: {t['faint']};
        background: {t['panel']}; border: 1px solid {t['border']}; }}
    QComboBox QAbstractItemView {{ background: {t['panel2']};
        border: 1px solid {t['border2']}; padding: 3px;
        selection-background-color: {t['accent']}; selection-color: {t['accent_text']};
        outline: none; }}
    QPushButton {{ background: {t['panel2']}; border: 1px solid {t['border']};
                   border-radius: 3px; padding: 5px 11px; min-height: 16px; }}
    QPushButton:hover {{ background: {t['hover']}; border: 1px solid {t['border']}; }}
    QPushButton:pressed {{ background: {feld}; }}
    QPushButton:disabled {{ color: {t['faint']}; background: {t['panel']};
                            border: 1px solid {t['border']}; }}
    QPushButton#primary {{ background: {t['accent']}; color: {t['accent_text']};
                           border: 1px solid {t['accent']}; font-weight: bold;
                           padding: 6px 14px; }}
    QPushButton#primary:hover {{ background: {t['accent_hi']};
                                 border: 1px solid {t['accent_hi']}; }}
    QPushButton#primary:disabled {{ background: {t['panel2']}; color: {t['faint']};
                                    border: 1px solid {t['border']}; }}
    QPushButton#step {{ background: {t['panel']}; color: {t['dim']};
                        border: 1px solid {t['border']};
                        text-align: left; padding: 8px 12px; }}
    QPushButton#step[done="true"] {{ color: {t['ok']}; }}
    QPushButton#step:hover {{ color: {t['text']}; background: {t['panel2']}; }}
    QPushButton#step:checked {{ background: {t['panel2']}; color: {t['text']};
                                border: 1px solid {t['border']};
                                border-bottom: 3px solid {t['accent']}; font-weight: bold; }}
    QPushButton#step[done="true"]:checked {{ color: {t['text']}; }}
    {_schritt_regeln(t)}
    {_ikon_regeln(t)}
    QFrame#stepline {{ background: {t['accent']}; border: none;
                       min-height: 2px; max-height: 2px; }}
    QPushButton#toggle:checked {{ border: 1px solid {t['accent']};
                                  color: {t['accent']}; }}
    QPushButton::menu-indicator {{ subcontrol-position: right center;
                                   subcontrol-origin: padding; right: 8px; }}
    QLabel#steparrow {{ color: {t['faint']}; font-size: 18px; padding: 0 2px; }}
    QLabel#hint {{ color: {t['dim']}; }}
    QMenu {{ background: {t['panel2']}; border: 1px solid {t['border2']}; padding: 4px; }}
    QMenu::item {{ padding: 5px 18px; border-radius: 2px; }}
    QMenu::item:selected {{ background: {t['accent']}; color: {t['accent_text']}; }}
    QMenu::item:disabled {{ color: {t['faint']}; }}
    QTabWidget::pane {{ border: 1px solid {t['border']}; border-radius: 4px;
                        background: {t['panel']}; top: -1px; }}
    QTabBar::tab {{ background: transparent; color: {t['dim']};
                    padding: 6px 14px; margin-right: 2px;
                    border-top-left-radius: 3px; border-top-right-radius: 3px; }}
    QTabBar::tab:selected {{ background: {t['panel']}; color: {t['text']};
                             border: 1px solid {t['border']}; border-bottom: none; }}
    QTabBar::tab:hover:!selected {{ color: {t['text']}; }}
    QTabBar::tab:disabled {{ color: {t['faint']}; }}
    QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
    QCheckBox:disabled, QRadioButton:disabled {{ color: {t['faint']}; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px;
        border: 1px solid {t['border2']}; background: {feld}; }}
    QCheckBox::indicator {{ border-radius: 2px; }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border: 1px solid {t['accent']}; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {t['accent']}; border: 1px solid {t['accent']}; }}
    QCheckBox::indicator:checked {{ image: url({haken}); }}
    QRadioButton::indicator:checked {{ image: url({punkt}); }}
    QCheckBox#stern {{ spacing: 0px; }}
    QCheckBox#stern::indicator {{ width: 18px; height: 18px; border: none;
        background: transparent; image: url({stern_leer}); }}
    QCheckBox#stern::indicator:hover {{ border: none; image: url({stern_voll}); }}
    QCheckBox#stern::indicator:checked {{ border: none; background: transparent;
        image: url({stern_voll}); }}
    QPushButton#mini {{ padding: 6px 4px; min-width: 22px; }}
    QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{
        background: {t['faint']}; border: 1px solid {t['faint']}; }}
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
        border: 1px solid {t['border']}; background: {t['panel']}; }}
    QSlider::groove:horizontal {{ height: 4px; background: {t['border2']};
                                  border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {t['panel']};
        border: 2px solid {t['accent']}; width: 13px; height: 13px;
        margin: -6px 0; border-radius: 8px; }}
    QProgressBar {{ background: {feld}; border: none;
                    border-radius: 2px; min-height: 6px; max-height: 6px;
                    text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 2px; }}
    QFrame#statuscard {{ background: {t['panel']}; border: 1px solid {t['border']};
                         border-radius: 4px; }}
    QWidget#ladeschirm {{ background: rgba(0, 0, 0, 150); }}
    QLabel#statustitel {{ font-size: 14px; font-weight: bold; color: {t['text']}; }}
    QLabel#statuszeit {{ color: {t['dim']}; }}
    QLabel#prozent {{ font-weight: bold; color: {t['text']}; }}
    QFrame#ablauf {{ background: transparent; border: none; }}
    QFrame#phase {{ background: {t['panel2']}; border: 1px solid {t['border']};
                    border-radius: 3px; }}
    QFrame#phase[zustand="aktiv"] {{ background: {aktiv_bg};
                                     border: 1px solid {aktiv_rand}; }}
    QFrame#phasenstrich {{ background: {t['border2']}; border: none;
                           border-radius: 1px; min-height: 3px; max-height: 3px; }}
    QFrame#phasenstrich[zustand="fertig"] {{ background: {t['ok']}; }}
    QFrame#phasenstrich[zustand="aktiv"] {{ background: {t['accent']}; }}
    QFrame#phasenstrich[zustand="fehler"] {{ background: {t['err']}; }}
    QLabel#phasename {{ font-weight: bold; color: {t['text']}; }}
    QLabel#phasename[zustand="aktiv"] {{ color: {t['accent']}; }}
    QLabel#phasename[zustand="offen"] {{ color: {t['faint']}; }}
    QLabel#phasename[zustand="entfallen"] {{ color: {t['faint']}; }}
    QLabel#phasename[zustand="fehler"] {{ color: {t['err']}; }}
    QLabel#phasezeit {{ color: {t['dim']}; font-size: 11px; }}
    QLabel#phasezeit[zustand="offen"] {{ color: {t['faint']}; }}
    QLabel#phasezeit[zustand="entfallen"] {{ color: {t['faint']}; }}
    QLabel#badge {{ background: {t['panel2']}; color: {t['dim']};
                    border-radius: 3px; padding: 2px 8px; font-size: 11px; }}
    QLabel#badge[art="aktiv"] {{ background: {warn_bg}; color: {t['warn']};
                                 font-weight: bold; }}
    QLabel#badge[art="fest"] {{ color: {t['text']}; }}
    QFrame#trenner {{ background: {t['border']}; border: none;
                      min-height: 1px; max-height: 1px; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0; }}
    QScrollBar::handle {{ background: {t['border2']}; border-radius: 4px;
                          min-height: 28px; min-width: 28px; }}
    QScrollBar::handle:hover {{ background: {t['faint']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QScrollArea {{ background: transparent; border: none; }}
    QSplitter::handle {{ background: {t['border']}; }}
    QToolTip {{ background: {t['panel2']}; color: {t['text']};
                border: 1px solid {t['border2']}; padding: 5px; }}
    QDialog {{ background: {t['bg']}; }}
    """
