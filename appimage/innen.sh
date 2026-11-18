#!/usr/bin/env bash
# Laeuft IM Bau-Container (siehe build_appimage.sh), nicht direkt aufrufen.
set -euo pipefail
cd /src
VERSION="${VERSION:-unbekannt}"
rm -rf /tmp/build /tmp/dist /tmp/AppDir
/opt/venv/bin/python -m PyInstaller --noconfirm --clean \
    --workpath /tmp/build --distpath /tmp/dist appimage/purelapse_appimage.spec
mkdir -p /tmp/AppDir/usr/lib
cp -a /tmp/dist/Purelapse /tmp/AppDir/usr/lib/purelapse
install -m 755 appimage/AppRun /tmp/AppDir/AppRun
install -m 644 appimage/purelapse.desktop /tmp/AppDir/purelapse.desktop
install -m 644 appimage/purelapse.png /tmp/AppDir/purelapse.png
ln -sf purelapse.png /tmp/AppDir/.DirIcon
# Das AppImage startet spaeter unter anderen Benutzern: alles muss fuer
# alle lesbar sein, Ordner und Programme auch ausfuehrbar. Die Quelldateien
# koennen strengere Rechte haben (z. B. 0600 nach einem Kopiervorgang).
chmod -R a+rX /tmp/AppDir
chmod a+rx /tmp/AppDir/AppRun /tmp/AppDir/usr/lib/purelapse/Purelapse
mkdir -p dist
ZIEL="dist/Purelapse-${VERSION}-x86_64.AppImage"
rm -f "$ZIEL"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 /opt/appimagetool --no-appstream /tmp/AppDir "$ZIEL"
chmod +x "$ZIEL"
