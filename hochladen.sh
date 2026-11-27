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
#     Name und Ort des Fotografen),
#   - eine bisher gefuellte Datei leer geworden ist (z. B. ein Video, dessen
#     Neuberechnung abgebrochen ist - die Webseite zeigte es sonst nicht mehr).
# Was nicht hochgeladen werden soll, regelt die .gitignore.
# Am Ende sagt es, wie es weitergeht - und, wenn die Versionsnummer noch
# kein Release hat, Schritt fuer Schritt, wie das Release veroeffentlicht wird.
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

# Leer gewordene Dateien
LEER=""
while IFS= read -r -d '' datei; do
    if [ -f "$datei" ] && [ ! -s "$datei" ]; then
        LEER="$LEER\n  $datei"
    fi
done < <(git diff --cached --name-only -z --diff-filter=M)
if [ -n "$LEER" ]; then
    git reset -q
    echo -e "ABBRUCH: Diese Dateien sind jetzt leer (0 Bytes):$LEER"
    echo "Vorige Fassung zurueckholen:  git show HEAD:<datei> > <datei>"
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

# ---------------------------------------------------------------- Wie weiter?
REPO="https://github.com/purelapse/purelapse"
VERSION="$(grep -m1 '^VERSION = ' purelapse_main.py | cut -d'"' -f2)"
TAG="v$VERSION"
APPIMAGE="dist/Purelapse-$VERSION-x86_64.AppImage"
NOTIZEN="dist/Release-$VERSION.md"
git fetch -q --tags origin 2>/dev/null || true

echo
echo "================================================================"
echo " Wie geht es weiter?"
echo "================================================================"
echo "1. Pruefung auf GitHub abwarten (Linux und Windows, ca. 10 Min.):"
echo "   $REPO/actions"
if [ "$ZWEIG" = "main" ]; then
    echo "2. Webseite: in 1-2 Minuten aktuell auf https://purelapse.org (Strg+F5)."
elif [ "$ZWEIG" = "windows" ]; then
    echo "2. Windows-Testfassung: Actions -> \"Windows-Paket\" -> unten bei Artifacts laden."
    echo "   Spaeter nach main holen:"
    echo "   git checkout main && git pull && git merge windows && git push origin main"
fi

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    echo
    echo "Kein Release noetig: $VERSION ist bereits veroeffentlicht."
    if grep -q '^## \[Unver' CHANGELOG.md; then
        echo "Die Aenderungen stehen im CHANGELOG unter [Unveroeffentlicht] und kommen"
        echo "mit der naechsten Version. Fuer ein neues Release Claude sagen:"
        echo "\"Bereite die naechste Version vor\" (Versionsnummer, CHANGELOG, Webseite, Release-Text)."
    fi
    exit 0
fi

echo
echo "RELEASE $VERSION ist vorbereitet, aber noch nicht veroeffentlicht:"
if [ "$ZWEIG" != "main" ]; then
    echo "   ACHTUNG: Ein Release gehoert auf main - erst nach main holen (siehe oben)."
fi
echo "3. Erst wenn die Pruefung gruen ist - AppImage bauen (einige Minuten):"
echo "   cd ~/Purelapse && bash build_appimage.sh"
[ -f "$NOTIZEN" ] || echo "   ACHTUNG: $NOTIZEN fehlt - Claude nach dem Release-Text fragen."
echo "4. Release anlegen - auf einem der beiden Wege:"
if command -v gh >/dev/null 2>&1; then
    echo "   a) im Terminal (gh ist installiert; beim allerersten Mal vorher: gh auth login):"
    echo "   cd ~/Purelapse && gh release create $TAG $APPIMAGE --prerelease --title \"Purelapse $VERSION\" --notes-file $NOTIZEN"
    echo "   b) im Browser:"
else
    echo "   Im Browser:"
fi
echo "   $REPO/releases/new?tag=$TAG&title=Purelapse%20$VERSION&prerelease=1"
echo "   - Tag und Titel sind schon eingetragen, Haken \"Set as a pre-release\" pruefen"
echo "   - Text: Inhalt von $NOTIZEN einfuegen"
echo "   - $APPIMAGE in das Feld fuer Dateien ziehen, dann \"Publish release\""
echo "5. Die Windows-.exe haengt GitHub nach 5-10 Minuten selbst an."
echo "6. Pruefen: $REPO/releases und auf purelapse.org beide Download-Knoepfe."
