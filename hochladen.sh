#!/usr/bin/env bash
# Purelapse hochladen: pruefen, dann committen und pushen.
#
#   bash hochladen.sh "Commit-Nachricht"
#
# Bricht ab, wenn
#   - keine Nachricht angegeben ist,
#   - eine Pruefung fehlschlaegt (tests/alle.py),
#   - eine Datei ueber 50 MB hochgeladen wuerde (GitHub warnt ab 50 MB und
#     lehnt ab 100 MB ab),
#   - eine Bild-XMP ausserhalb von tests/daten dabei ist (darin stehen
#     Name und Ort des Fotografen).
# Was nicht hochgeladen werden soll, regelt die .gitignore.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

GRENZE_MB=50
NACHRICHT="${1:-}"
if [ -z "$NACHRICHT" ]; then
    echo "Bitte eine Commit-Nachricht angeben:  purelapse-push \"Was sich geaendert hat\""
    exit 1
fi

ZWEIG="$(git rev-parse --abbrev-ref HEAD)"
echo "== Zweig: $ZWEIG"

# Ablaufdateien, die Claude nach dist/ legt (dorthin darf es nicht direkt schreiben)
for f in dist/pruefung.yml dist/windows.yml; do
    if [ -f "$f" ]; then
        mv "$f" .github/workflows/
        echo "== $(basename "$f") nach .github/workflows/ verschoben"
    fi
done

echo "== Pruefungen laufen (einige Minuten) ..."
if ! python3 tests/alle.py; then
    echo
    echo "ABBRUCH: Pruefungen fehlgeschlagen - nichts wurde hochgeladen."
    exit 1
fi

git add -A

# Grosse Dateien
ZU_GROSS=""
while IFS= read -r -d '' datei; do
    [ -f "$datei" ] || continue
    groesse=$(stat -c %s "$datei")
    if [ "$groesse" -gt $((GRENZE_MB * 1024 * 1024)) ]; then
        ZU_GROSS="$ZU_GROSS\n  $datei ($((groesse / 1024 / 1024)) MB)"
    fi
done < <(git diff --cached --name-only -z --diff-filter=AM)
if [ -n "$ZU_GROSS" ]; then
    git reset -q
    echo -e "ABBRUCH: Dateien ueber $GRENZE_MB MB:$ZU_GROSS"
    echo "Nichts wurde hochgeladen."
    exit 1
fi

# Bild-XMPs mit persoenlichen Daten
XMP=$(git diff --cached --name-only --diff-filter=AM | grep -iE '\.xmp$' | grep -v '^tests/daten/' || true)
if [ -n "$XMP" ]; then
    git reset -q
    echo "ABBRUCH: XMP-Dateien ausserhalb von tests/daten:"
    echo "$XMP" | sed 's/^/  /'
    echo "Nichts wurde hochgeladen."
    exit 1
fi

if git diff --cached --quiet; then
    echo "Keine Aenderungen - nichts hochzuladen."
    exit 0
fi

echo "== Wird hochgeladen:"
git diff --cached --stat
git commit -q -m "$NACHRICHT"
git push origin "$ZWEIG"
echo
echo "Fertig: \"$NACHRICHT\" ist auf GitHub ($ZWEIG)."
