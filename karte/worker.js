// Purelapse – Weltkarte der Nutzer
// Cloudflare Worker mit D1-Datenbank (Bindung "DB").
//
// Einstellungen im Worker (Settings → Variables and Secrets):
//   TURNSTILE_SECRET  Secret   geheimer Schluessel des Turnstile-Widgets
//   ADMIN_TOKEN       Secret   langes Zufallswort zum Ausblenden von Pins
//   ERLAUBT           Text     erlaubte Herkunft, Standard https://purelapse.org
//
// Schnittstelle:
//   GET    /pins          alle sichtbaren Pins (oeffentlich, 60 s zwischengespeichert)
//   POST   /pins          neuen Pin setzen (Turnstile, Zustimmung, 1 je Besucher und Tag)
//   DELETE /pins/<id>     Pin endgueltig loeschen (Authorization: Bearer <ADMIN_TOKEN>)
//
// Datenschutz: Der Ort kommt schon gerundet aus dem Browser und wird hier
// noch einmal auf 0,5 Grad (etwa 50 km) gerundet. Die IP-Adresse wird nicht
// gespeichert - fuer die Sperre "ein Pin je Tag" nur ein Hash aus IP, Datum
// und geheimem Schluessel, der am naechsten Tag geloescht wird.

const RASTER = 0.5;
const REAKTIONEN = ["laeuft", "holygrail", "danke", "begeistert", "getueftelt"];
const ENGINES = ["art", "rt", "dt", "jpg", "andere"];
const PINS_JE_TAG_MAX = 300;          // Notbremse gegen Massen-Spam

const SCHEMA = `
CREATE TABLE IF NOT EXISTS pins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lat REAL NOT NULL, lon REAL NOT NULL,
  reaktion TEXT NOT NULL, engine TEXT NOT NULL,
  land TEXT,
  erstellt TEXT NOT NULL DEFAULT (datetime('now')),
  sichtbar INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sperre (schluessel TEXT PRIMARY KEY, tag TEXT NOT NULL);
`;
let schemaDa = false;

async function schemaAnlegen(env) {
  if (schemaDa) return;
  for (const satz of SCHEMA.split(";").map((s) => s.trim()).filter(Boolean)) {
    await env.DB.prepare(satz).run();
  }
  schemaDa = true;
}

function runden(wert, min, max) {
  const r = Math.round(wert / RASTER) * RASTER;
  return Math.min(max, Math.max(min, Number(r.toFixed(2))));
}

async function hash(text) {
  const daten = new TextEncoder().encode(text);
  const h = await crypto.subtle.digest("SHA-256", daten);
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function antwort(daten, status, kopf) {
  return new Response(JSON.stringify(daten), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...kopf },
  });
}

async function turnstileOk(env, token, ip) {
  if (!token || typeof token !== "string" || token.length > 4096) return false;
  const form = new FormData();
  form.append("secret", env.TURNSTILE_SECRET || "");
  form.append("response", token);
  if (ip) form.append("remoteip", ip);
  try {
    const r = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify",
      { method: "POST", body: form });
    const d = await r.json();
    return d.success === true;
  } catch (e) {
    return false;
  }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const erlaubt = (env.ERLAUBT || "https://purelapse.org").split(",").map((s) => s.trim());
    const herkunft = req.headers.get("Origin") || "";
    const cors = {
      "Access-Control-Allow-Origin": erlaubt.includes(herkunft) ? herkunft : erlaubt[0],
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Vary": "Origin",
    };
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

    try {
      await schemaAnlegen(env);

      // ---- alle Pins -------------------------------------------------
      if (url.pathname === "/pins" && req.method === "GET") {
        const { results } = await env.DB.prepare(
          "SELECT id, lat, lon, reaktion, engine, land, substr(erstellt, 1, 7) AS monat " +
          "FROM pins WHERE sichtbar = 1 ORDER BY id").all();
        return antwort({ pins: results }, 200, { ...cors, "Cache-Control": "public, max-age=60" });
      }

      // ---- neuer Pin -------------------------------------------------
      if (url.pathname === "/pins" && req.method === "POST") {
        if (!erlaubt.includes(herkunft)) return antwort({ fehler: "herkunft" }, 403, cors);
        let d;
        try {
          d = await req.json();
        } catch (e) {
          return antwort({ fehler: "daten" }, 400, cors);
        }
        const lat = Number(d && d.lat), lon = Number(d && d.lon);
        if (!d || d.zustimmung !== true || !Number.isFinite(lat) || !Number.isFinite(lon)
            || Math.abs(lat) > 90 || Math.abs(lon) > 180
            || !REAKTIONEN.includes(d.reaktion) || !ENGINES.includes(d.engine)) {
          return antwort({ fehler: "daten" }, 400, cors);
        }
        const ip = req.headers.get("CF-Connecting-IP") || "";
        if (!(await turnstileOk(env, d.token, ip))) return antwort({ fehler: "pruefung" }, 403, cors);

        const tag = new Date().toISOString().slice(0, 10);
        await env.DB.prepare("DELETE FROM sperre WHERE tag < ?").bind(tag).run();
        const schluessel = await hash(`${ip}|${tag}|${env.ADMIN_TOKEN || ""}`);
        const schon = await env.DB.prepare("SELECT 1 AS x FROM sperre WHERE schluessel = ?")
          .bind(schluessel).first();
        if (schon) return antwort({ fehler: "heute" }, 429, cors);
        const heute = await env.DB.prepare(
          "SELECT COUNT(*) AS n FROM pins WHERE substr(erstellt, 1, 10) = ?").bind(tag).first();
        if (heute && heute.n >= PINS_JE_TAG_MAX) return antwort({ fehler: "voll" }, 429, cors);

        const land = (req.cf && typeof req.cf.country === "string" && /^[A-Z]{2}$/.test(req.cf.country))
          ? req.cf.country : null;
        const neu = await env.DB.prepare(
          "INSERT INTO pins (lat, lon, reaktion, engine, land) VALUES (?, ?, ?, ?, ?) RETURNING id")
          .bind(runden(lat, -60, 85), runden(lon, -180, 180), d.reaktion, d.engine, land).first();
        await env.DB.prepare("INSERT INTO sperre (schluessel, tag) VALUES (?, ?)").bind(schluessel, tag).run();
        return antwort({ ok: true, id: neu ? neu.id : null }, 201, cors);
      }

      // ---- Pin loeschen (nur mit ADMIN_TOKEN) ------------------------
      const m = url.pathname.match(/^\/pins\/(\d+)$/);
      if (m && req.method === "DELETE") {
        const auth = req.headers.get("Authorization") || "";
        if (!env.ADMIN_TOKEN || auth !== `Bearer ${env.ADMIN_TOKEN}`) {
          return antwort({ fehler: "verboten" }, 403, cors);
        }
        const r = await env.DB.prepare("DELETE FROM pins WHERE id = ?").bind(Number(m[1])).run();
        return antwort({ ok: true, geaendert: r.meta ? r.meta.changes : null }, 200, cors);
      }

      return antwort({ fehler: "unbekannt" }, 404, cors);
    } catch (e) {
      return antwort({ fehler: "intern" }, 500, cors);
    }
  },
};
