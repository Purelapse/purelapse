# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Bauanleitung fuer Purelapse (Einzeldatei).
# Gebaut wird mit:  ./build.sh
import sys
from PyInstaller.utils.hooks import collect_data_files

# ffmpeg-Programm aus dem Paket imageio-ffmpeg mit einpacken
ffmpeg_files = collect_data_files('imageio_ffmpeg', include_py_files=False)

a = Analysis(
    ['purelapse_main.py'],
    pathex=[],
    binaries=[],
    datas=ffmpeg_files,
    hiddenimports=['astral', 'astral.sun', 'imageio_ffmpeg', 'purelapse_engines',
                   'purelapse_texte', 'purelapse_design'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Nicht benoetigte, grosse Module weglassen
    excludes=['tkinter', 'matplotlib', 'IPython', 'jupyter', 'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False,
    optimize=0,
)
# libstdc++/libgcc NICHT mitliefern: jeder Mint-Rechner hat sie, und eine
# mitgelieferte aeltere Version kann auf neueren Systemen die Grafiktreiber stoeren.
_SYSTEM_LIBS = ('libstdc++.so', 'libgcc_s.so')
a.binaries = [b for b in a.binaries if not b[0].split('/')[-1].startswith(_SYSTEM_LIBS)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Purelapse',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows: Symbol der .exe - ein .ico mit eigens gerechneten kleinen
    # Groessen (16-256 px, aus grafik/icon_bauen.py)
    icon=('docs/assets/purelapse.ico' if sys.platform.startswith('win') else None),
)
