# -*- mode: python ; coding: utf-8 -*-
# PyInstaller-Bauanleitung fuer das AppImage (Ordner-Build, kein Einzeldatei-
# Build: das AppImage packt den Ordner selbst zusammen und startet so
# schneller, weil nichts erst ausgepackt werden muss).
# Gebaut wird mit:  ./build_appimage.sh
import os
from PyInstaller.utils.hooks import collect_data_files

PROJEKT = os.path.abspath(os.path.join(SPECPATH, '..'))

# ffmpeg-Programm aus dem Paket imageio-ffmpeg mit einpacken
ffmpeg_files = collect_data_files('imageio_ffmpeg', include_py_files=False)

a = Analysis(
    [os.path.join(PROJEKT, 'purelapse_main.py')],
    pathex=[PROJEKT],
    binaries=[],
    datas=ffmpeg_files,
    hiddenimports=['astral', 'astral.sun', 'imageio_ffmpeg', 'purelapse_engines',
                   'purelapse_texte', 'purelapse_design'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'IPython', 'jupyter', 'PyQt6', 'PySide2', 'PySide6'],
    noarchive=False,
    optimize=0,
)
# libstdc++/libgcc NICHT mitliefern: jeder Linux-Rechner hat sie, und eine
# mitgelieferte aeltere Version kann auf neueren Systemen die Grafiktreiber stoeren.
_SYSTEM_LIBS = ('libstdc++.so', 'libgcc_s.so')
a.binaries = [b for b in a.binaries if not b[0].split('/')[-1].startswith(_SYSTEM_LIBS)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Purelapse',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='Purelapse',
)
