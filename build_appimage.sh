#!/usr/bin/env bash
# Baut Purelapse als AppImage:  dist/Purelapse-<Version>-x86_64.AppImage
#
# Die Datei enthaelt alles (Python, Qt, OpenCV, NumPy, SciPy, rawpy,
# ffmpeg). Auf dem Zielrechner wird nur RawTherapee und/oder ART gebraucht.
# Gebaut wird in einem Ubuntu-22.04-Container; das Ergebnis laeuft auf
# Linux Mint 21 / Ubuntu 22.04 und allen neueren Versionen.
#
# Voraussetzung auf DIESEM Rechner: Docker und Internet (nur beim Bauen).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
VERSION="$(grep -m1 '^VERSION = ' purelapse_main.py | cut -d'"' -f2)"
echo "Baue Purelapse ${VERSION} als AppImage ..."
docker build -t purelapse-build .
docker run --rm -u "$(id -u):$(id -g)" -e VERSION="$VERSION" \
    -v "$PWD":/src purelapse-build bash /src/appimage/innen.sh
echo
echo "Fertig:  $(pwd)/dist/Purelapse-${VERSION}-x86_64.AppImage"
ls -lh "dist/Purelapse-${VERSION}-x86_64.AppImage"
