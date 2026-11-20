# Weltkarte der Nutzer

Cloudflare Worker mit D1-Datenbank, der die Pins der Karte auf purelapse.org
speichert. Keine Geheimnisse in diesem Ordner: Turnstile-Schlüssel und
Admin-Token liegen nur als Secrets im Worker.

- `worker.js` – der Worker (im Cloudflare-Dashboard einfügen)
- `test_worker.mjs` – Prüfung mit nachgebauter Datenbank: `node karte/test_worker.mjs`
  (Node 22.5 oder neuer)
- `welt.py` – erzeugt `docs/assets/welt.svg` aus den Natural-Earth-Umrissen
  (`world-atlas/land-110m.json`): `python3 karte/welt.py dist/land-110m.json docs/assets/welt.svg`

Die Webseite selbst: `docs/assets/karte.js`, Abschnitt `#karte` in
`docs/index.html` und `docs/en.html`.

Pin löschen (die Nummer steht im Hinweis des Pins auf der Karte):

    curl -X DELETE -H "Authorization: Bearer <ADMIN_TOKEN>" https://purelapse-karte.silvio-boenig.workers.dev/pins/<nummer>
