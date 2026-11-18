#!/usr/bin/env bash
# Raeumt den Purelapse-Ordner auf: alte Staende, Sicherungskopien und
# alte Bauergebnisse wandern nach archiv/<Datum>/. Geloescht wird nichts
# ausser __pycache__ (entsteht beim naechsten Start von selbst neu).
# Im Ordner bleibt die aktuelle Version mit allem, was zum Starten und
# Bauen noetig ist. Mehrfaches Ausfuehren schadet nicht.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
ZIEL="archiv/$(date +%Y-%m-%d)"
mkdir -p "$ZIEL/dist"

verschiebe() {
    for f in "$@"; do
        if [ -e "$f" ]; then
            mv -n -- "$f" "$ZIEL/${f}"
            echo "  archiviert: $f"
        fi
    done
}

echo "Aufraeumen nach $ZIEL ..."
# Alte Staende und Sicherungskopien des Programms
verschiebe "purelapse_main (Kopie).py" purelapse_main_2142.py \
    purelapse_main.py.orig purelapse_main.py.vor-codec purelapse_main.py.vor-ui-umbau
# Alter Einzeldatei-Bau (ersetzt durch build_appimage.sh) und sein Protokoll
verschiebe build.sh build.log
# Bauergebnisse: nur das neueste AppImage bleibt in dist/
if [ -d dist ]; then
    [ -e dist/Purelapse ] && mv -n dist/Purelapse "$ZIEL/dist/" && echo "  archiviert: dist/Purelapse"
    neuestes="$(ls -1 dist/Purelapse-*.AppImage 2>/dev/null | sort -V | tail -n 1 || true)"
    for f in dist/Purelapse-*.AppImage; do
        [ -e "$f" ] || continue
        if [ "$f" != "$neuestes" ]; then
            mv -n -- "$f" "$ZIEL/dist/" && echo "  archiviert: $f"
        fi
    done
    [ -n "$neuestes" ] && echo "  behalten:   $neuestes"
fi
rm -rf __pycache__
rmdir "$ZIEL/dist" 2>/dev/null || true
echo "Fertig."
