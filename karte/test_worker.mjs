import { DatabaseSync } from "node:sqlite";
import worker from "./worker.js";
const db = new DatabaseSync(":memory:");
const DB = { prepare(sql) { let args = []; const st = {
  bind(...a) { args = a; return st; },
  async all() { return { results: db.prepare(sql).all(...args) }; },
  async first() { return db.prepare(sql).get(...args) ?? null; },
  async run() { const r = db.prepare(sql).run(...args); return { meta: { changes: r.changes } }; } }; return st; } };
const env = { DB, TURNSTILE_SECRET: "geheim", ADMIN_TOKEN: "admin123", ERLAUBT: "https://purelapse.org" };
let tsOk = true;
globalThis.fetch = async (u, o) => ({ json: async () => {
  if (o.body.get("secret") !== "geheim") return { success: false, "error-codes": ["invalid-input-secret"] };
  return o.body.get("response") === "tok" && tsOk ? { success: true } : { success: false, "error-codes": ["invalid-input-response"] }; } });
let ok = 0, fehl = 0;
const pruef = (b, t) => { if (b) ok++; else { fehl++; console.log("FEHLER:", t); } };
async function rufe(method, pfad, body, kopf = {}, ip = "1.2.3.4", land = "DE") {
  const r = new Request("https://w.example" + pfad, { method, body: body ? JSON.stringify(body) : undefined,
    headers: { "Origin": "https://purelapse.org", "CF-Connecting-IP": ip, "Content-Type": "application/json", ...kopf } });
  r.cf = { country: land };
  const a = await worker.fetch(r, env);
  return { s: a.status, d: a.status === 204 ? null : await a.json(), h: a.headers };
}
const gut = { lat: 50.3712, lon: 11.9411, reaktion: "laeuft", engine: "rt", zustimmung: true, token: "tok" };
let r = await rufe("GET", "/pins"); pruef(r.s === 200 && r.d.pins.length === 0, "leer");
pruef(r.h.get("Access-Control-Allow-Origin") === "https://purelapse.org", "CORS");
r = await rufe("OPTIONS", "/pins"); pruef(r.s === 204, "OPTIONS");
r = await rufe("POST", "/pins", gut); pruef(r.s === 201 && r.d.id === 1, "Pin setzen " + JSON.stringify(r));
r = await rufe("GET", "/pins"); const p = r.d.pins[0];
pruef(p.lat === 50.5 && p.lon === 12 && p.land === "DE" && p.reaktion === "laeuft" && /^\d{4}-\d\d$/.test(p.monat), "gerundet " + JSON.stringify(p));
pruef(!("ip" in p) && Object.keys(p).length === 7, "nur erlaubte Felder");
r = await rufe("POST", "/pins", gut); pruef(r.s === 429 && r.d.fehler === "heute", "zweiter Pin am selben Tag");
r = await rufe("POST", "/pins", gut, {}, "5.6.7.8", "AT"); pruef(r.s === 201, "anderer Besucher");
r = await rufe("POST", "/pins", { ...gut, zustimmung: false }, {}, "9.9.9.1"); pruef(r.s === 400, "ohne Zustimmung");
r = await rufe("POST", "/pins", { ...gut, reaktion: "<script>" }, {}, "9.9.9.2"); pruef(r.s === 400, "falsche Reaktion");
r = await rufe("POST", "/pins", { ...gut, lat: 200 }, {}, "9.9.9.3"); pruef(r.s === 400, "falscher Ort");
r = await rufe("POST", "/pins", { ...gut, token: "falsch" }, {}, "9.9.9.4"); pruef(r.s === 403 && r.d.fehler === "pruefung" && r.d.codes[0] === "invalid-input-response", "Turnstile " + JSON.stringify(r.d));
env.TURNSTILE_SECRET = "falsch"; r = await rufe("POST", "/pins", gut, {}, "9.9.9.8"); env.TURNSTILE_SECRET = "geheim";
pruef(r.s === 403 && r.d.codes[0] === "invalid-input-secret", "falsches Secret wird benannt " + JSON.stringify(r.d));
r = await rufe("POST", "/pins", gut, { "Origin": "https://boese.example" }, "9.9.9.5"); pruef(r.s === 403, "fremde Herkunft");
r = await rufe("POST", "/pins", { ...gut, lat: 89.9, lon: -179.9 }, {}, "9.9.9.6"); pruef(r.s === 201, "Rand");
r = await rufe("GET", "/pins"); pruef(r.d.pins.at(-1).lat === 85 && r.d.pins.at(-1).lon === -180, "Rand begrenzt " + JSON.stringify(r.d.pins.at(-1)));
r = await rufe("DELETE", "/pins/1"); pruef(r.s === 403, "Loeschen ohne Token");
r = await rufe("DELETE", "/pins/1", null, { Authorization: "Bearer admin123" }); pruef(r.s === 200 && r.d.geaendert === 1, "Loeschen mit Token");
r = await rufe("GET", "/pins"); pruef(r.d.pins.length === 2 && !r.d.pins.some((x) => x.id === 1), "geloescht");
pruef(db.prepare("SELECT COUNT(*) n FROM pins WHERE id=1").get().n === 0, "wirklich aus der Datenbank");
pruef(db.prepare("SELECT COUNT(*) n FROM sperre").get().n === 3 && db.prepare("SELECT schluessel FROM sperre").all().every((z) => /^[0-9a-f]{64}$/.test(z.schluessel)), "Sperre nur als Hash");
db.prepare("UPDATE sperre SET tag='2000-01-01'").run();
r = await rufe("POST", "/pins", gut, {}, "9.9.9.7"); pruef(db.prepare("SELECT COUNT(*) n FROM sperre").get().n === 1, "alte Sperren geloescht");
r = await rufe("GET", "/gibtsnicht"); pruef(r.s === 404, "404");
const kaputt = new Request("https://w.example/pins", { method: "POST", body: "{kaputt", headers: { Origin: "https://purelapse.org" } });
pruef((await worker.fetch(kaputt, env)).status === 400, "kaputtes JSON");
console.log(`${ok} bestanden, ${fehl} fehlgeschlagen`);
