/* Purelapse – Weltkarte der Nutzer.
   Pins kommen vom Cloudflare Worker (data-api), der Bot-Schutz Turnstile
   wird erst geladen, wenn jemand einen Pin setzen will. Der Ort wird hier
   im Browser auf 0,5 Grad gerundet, bevor er die Seite verlaesst. */
(function () {
  "use strict";
  var sek = document.getElementById("karte");
  if (!sek) return;
  var API = (sek.getAttribute("data-api") || "").replace(/\/$/, "");
  var SITEKEY = sek.getAttribute("data-sitekey") || "";
  var EN = (document.documentElement.lang || "de").slice(0, 2) === "en";
  var NORD = 80, SUED = -56, BREITE = 360, HOEHE = NORD - SUED, RASTER = 0.5;

  var T = EN ? {
    laden: "Loading map …", fehlerLaden: "The map could not be loaded right now.",
    keine: "No pins yet – be the first!",
    stats: function (n, l) { return "<b>" + n + "</b> " + (n === 1 ? "pin" : "pins") + (l ? " from <b>" + l + "</b> " + (l === 1 ? "country" : "countries") : ""); },
    tipp1: "Tap roughly where you are.", tipp2: "Now tap more precisely.",
    standort: "Use my approximate location", zurueck: "Back to world view", abbrechen: "Cancel",
    keinStandort: "Your browser did not share a location.",
    ok: "Thank you! Your pin is on the map.", heute: "A pin from you already arrived today – try again tomorrow.",
    pruefung: "The bot check did not succeed. Please try again.", voll: "Too many pins today – please try again tomorrow.",
    netz: "No connection to the map service. Please try again later.", daten: "Something was missing. Please check your choices.",
    pruefungLaden: "Loading the bot check …",
    reaktion: { laeuft: "Works", holygrail: "Holy grail done", danke: "Thanks", begeistert: "Thrilled", getueftelt: "Tinkering" },
    engine: { art: "ART", rt: "RawTherapee", dt: "darktable", jpg: "JPG", andere: "Other" },
    monat: function (m) { var d = new Date(m + "-01T12:00:00"); return isNaN(d) ? m : d.toLocaleDateString("en-GB", { month: "short", year: "numeric" }); },
    mehr: function (n) { return n + " pins here"; }
  } : {
    laden: "Karte wird geladen …", fehlerLaden: "Die Karte lässt sich gerade nicht laden.",
    keine: "Noch keine Pins – setz den ersten!",
    stats: function (n, l) { return "<b>" + n + "</b> " + (n === 1 ? "Pin" : "Pins") + (l ? " aus <b>" + l + "</b> " + (l === 1 ? "Land" : "Ländern") : ""); },
    tipp1: "Tippe ungefähr dorthin, wo du bist.", tipp2: "Jetzt genauer tippen.",
    standort: "Ungefähren Standort verwenden", zurueck: "Zurück zur Weltkarte", abbrechen: "Abbrechen",
    keinStandort: "Dein Browser hat keinen Standort freigegeben.",
    ok: "Danke! Dein Pin ist auf der Karte.", heute: "Von dir kam heute schon ein Pin – morgen wieder.",
    pruefung: "Die Prüfung gegen Bots hat nicht geklappt. Bitte noch einmal.", voll: "Heute sind schon sehr viele Pins gekommen – bitte morgen wieder.",
    netz: "Keine Verbindung zum Kartendienst. Bitte später noch einmal.", daten: "Es fehlt noch eine Angabe.",
    pruefungLaden: "Prüfung gegen Bots wird geladen …",
    reaktion: { laeuft: "Läuft", holygrail: "Holy Grail geschafft", danke: "Danke", begeistert: "Begeistert", getueftelt: "Am Tüfteln" },
    engine: { art: "ART", rt: "RawTherapee", dt: "darktable", jpg: "JPG", andere: "Andere" },
    monat: function (m) { var d = new Date(m + "-01T12:00:00"); return isNaN(d) ? m : d.toLocaleDateString("de-DE", { month: "short", year: "numeric" }); },
    mehr: function (n) { return n + " Pins an dieser Stelle"; }
  };
  var FARBE = { art: "#f2a24b", rt: "#a99df9", dt: "#35b8a8", jpg: "#5b9cf6", andere: "#a2aaba" };

  var svg = sek.querySelector("svg.map"), gPins = sek.querySelector(".pins"), gWahl = sek.querySelector(".pick");
  var rahmen = sek.querySelector(".map-frame"), tip = sek.querySelector(".map-tip"), hinweis = sek.querySelector(".map-hint");
  var stats = sek.querySelector(".map-stats"), knopf = sek.querySelector(".map-set"), form = sek.querySelector(".map-form");
  var meldung = sek.querySelector(".map-msg"), senden = form.querySelector("[type=submit]");
  var NS = "http://www.w3.org/2000/svg";
  var zustand = { pins: [], wahl: null, modus: null, token: null, widget: null, neu: null };
  var ansicht = [0, 0, BREITE, HOEHE];

  function el(name, attr) { var e = document.createElementNS(NS, name); for (var k in attr) e.setAttribute(k, attr[k]); return e; }
  function xy(lat, lon) { return [lon + 180, NORD - Math.max(SUED, Math.min(NORD, lat))]; }
  function runden(v) { return Math.round(v / RASTER) * RASTER; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function pxJeEinheit() { var b = svg.getBoundingClientRect(); return b.width / ansicht[2] || 1; }

  // ---- Ansicht (Zoom) -------------------------------------------------
  function setzeAnsicht(v) { ansicht = v; svg.setAttribute("viewBox", v.join(" ")); zeichnen(); }
  function fahre(ziel) {
    var start = ansicht.slice(), t0 = null;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return setzeAnsicht(ziel);
    function schritt(t) {
      if (t0 === null) t0 = t;
      var p = Math.min(1, (t - t0) / 320), e = p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      setzeAnsicht(start.map(function (a, i) { return a + (ziel[i] - a) * e; }));
      if (p < 1) requestAnimationFrame(schritt);
    }
    requestAnimationFrame(schritt);
  }
  function zoomAuf(x, y) {
    var w = BREITE / 4, h = HOEHE / 4;
    fahre([Math.max(0, Math.min(BREITE - w, x - w / 2)), Math.max(0, Math.min(HOEHE - h, y - h / 2)), w, h]);
  }

  // ---- Pins zeichnen --------------------------------------------------
  function gruppen() {
    var m = {};
    zustand.pins.forEach(function (p) { var k = p.lat + "|" + p.lon; (m[k] = m[k] || []).push(p); });
    return Object.keys(m).map(function (k) { return m[k]; });
  }
  function zeichnen() {
    var r = Math.max(0.35, 4.2 / pxJeEinheit());
    gPins.textContent = "";
    gruppen().forEach(function (g) {
      var p = g[g.length - 1], pos = xy(p.lat, p.lon), zahl = {};
      g.forEach(function (q) { zahl[q.engine] = (zahl[q.engine] || 0) + 1; });
      var eng = Object.keys(zahl).sort(function (a, b) { return zahl[b] - zahl[a]; })[0];
      var rr = r * (g.length > 1 ? Math.min(1.8, 1 + 0.25 * Math.log2(g.length) + 0.25) : 1);
      var neu = g.some(function (q) { return q.id === zustand.neu; });
      var kreis = el("circle", { cx: pos[0], cy: pos[1], r: rr, fill: FARBE[eng] || FARBE.andere, "class": "pin" + (neu ? " pin-neu" : ""), tabindex: "0", role: "button" });
      kreis.style.setProperty("--glow", (FARBE[eng] || FARBE.andere));
      kreis.setAttribute("stroke-width", r * 0.45);
      kreis.addEventListener("mouseenter", function () { zeigeTip(g, kreis); });
      kreis.addEventListener("focus", function () { zeigeTip(g, kreis); });
      kreis.addEventListener("mouseleave", versteckeTip);
      kreis.addEventListener("blur", versteckeTip);
      kreis.addEventListener("click", function (e) { if (!zustand.modus) { e.stopPropagation(); zeigeTip(g, kreis); } });
      kreis.setAttribute("aria-label", g.map(text).join("; "));
      gPins.appendChild(kreis);
    });
    gWahl.textContent = "";
    if (zustand.wahl) {
      var w = xy(zustand.wahl.lat, zustand.wahl.lon);
      gWahl.appendChild(el("circle", { cx: w[0], cy: w[1], r: r * 2.4, "class": "pick-ring", "stroke-width": r * 0.4 }));
      gWahl.appendChild(el("circle", { cx: w[0], cy: w[1], r: r * 0.9, "class": "pick-dot" }));
    }
  }
  function text(p) {
    return (T.reaktion[p.reaktion] || p.reaktion) + " · " + (T.engine[p.engine] || p.engine) + " · " + T.monat(p.monat) + " · #" + p.id;
  }
  function zeigeTip(g, kreis) {
    var zeilen = g.slice(-4).reverse().map(function (p) {
      return '<span class="tip-row"><i style="background:' + (FARBE[p.engine] || FARBE.andere) + '"></i>' + esc(text(p)) + "</span>";
    }).join("");
    if (g.length > 4) zeilen += '<span class="tip-more">' + esc(T.mehr(g.length)) + "</span>";
    tip.innerHTML = zeilen;
    tip.hidden = false;
    var b = kreis.getBoundingClientRect(), f = rahmen.getBoundingClientRect();
    var x = b.left + b.width / 2 - f.left, y = b.top - f.top;
    tip.style.left = Math.max(8, Math.min(f.width - tip.offsetWidth - 8, x - tip.offsetWidth / 2)) + "px";
    tip.style.top = (y - tip.offsetHeight - 10 < 4 ? y + b.height + 10 : y - tip.offsetHeight - 10) + "px";
  }
  function versteckeTip() { tip.hidden = true; }

  function statistik() {
    var n = zustand.pins.length, l = {};
    zustand.pins.forEach(function (p) { if (p.land) l[p.land] = 1; });
    stats.innerHTML = n ? T.stats(n, Object.keys(l).length) : esc(T.keine);
  }

  // ---- Laden ----------------------------------------------------------
  function laden(frisch) {
    if (!API) return;
    fetch(API + "/pins" + (frisch ? "?t=" + Date.now() : ""), { cache: frisch ? "no-store" : "default" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) { zustand.pins = Array.isArray(d.pins) ? d.pins : []; statistik(); zeichnen(); })
      .catch(function () { stats.textContent = T.fehlerLaden; });
  }

  // ---- Pin waehlen ----------------------------------------------------
  function punktAus(e) {
    var pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    var m = svg.getScreenCTM(); if (!m) return null;
    var p = pt.matrixTransform(m.inverse());
    return [Math.max(0, Math.min(BREITE, p.x)), Math.max(0, Math.min(HOEHE, p.y))];
  }
  function zeigeHinweis(txt, mitStandort) {
    hinweis.innerHTML = "";
    var s = document.createElement("span"); s.textContent = txt; hinweis.appendChild(s);
    var b = document.createElement("button"); b.type = "button"; b.className = "map-link";
    if (mitStandort) { b.textContent = T.standort; b.addEventListener("click", standort); }
    else { b.textContent = T.zurueck; b.addEventListener("click", function () { zustand.modus = "welt"; fahre([0, 0, BREITE, HOEHE]); zeigeHinweis(T.tipp1, true); }); }
    hinweis.appendChild(b);
    var c = document.createElement("button"); c.type = "button"; c.className = "map-link"; c.textContent = T.abbrechen;
    c.addEventListener("click", beenden); hinweis.appendChild(c);
    hinweis.hidden = false;
  }
  function starten() {
    zustand.modus = "welt"; rahmen.classList.add("picking"); knopf.hidden = true;
    meldung.textContent = ""; zeigeHinweis(T.tipp1, true);
  }
  function beenden() {
    zustand.modus = null; zustand.wahl = null; rahmen.classList.remove("picking");
    hinweis.hidden = true; form.hidden = true; knopf.hidden = false;
    fahre([0, 0, BREITE, HOEHE]);
  }
  function waehle(lat, lon) {
    zustand.wahl = { lat: runden(lat), lon: runden(lon) };
    zustand.modus = "fein"; zeichnen(); oeffneForm();
  }
  function standort() {
    if (!navigator.geolocation) { meldung.textContent = T.keinStandort; meldung.className = "map-msg err"; return; }
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = runden(pos.coords.latitude), lon = runden(pos.coords.longitude);
      var p = xy(lat, lon); zoomAuf(p[0], p[1]); zeigeHinweis(T.tipp2, false); waehle(lat, lon);
    }, function () { meldung.textContent = T.keinStandort; meldung.className = "map-msg err"; }, { maximumAge: 600000, timeout: 15000, enableHighAccuracy: false });
  }
  svg.addEventListener("click", function (e) {
    if (!zustand.modus) return;
    var p = punktAus(e); if (!p) return;
    if (zustand.modus === "welt") { zustand.modus = "fein"; zoomAuf(p[0], p[1]); zeigeHinweis(T.tipp2, false); return; }
    waehle(NORD - p[1], p[0] - 180);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && zustand.modus) beenden(); });
  document.addEventListener("click", function (e) { if (!tip.hidden && !e.target.closest(".pin")) versteckeTip(); });
  window.addEventListener("resize", zeichnen);
  knopf.addEventListener("click", starten);

  // ---- Formular und Turnstile ------------------------------------------
  function pruefeForm() {
    var ok = form.querySelector("input[name=reaktion]:checked") && form.querySelector("input[name=engine]:checked")
      && form.querySelector("input[name=zustimmung]").checked && zustand.token && zustand.wahl;
    senden.disabled = !ok;
  }
  form.addEventListener("change", pruefeForm);
  form.querySelector(".map-cancel").addEventListener("click", beenden);
  function turnstile() {
    var box = form.querySelector(".map-turnstile");
    function rendern() {
      if (zustand.widget !== null || !window.turnstile) return;
      box.textContent = "";
      zustand.widget = window.turnstile.render(box, {
        sitekey: SITEKEY, theme: "dark", language: EN ? "en" : "de", size: "flexible",
        callback: function (t) { zustand.token = t; pruefeForm(); },
        "expired-callback": function () { zustand.token = null; pruefeForm(); },
        "error-callback": function () { zustand.token = null; pruefeForm(); }
      });
    }
    if (window.turnstile) return rendern();
    if (document.getElementById("cf-turnstile-skript")) return;
    box.textContent = T.pruefungLaden;
    window.plTurnstileBereit = rendern;
    var s = document.createElement("script");
    s.id = "cf-turnstile-skript"; s.async = true; s.defer = true;
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=plTurnstileBereit";
    document.head.appendChild(s);
  }
  function oeffneForm() {
    if (form.hidden) {
      form.hidden = false;
      // Ein Turnstile-Nachweis gilt nur einmal: nach einem gesendeten Pin
      // braucht das Widget einen neuen.
      if (zustand.widget !== null && !zustand.token && window.turnstile) window.turnstile.reset(zustand.widget);
      else turnstile();
    }
    pruefeForm();
  }
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (senden.disabled) return;
    senden.disabled = true; meldung.textContent = "";
    var daten = {
      lat: zustand.wahl.lat, lon: zustand.wahl.lon,
      reaktion: form.querySelector("input[name=reaktion]:checked").value,
      engine: form.querySelector("input[name=engine]:checked").value,
      zustimmung: true, token: zustand.token
    };
    fetch(API + "/pins", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(daten) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (d) { return { s: r.status, d: d }; }); })
      .then(function (a) {
        if (a.s === 201) {
          zustand.neu = a.d.id; meldung.textContent = T.ok; meldung.className = "map-msg ok";
          form.reset(); zustand.token = null;
          setTimeout(function () { beenden(); laden(true); }, 1400);
        } else {
          meldung.textContent = T[a.d.fehler] || T.netz; meldung.className = "map-msg err";
          zustand.token = null;
          if (window.turnstile && zustand.widget !== null) window.turnstile.reset(zustand.widget);
        }
        pruefeForm();
      })
      .catch(function () { meldung.textContent = T.netz; meldung.className = "map-msg err"; pruefeForm(); });
  });

  // ---- Start: Pins erst laden, wenn die Karte in die Naehe kommt -----------
  stats.textContent = T.laden;
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (e) { if (e[0].isIntersecting) { io.disconnect(); laden(false); } }, { rootMargin: "400px" });
    io.observe(sek);
  } else laden(false);
  zeichnen();
})();
