"use strict";
/* ============================================================
   Skytech Energy Pilot – Ingress-SPA (Preact + htm, kein Build).
   Ersetzt die frühere Vanilla-innerHTML-SPA (D-010). Gleiche API-Pfade,
   IDs/Klassen und Verhalten; Reaktivität statt manueller DOM-Pflege.
   Ingress liefert relative Pfade → API immer OHNE führenden Slash.
   ============================================================ */
const { h, render, Fragment } = preact;
const { useState, useEffect, useRef, useCallback } = preactHooks;
const html = htm.bind(h);

/* ---------- Helfer ---------- */
const fmt = (v) =>
  v === null || v === undefined ? "–" : Number(v).toLocaleString("de-DE", { maximumFractionDigits: 1 });
const tsDE = (t) => (t ? new Date(t * 1000).toLocaleString("de-DE") : "–");
const boolDe = (v) => (v ? "Ja" : "Nein");
// Technische Quell-/Herkunftstoken (aus dem Backend) als lesbare deutsche Anzeige.
// Die CSS-Klasse `src-<token>` bleibt am Rohwert – nur der sichtbare Text wird übersetzt.
const SRC_LABELS = {
  live: "Live",
  none: "keine",
  fallback: "Ersatzwert",
  hems: "HEMS",
  measurement: "Messwert",
  device: "Gerät",
  forecast: "Prognose",
  weather: "Wetter",
};
const srcDe = (s) => SRC_LABELS[s] || s || "–";
// Technischer HEMS-Regelmodus-Wert als lesbare deutsche Anzeige (aus input_select.ems_regelmodus).
const MODE_LABELS = { aus: "Aus", auto: "Automatik", nur_heizen: "Nur Heizen", nur_laden: "Nur Laden" };
const modeDe = (m) => MODE_LABELS[m] || m || "–";

// Robust gegen Nicht-JSON-Antworten (HA-Ingress-Fehlerseite bei Timeout/502): liefert
// eine lesbare Meldung statt „Unexpected token '<'". Ersetzt die frühere fetchJson().
async function api(path, opts) {
  const resp = await fetch(path, opts);
  const text = await resp.text();
  try {
    return JSON.parse(text);
  } catch {
    const hint =
      resp.status >= 500 || !text.trim().startsWith("{")
        ? `Server-Fehler ${resp.status}: keine JSON-Antwort (evtl. Zeitüberschreitung/Ingress). Details im Addon-Log.`
        : `Unerwartete Antwort (${resp.status}). Details im Addon-Log.`;
    return { ok: false, error: hint, reason: hint, validation: { ok: false, errors: [hint], clamped: [] } };
  }
}

// Lädt beim Mounten; pollt alle 10 s, solange die Komponente (= der aktive Tab) lebt.
function usePoll(loader, poll) {
  const [data, setData] = useState(null);
  const ref = useRef(loader);
  ref.current = loader;
  const reload = useCallback(async () => {
    try {
      setData(await ref.current());
    } catch (e) {
      setData({ __error: String(e) });
    }
  }, []);
  useEffect(() => {
    reload();
    if (!poll) return undefined;
    const id = setInterval(reload, 10000);
    return () => clearInterval(id);
  }, [reload, poll]);
  return [data, reload, setData];
}

// Tabellen am Handy als Karten: <thead>-Überschrift je Körperzelle als data-label spiegeln
// (siehe CSS @media ≤480px). Idempotent; ein MutationObserver hält es über Re-Renders aktuell.
function labelizeTables(root) {
  (root || document).querySelectorAll("table").forEach((t) => {
    const heads = [...t.querySelectorAll("thead th")].map((th) => th.textContent.trim());
    if (!heads.length) return;
    t.querySelectorAll("tbody tr").forEach((tr) => {
      [...tr.children].forEach((td, i) => {
        if (heads[i] && !td.hasAttribute("data-label")) td.setAttribute("data-label", heads[i]);
      });
    });
  });
}

/* ---------- Konstanten (aus der Vanilla-Version übernommen) ---------- */
const PLAN_FIELD_LABELS = {
  prio_vorschlag: "Priorität",
  freigabe_vorschlag: "Freigabe",
  geschutzte_mindestleistung_w_vorschlag: "Geschützte Mindestleistung (W)",
  geschutzte_mindestleistung_a_vorschlag: "Geschützte Mindestleistung (A)",
};
function planFieldLabel(k) {
  if (PLAN_FIELD_LABELS[k]) return PLAN_FIELD_LABELS[k];
  const m = /^extra_(.+)_vorschlag$/.exec(k);
  if (m) return "Zusatz: " + m[1].replace(/_/g, " ");
  return k;
}
// Technischer Gerätename (z. B. "heizstab") als lesbare Überschrift, falls kein
// Anzeige-Label mitgeliefert wird (Plan-Geräte tragen nur den technischen `name`).
function deviceHeading(name) {
  return String(name || "")
    .replace(/_/g, " ")
    .replace(/\b\p{L}/gu, (c) => c.toUpperCase());
}
const HEMS_OVERALL = {
  kein_plan: ["Kein Plan", "#888"],
  unbekannt: ["Unbekannt", "#c93"],
  beobachtet_konform: ["Beobachtet konform", "#2a8"],
  beobachtet_abweichend: ["Beobachtet abweichend", "#c33"],
};
const FIELD_STATUS = { match: "✅", abweichend: "❌", unbekannt: "–" };

/* ---------- Kleine UI-Bausteine ---------- */
function Kv({ rows }) {
  return html`<div class="kv">
    ${rows.map(
      ([k, v], i) =>
        html`<${Fragment} key=${i}><div>${k}</div><div><code>${v}</code></div></${Fragment}>`
    )}
  </div>`;
}

/* ============================================================
   Tab: Status
   ============================================================ */
function StatusTab() {
  const [health] = usePoll(() => api("api/health"), false);
  const [diag, reloadDiag] = usePoll(() => api("api/diagnostics"), true);
  const [allow] = usePoll(() => api("api/allowlist"), true);
  const [haTest, setHaTest] = useState("");
  const runHaTest = async () => {
    setHaTest(" … teste …");
    try {
      const res = await fetch("api/ha/test");
      const d = await res.json();
      setHaTest(d.connected ? " ✅ verbunden" : ` ❌ ${d.reason || res.status}`);
    } catch (e) {
      setHaTest(" ❌ " + e);
    }
    reloadDiag();
  };
  const HEALTH_LABELS = {
    status: "Status",
    version: "Version",
    provider: "KI-Anbieter",
    model: "Modell",
    ha_configured: "HA verbunden",
  };
  const healthRows =
    health && !health.__error
      ? Object.entries(health).map(([k, v]) => [
          HEALTH_LABELS[k] || k,
          typeof v === "boolean" ? boolDe(v) : String(v),
        ])
      : [];
  const diagRows =
    diag && !diag.__error
      ? [
          ["HA verbunden", boolDe(diag.ha_configured)],
          ["Poller aktiv", boolDe(diag.poller_active)],
          ["Intervall (s)", diag.poll_interval_s],
          ["Zugeordnete Größen", (diag.mapped_roles || []).join(", ") || "–"],
          ["Letzter Lauf", tsDE(diag.last_collect_ts)],
          ["Letzter Fehler", diag.last_error || "–"],
        ]
      : [];
  return html`
    <div class="ha-card">
      <div class="card-title">Systemstatus</div>
      <${Kv} rows=${healthRows} />
    </div>
    <div class="ha-card">
      <div class="card-title">Diagnose</div>
      <${Kv} rows=${diagRows} />
      <div class="toolbar">
        <button onClick=${runHaTest}>HA-Verbindung testen</button>
        <span class="hint-inline">${haTest}</span>
      </div>
    </div>
    <div class="ha-card">
      <div class="card-title">Freigegebene Entitäten (Allowlist)</div>
      <p class="hint">EP liest nur diese Entitäten. Zugriffe außerhalb der Liste werden protokolliert, aber nicht blockiert.</p>
      <${Allowlist} data=${allow} />
    </div>`;
}

function Allowlist({ data }) {
  if (!data) return html`<p class="hint-inline">…</p>`;
  if (!data.count)
    return html`<p>Noch keine Entitäten freigegeben (Zuordnung/Geräte/Prognose in der Addon-Config pflegen).</p>`;
  const bySrc = Object.entries(data.by_source || {})
    .map(([k, v]) => `${srcDe(k)}: ${v}`)
    .join(", ");
  return html`
    <p style="font-size:.8rem;color:#888;">${data.count} Entitäten (${bySrc})</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Entität</th><th>Quelle</th></tr></thead>
      <tbody>${(data.entries || []).map(
        (e, i) => html`<tr key=${i}><td><code>${e.entity_id}</code></td><td>${srcDe(e.source)}</td></tr>`
      )}</tbody>
    </table></div>`;
}

/* ============================================================
   Tab: Daten
   ============================================================ */
function DatenTab() {
  const [data, reload] = usePoll(() => api("api/state"), true);
  const rows = data && !data.__error ? Object.values(data) : [];
  return html`<div class="ha-card">
    <div class="card-title">Messwerte<div class="card-actions"><button onClick=${reload}>Aktualisieren</button></div></div>
    <div class="table-wrap"><table>
      <thead><tr><th>Größe</th><th class="num">Aktuell</th><th class="num">Ø 1 min</th><th class="num">Ø 15 min</th><th class="num">Ø 60 min</th><th>Quelle</th></tr></thead>
      <tbody>${rows.map((r, i) => {
        const unit = r.unit ? " " + r.unit : "";
        const cur = r.averaged ? r.latest : r.value;
        return html`<tr key=${i}>
          <td>${r.label}</td>
          <td class="num">${fmt(cur)}${unit}</td>
          <td class="num">${r.averaged ? fmt(r.mean_1m) + unit : ""}</td>
          <td class="num">${r.averaged ? fmt(r.mean_15m) + unit : ""}</td>
          <td class="num">${r.averaged ? fmt(r.mean_60m) + unit : ""}</td>
          <td class="src-${r.source}">${srcDe(r.source)}</td>
        </tr>`;
      })}</tbody>
    </table></div>
  </div>`;
}

/* ============================================================
   Tab: Geräte
   ============================================================ */
function GeraeteTab() {
  const [data, reload] = usePoll(() => api("api/devices"), true);
  const [selected, setSelected] = useState(null);
  const devices = (data && data.devices) || [];
  const names = devices.map((d) => d.name);
  // Auswahl über Auto-Aktualisierungen hinweg beibehalten; sonst auf das erste Gerät.
  useEffect(() => {
    if (!devices.length) {
      if (selected !== null) setSelected(null);
    } else if (!selected || !names.includes(selected)) {
      setSelected(names[0]);
    }
    // eslint-disable-next-line
  }, [data]);
  const srcLabel = data
    ? { hems: "HEMS-Schema", none: "keine (HEMS nicht verbunden)" }[data.source] || data.source
    : "";
  const dev = devices.find((d) => d.name === selected);
  return html`<div class="ha-card">
    <div class="card-title">Geräte<div class="card-actions"><button onClick=${reload}>Aktualisieren</button></div></div>
    <div class="toolbar">
      <label for="device-select">Gerät:</label>
      <select id="device-select" style=${devices.length ? "min-width:14rem;" : "display:none;"}
              value=${selected || ""} onChange=${(e) => setSelected(e.target.value)}>
        ${devices.map(
          (d) =>
            html`<option key=${d.name} value=${d.name}>${d.label} (${d.class === "controllable" ? "regelbar" : "binär"})</option>`
        )}
      </select>
      <span class="hint-inline"> Quelle: ${srcLabel}</span>
    </div>
    <p class="hint">Ein Gerät auswählen, um dessen Werte, Zusatz-Entitäten und KI-Beschreibung zu sehen.
      Geräte kommen ausschließlich vom HEMS. Über <b>Zusatz-Entitäten</b> kannst du je Gerät weitere
      Werte <b>beliebiger Domäne</b> hinterlegen (<code>sensor</code>, <code>input_number</code>,
      <code>input_boolean</code>, <code>input_datetime</code>, <code>input_text</code>,
      <code>input_select</code> …), die EP liest – optional liefert die KI dafür einen typgerechten
      Vorschlag als <code>${"sensor.ep_<entität>_vorschlag"}</code> (nur HA-Sensor, nicht ans HEMS).</p>
    ${!devices.length
      ? html`<p>Keine Geräte erkannt. HEMS-URL in der Addon-Config (<code>hems_base_url</code>) setzen und die
          Geräte im HEMS anlegen – dann im HEMS-Tab „Geräte von HEMS neu laden“.</p>`
      : dev
        ? html`<${DeviceCard} key=${dev.name} device=${dev} onChanged=${reload} />`
        : ""}
  </div>`;
}

function DeviceCard({ device: d, onChanged }) {
  const cls = d.class === "controllable" ? "regelbar" : "binär";
  return html`
    <h2 style="font-size:1rem;margin-top:1rem;">${d.label} <small style="font-weight:normal;color:#888;">(${cls})</small></h2>
    <table>
      <thead><tr><th>Größe</th><th class="num">Wert</th><th>Entität</th><th>Quelle</th></tr></thead>
      <tbody>${d.fields.map((f, i) => {
        let val;
        if (f.value === null || f.value === undefined) val = "–";
        else if (f.kind === "bool") val = f.value ? "Ja" : "Nein";
        else val = fmt(f.value) + (f.unit ? " " + f.unit : "");
        return html`<tr key=${i}><td>${f.label}</td><td class="num">${val}</td><td><code>${f.entity_id}</code></td><td class="src-${f.source}">${srcDe(f.source)}</td></tr>`;
      })}</tbody>
    </table>
    <${Extras} device=${d} onChanged=${onChanged} />
    <${DevicePrompt} device=${d} onChanged=${onChanged} />`;
}

// Freitext-Beschreibung des Geräts für die KI (D-051).
function DevicePrompt({ device: d, onChanged }) {
  const [text, setText] = useState(d.ai_prompt || "");
  const [msg, setMsg] = useState(d.ai_prompt ? " (eigene Beschreibung)" : " (keine)");
  const save = async (clear) => {
    const val = clear ? "" : text;
    if (clear) setText("");
    setMsg(" … speichern …");
    try {
      const res = await fetch("api/devices/prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_name: d.name, prompt: val }),
      });
      const data = await res.json();
      if (data.ok) {
        setMsg(data.is_custom ? " ✅ gespeichert (eigene Beschreibung)" : " ✅ geleert (keine)");
        onChanged();
      } else {
        setMsg(" ❌ " + (data.reason || res.status));
      }
    } catch (e) {
      setMsg(" ❌ " + e);
    }
  };
  return html`<div class="device-prompt">
    <h3 style="font-size:.85rem;margin:.8rem 0 .2rem;">KI-Beschreibung / Funktion dieses Geräts</h3>
    <p style="font-size:.8rem;color:#888;margin:.2rem 0;">Optionaler Freitext, der der KI erklärt, was dieses Gerät
      tut und wie es zu behandeln ist (z. B. „versorgt die Fußbodenheizung, träge, darf bevorzugt mittags laufen“).
      Geht als Feld <code>funktion</code> in die Planung ein – rein advisorisch, <strong>nicht</strong> ans HEMS.</p>
    <textarea style="width:100%;max-width:44rem;min-height:3.5rem;box-sizing:border-box;font-family:inherit;font-size:.85rem;"
      value=${text} onInput=${(e) => setText(e.target.value)}></textarea>
    <div style="margin-top:.3rem;">
      <button onClick=${() => save(false)}>Speichern</button>
      <button onClick=${() => save(true)}>Leeren</button>
      <span style="font-size:.8rem;">${msg}</span>
    </div>
  </div>`;
}

// Zusatz-Entität-Wert typgerecht (Zahl/Bool/Text/Datum, D-048).
function fmtExtraValue(x) {
  if (x.value === null || x.value === undefined) return "–";
  const u = x.unit ? " " + x.unit : "";
  if (typeof x.value === "boolean") return x.value ? "Ja" : "Nein";
  if (typeof x.value === "number") return fmt(x.value) + u;
  return String(x.value) + u;
}
// Typ + gelesene Grenzen/Format je Zusatz-Entität (D-048).
function extraTypeInfo(x) {
  const a = x.attrs || {};
  if (x.kind === "number")
    return a.min != null || a.max != null
      ? `Zahl (${a.min ?? "?"}–${a.max ?? "?"}${a.unit_of_measurement ? " " + a.unit_of_measurement : ""})`
      : "Zahl";
  if (x.kind === "bool") return "Ja/Nein";
  if (x.kind === "datetime") {
    const p = [];
    if (a.has_date) p.push("Datum");
    if (a.has_time) p.push("Uhrzeit");
    return "Datum/Zeit" + (p.length ? " (" + p.join("+") + ")" : "");
  }
  if (x.kind === "select") {
    const opts = Array.isArray(a.options) ? a.options : [];
    return "Auswahl" + (opts.length ? " (" + opts.join(", ") + ")" : "");
  }
  if (x.kind === "text") return "Text";
  return "auto";
}
// D-052: effektiver „In Original schreiben"-Zustand.
function OrigState({ x }) {
  if (!x.ai_suggestion) return html`<span style="color:#888;">–</span>`;
  if (x.should_write_original) return "Ja";
  if (x.write_original) return html`Ja <small style="color:#888;">(nicht wirksam, kein Helfer)</small>`;
  return "Nein";
}

// Zusatz-Entitäten-Editor je Gerät (D-047/D-048/D-052).
function Extras({ device: d, onChanged }) {
  const empty = { entity: "", label: "", unit: "", suggest: false, original: false, hint: "" };
  const [form, setForm] = useState(empty);
  const [msg, setMsg] = useState("");
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const startEdit = (x) =>
    setForm({
      entity: x.read_entity_id,
      label: x.label || "",
      unit: x.unit || "",
      suggest: !!x.ai_suggestion,
      original: !!x.write_original,
      hint: x.ai_hint || "",
    });
  const del = async (entity) => {
    if (!confirm(`Zusatz-Entität ${entity} entfernen?`)) return;
    await fetch("api/devices/extras", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_name: d.name, read_entity_id: entity }),
    });
    onChanged();
  };
  const add = async () => {
    const payload = {
      device_name: d.name,
      read_entity_id: form.entity.trim(),
      ai_suggestion: form.suggest,
      ai_hint: form.hint,
      label: form.label,
      unit: form.unit,
      write_original: form.suggest && form.original,
    };
    if (!payload.read_entity_id) {
      setMsg("❌ Entität erforderlich");
      return;
    }
    setMsg(" … speichern …");
    try {
      const res = await fetch("api/devices/extras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.ok) {
        setMsg("✅ gespeichert");
        setForm(empty);
        onChanged();
      } else {
        setMsg("❌ " + (data.reason || res.status));
      }
    } catch (e) {
      setMsg("❌ " + e);
    }
  };
  const extras = d.extras || [];
  return html`<div class="extras">
    <h3 style="font-size:.85rem;margin:.6rem 0 .2rem;">Zusatz-Entitäten
      <small style="font-weight:normal;color:#888;">(zusätzlich zu den HEMS-Werten)</small></h3>
    ${extras.length
      ? html`<table>
          <thead><tr><th>Entität (gelesen)</th><th>Typ</th><th>KI-Vorschlag</th><th>Vorschlags-Sensor</th>
            <th>In Original schreiben</th><th class="num">Wert</th><th>Hinweis für KI</th><th></th></tr></thead>
          <tbody>${extras.map(
            (x, i) => html`<tr key=${i}>
              <td><code>${x.read_entity_id}</code>${x.label
                ? html` <small style="color:#888;">(${x.label})</small>`
                : ""}</td>
              <td style="font-size:.75rem;color:#888;">${extraTypeInfo(x)}</td>
              <td>${x.ai_suggestion ? "Ja" : "Nein"}</td>
              <td>${x.ai_suggestion
                ? html`<code>${x.suggestion_entity_id}</code>`
                : html`<span style="color:#888;">–</span>`}</td>
              <td><${OrigState} x=${x} /></td>
              <td class="num src-${x.source}">${fmtExtraValue(x)}</td>
              <td style="font-size:.72rem;color:#888;max-width:16rem;">${x.ai_hint || ""}</td>
              <td style="white-space:nowrap;">
                <button onClick=${() => startEdit(x)}>Bearbeiten</button>
                <button onClick=${() => del(x.read_entity_id)}>Löschen</button>
              </td>
            </tr>`
          )}</tbody>
        </table>`
      : html`<p style="font-size:.8rem;color:#888;">Noch keine Zusatz-Entitäten. Unten hinzufügen.</p>`}
    <div class="extra-form" style="display:grid;grid-template-columns:1fr 1fr;gap:.35rem;margin:.4rem 0 .8rem;max-width:44rem;">
      <input style="grid-column:1/3;" placeholder="Entität, z. B. sensor.…, input_number.…, input_boolean.…, input_datetime.…, input_select.…"
        value=${form.entity} onInput=${(e) => set({ entity: e.target.value })} />
      <input placeholder="Anzeigename (optional)" value=${form.label} onInput=${(e) => set({ label: e.target.value })} />
      <input placeholder="Einheit, z. B. % oder °C (optional)" value=${form.unit} onInput=${(e) => set({ unit: e.target.value })} />
      <label style="grid-column:1/3;font-size:.82rem;">
        <input type="checkbox" checked=${form.suggest}
          onChange=${(e) => set({ suggest: e.target.checked, original: e.target.checked ? form.original : false })} />
        KI liefert Vorschlagswert (<code>${"sensor.ep_<entität>_vorschlag"}</code>)</label>
      <label style="grid-column:1/3;font-size:.82rem;">
        <input type="checkbox" disabled=${!form.suggest} checked=${form.original}
          onChange=${(e) => set({ original: e.target.checked })} />
        In Original schreiben <small style="color:#888;">(nur bei KI-Vorschlag; wirkungslos bei
        <code>sensor.*</code> – dort entsteht nur der Vorschlags-Sensor)</small></label>
      <textarea class="ex-hint" placeholder="Freitext für die KI: was der Wert bedeutet und wie sie ihn verwenden/interpretieren soll."
        style="grid-column:1/3;min-height:3rem;" value=${form.hint} onInput=${(e) => set({ hint: e.target.value })}></textarea>
      <div style="grid-column:1/3;"><button onClick=${add}>Speichern</button> <span style="font-size:.8rem;">${msg}</span></div>
    </div>
  </div>`;
}

/* ============================================================
   Tab: Prognose
   ============================================================ */
function PrognoseTab() {
  const [fc, reloadFc] = usePoll(() => api("api/forecast"), true);
  const [wx, reloadWx] = usePoll(() => api("api/weather"), true);
  const [wxTest, setWxTest] = useState("");
  const testWeather = async () => {
    setWxTest(" … teste Wetterabruf …");
    try {
      const res = await fetch("api/weather/test");
      const data = await res.json();
      const r = data.result || {};
      if (Array.isArray(r.timelines)) {
        const parts = r.timelines.map((t) =>
          t.ok
            ? `${t.resolution} ✅ ${t.slots ?? 0}${t.pages > 1 ? "/" + t.pages + "S" : ""}`
            : `${t.resolution} ❌ ${t.reason || ""}`
        );
        if (r.alerts) parts.push(r.alerts.ok ? `Alerts ✅ ${r.alerts.count ?? 0}` : `Alerts ❌ ${r.alerts.reason || ""}`);
        if (r.daily_call_budget != null) parts.push(`Budget ${r.calls_today ?? 0}/${r.daily_call_budget}`);
        setWxTest((data.connected ? " ✅ " : " ❌ ") + parts.join(" · "));
      } else if (data.connected) {
        setWxTest(` ✅ ${r.city || "Abruf ok"} (${r.slots ?? 0} Zeitschritte)`);
      } else {
        setWxTest(` ❌ ${r.reason || data.reason || res.status}${r.request_url ? " · URL: " + r.request_url : ""}`);
      }
    } catch (e) {
      setWxTest(" ❌ " + e);
    }
    reloadWx();
  };
  return html`
    <div class="ha-card">
      <div class="card-title">PV-Prognose (Summe über alle Ausrichtungen)<div class="card-actions">
        <button onClick=${() => { reloadFc(); reloadWx(); }}>Aktualisieren</button></div></div>
      <${Forecast} data=${fc} />
    </div>
    <div class="ha-card">
      <div class="card-title">Wetter (OpenWeatherMap)<div class="card-actions">
        <button onClick=${testWeather}>Wetter testen</button></div></div>
      <p class="hint">Direkt im EP über OpenWeatherMap abgerufen (Quelle umschaltbar: 5 Tage / 3 h oder One Call API 4.0).
        Koordinaten aus der HA-Zone, API-Schlüssel in der Addon-Config (<code>weather</code>). Nur EP-intern –
        <strong>nicht</strong> als HA-Sensor oder an HEMS.</p>
      <div class="hint-inline">${wxTest}</div>
      <${Weather} data=${wx} />
    </div>`;
}

function Forecast({ data }) {
  if (!data) return html`<p class="hint-inline">…</p>`;
  const unit = data.unit ? " " + data.unit : "";
  const values = data.values || [];
  const labels = Object.fromEntries(values.map((v) => [v.key, v.label]));
  return html`<${Fragment}>
    ${values.length
      ? html`<div class="table-wrap"><table>
          <thead><tr><th>Wert</th><th class="num">Summe</th></tr></thead>
          <tbody>${values.map(
            (v, i) => html`<tr key=${i}><td>${v.label}</td><td class="num">${v.total == null ? "–" : fmt(v.total) + unit}</td></tr>`
          )}</tbody>
        </table></div>`
      : html`<p>Keine PV-Prognose konfiguriert. Ausrichtungen in der Addon-Config (<code>pv_forecast</code>) pflegen.</p>`}
    ${(data.orientations || []).map(
      (o, oi) => html`<${Fragment} key=${oi}>
        <h2 style="font-size:1rem;margin-top:1rem;">${o.label}</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Wert</th><th class="num">Wert</th><th>Entität</th><th>Quelle</th></tr></thead>
          <tbody>${Object.entries(o.values).map(
            ([k, f], i) => html`<tr key=${i}><td>${labels[k] || k}</td>
              <td class="num">${f.value == null ? "–" : fmt(f.value) + unit}</td>
              <td><code>${f.entity_id}</code></td><td class="src-${f.source}">${srcDe(f.source)}</td></tr>`
          )}</tbody>
        </table></div>
      </${Fragment}>`
    )}
  </${Fragment}>`;
}

function weatherTime(s) {
  if (s.dt) return new Date(s.dt * 1000).toLocaleString("de-DE");
  return s.time || "–";
}

function Weather({ data }) {
  if (!data) return html`<p class="hint-inline">…</p>`;
  if (!data.enabled)
    return html`<div class="hint">Wetterabruf inaktiv – OpenWeatherMap-Schlüssel in der Addon-Config (weather) setzen.</div>`;
  if (data.source === "onecall") return html`<${WeatherOneCall} data=${data} />`;
  const fc = data.forecast;
  const place = fc && fc.city ? `${fc.city}${fc.country ? ", " + fc.country : ""}` : "–";
  const coords = data.coords ? `${fmt(data.coords.lat)}/${fmt(data.coords.lon)}` : "–";
  const slots = (fc && fc.slots) || [];
  return html`<${Fragment}>
    <div class="hint">Ort: <code>${place}</code> · Zone: <code>${data.zone_entity}</code> (${coords}) · Stand: ${tsDE(
      data.last_fetch_ts
    )}${data.last_error ? " · ⚠️ " + data.last_error : ""}</div>
    ${slots.length
      ? html`<div class="table-wrap"><table>
          <thead><tr><th>Zeit</th><th class="num">Temp</th><th class="num">Bewölkung</th><th class="num">Regen-W.</th><th class="num">Wind</th><th>Wetter</th></tr></thead>
          <tbody>${slots.map((s, i) => {
            const t = s.time || (s.dt ? new Date(s.dt * 1000).toLocaleString("de-DE") : "–");
            const pop = s.pop == null ? "–" : Math.round(s.pop * 100) + " %";
            return html`<tr key=${i}><td>${t}</td><td class="num">${fmt(s.temp)} °</td><td class="num">${fmt(s.clouds)} %</td>
              <td class="num">${pop}</td><td class="num">${fmt(s.wind_speed)}</td><td>${s.condition || "–"}</td></tr>`;
          })}</tbody>
        </table></div>`
      : html`<p>Noch keine Prognose abgerufen.</p>`}
  </${Fragment}>`;
}

function WeatherOneCall({ data }) {
  const coords = data.coords ? `${fmt(data.coords.lat)}/${fmt(data.coords.lon)}` : "–";
  const budget =
    data.daily_call_budget != null
      ? ` · Budget heute: ${data.calls_today ?? 0}/${data.daily_call_budget}${data.budget_exhausted ? " ⛔ erschöpft" : ""}`
      : "";
  const labels = { "15min": "15-Minuten", "1h": "Stündlich", "1day": "Täglich" };
  const tl = data.timelines || {};
  const active = ["15min", "1h", "1day"].filter((res) => tl[res] && tl[res].enabled);
  return html`<${Fragment}>
    <div class="hint">Quelle: <code>One Call API 4.0</code> · Zone: <code>${data.zone_entity}</code> (${coords})
      · KI-Timeline: <code>${data.llm_timeline}</code> · Stand: ${tsDE(data.last_fetch_ts)}${budget}${data.last_error
        ? " · ⚠️ " + data.last_error
        : ""}</div>
    ${active.length
      ? active.map((res) => {
          const t = tl[res];
          const pages = t.pages && t.pages > 1 ? ` · ${t.pages} Seiten` : "";
          return html`<${Fragment} key=${res}>
            <h3 style="font-size:.9rem;margin:.75rem 0 .25rem;">${labels[res]}
              <span style="font-weight:normal;color:#888;">(alle ${t.refresh_min} min${pages} · Stand ${tsDE(
                t.last_fetch_ts
              )}${t.last_error ? " · ⚠️ " + t.last_error : ""})</span></h3>
            <${OneCallTable} res=${res} slots=${t.slots || []} />
          </${Fragment}>`;
        })
      : html`<p>Keine One-Call-Timeline aktiviert oder noch keine Daten abgerufen.</p>`}
    ${data.alerts_enabled && (data.alerts || []).length ? html`<${OneCallAlerts} alerts=${data.alerts} />` : ""}
  </${Fragment}>`;
}

function OneCallTable({ res, slots }) {
  if (!slots.length) return html`<p>Noch keine Prognose abgerufen.</p>`;
  const daily = res === "1day";
  return html`<div class="table-wrap"><table>
    <thead><tr><th>Zeit</th><th class="num">Temp</th><th class="num">Bewölkung</th><th class="num">Regen-W.</th>
      ${daily ? "" : html`<th class="num">Wind</th>`}<th>Wetter</th></tr></thead>
    <tbody>${slots.map((s, i) => {
      const pop = s.pop == null ? "–" : Math.round(s.pop * 100) + " %";
      const temp = daily ? `${fmt(s.temp_min)}–${fmt(s.temp_max)} °` : `${fmt(s.temp)} °`;
      return html`<tr key=${i}><td>${weatherTime(s)}</td><td class="num">${temp}</td><td class="num">${fmt(s.clouds)} %</td>
        <td class="num">${pop}</td>${daily ? "" : html`<td class="num">${fmt(s.wind_speed)}</td>`}<td>${s.condition || "–"}</td></tr>`;
    })}</tbody>
  </table></div>`;
}

function OneCallAlerts({ alerts }) {
  return html`<${Fragment}>
    <h3 style="font-size:.9rem;margin:.75rem 0 .25rem;">⚠️ Unwetter-Warnungen</h3>
    <ul style="margin:.25rem 0;padding-left:1.2rem;">
      ${alerts.map((a, i) => {
        const from = a.start ? new Date(a.start * 1000).toLocaleString("de-DE") : "?";
        const to = a.end ? new Date(a.end * 1000).toLocaleString("de-DE") : "?";
        const tags = (a.tags || []).join(", ");
        return html`<li key=${i}><strong>${a.event || "Warnung"}</strong>${a.sender_name
          ? html` <span style="color:#888;">(${a.sender_name})</span>`
          : ""}<br /><span style="font-size:.8rem;color:#888;">${from} – ${to}${tags ? " · " + tags : ""}</span>${a.description
          ? html`<br /><span style="font-size:.85rem;">${a.description}</span>`
          : ""}</li>`;
      })}
    </ul>
  </${Fragment}>`;
}

/* ============================================================
   Tab: Grenzen & Ziele
   ============================================================ */
function GrenzenTab() {
  const [cons, reloadCons] = usePoll(() => api("api/constraints"), true);
  const [obj] = usePoll(() => api("api/objectives"), false);
  return html`
    <div class="ha-card">
      <div class="card-title">Harte Grenzen je Gerät<div class="card-actions"><button onClick=${reloadCons}>Aktualisieren</button></div></div>
      <p class="hint">Technische Limits/Freigaben aus den <code>ems_*</code>-Werten. Read-only und
        <strong>nie</strong> durch die KI änderbar. „Schreibbar" = Vorschlagsfelder, die EP für dieses Gerät erzeugen darf.</p>
      <${Constraints} data=${cons} />
    </div>
    <div class="ha-card">
      <div class="card-title">Weiche Zielgewichte</div>
      <p class="hint">Gewichte (0–100 %) aus info.md §7, in der Addon-Config unter <code>objective_weights</code> pflegbar.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Ziel</th><th class="num">Gewicht</th></tr></thead>
        <tbody>${((obj && obj.objectives) || []).map(
          (o, i) => html`<tr key=${i}><td>${o.label}</td><td class="num">${o.weight} %</td></tr>`
        )}</tbody>
      </table></div>
    </div>`;
}

function Constraints({ data }) {
  if (!data) return html`<p class="hint-inline">…</p>`;
  const devs = data.devices || [];
  if (!devs.length)
    return html`<p>Keine Geräte erkannt. HEMS-URL in der Addon-Config (<code>hems_base_url</code>) setzen und die Geräte
      im HEMS anlegen – dann im HEMS-Tab „Geräte von HEMS neu laden“.</p>`;
  return devs.map((d, di) => {
    const unit = d.output_unit === "ampere" ? " A" : " W";
    const rows = [];
    rows.push(["Technische Freigabe", d.freigabe === null ? "–" : d.freigabe ? "Ja" : "Nein"]);
    if (d.class === "binary") rows.push(["Feste Leistung", d.fixed_power == null ? "–" : fmt(d.fixed_power) + unit]);
    else {
      rows.push(["Min. Leistung", d.min_power == null ? "–" : fmt(d.min_power) + unit]);
      rows.push([d.is_battery ? "Max. Ladeleistung" : "Max. Leistung", d.max_power == null ? "–" : fmt(d.max_power) + unit]);
    }
    (d.extras || []).forEach((x) => {
      const u = x.extra.unit ? " " + x.extra.unit : "";
      const lbl = (x.extra.label && x.extra.label.trim()) || x.extra.read_entity_id;
      let v;
      if (x.value == null) v = "–";
      else if (typeof x.value === "boolean") v = x.value ? "Ja" : "Nein";
      else if (typeof x.value === "number") v = fmt(x.value) + u;
      else v = String(x.value) + u;
      rows.push(["Zusatz: " + lbl + (x.extra.ai_suggestion ? " (KI-Vorschlag)" : ""), v]);
    });
    if (d.forced_prio != null) rows.push(["Feste Priorität", d.forced_prio]);
    const cls = d.class === "controllable" ? "regelbar" : "binär";
    const writable = (d.suggestion_keys || []).map((k) => html`<code>${k}</code>`);
    return html`<${Fragment} key=${di}>
      <h3 style="font-size:.95rem;margin:.75rem 0 .25rem;">${d.label} <small style="font-weight:normal;color:#888;">(${cls})</small></h3>
      <table><tbody>${rows.map(
        (r, i) => html`<tr key=${i}><td>${r[0]}</td><td class="num">${r[1]}</td></tr>`
      )}</tbody></table>
      <p style="font-size:.78rem;color:#888;margin:.25rem 0;">Schreibbar: ${writable.length
        ? writable.map((w, i) => html`<${Fragment} key=${i}>${i ? ", " : ""}${w}</${Fragment}>`)
        : "–"}</p>
    </${Fragment}>`;
  });
}

/* ============================================================
   Tab: Plan
   ============================================================ */
function PromptEditor() {
  const [prompt, setPrompt] = useState("");
  const [def, setDef] = useState("");
  const [status, setStatus] = useState("");
  useEffect(() => {
    (async () => {
      const d = await api("api/prompt");
      setDef(d.default || "");
      setPrompt(d.prompt || "");
      setStatus(d.is_custom ? " (eigener Prompt)" : " (Standard)");
    })();
  }, []);
  const save = async (text) => {
    setStatus(" … speichere …");
    try {
      const res = await fetch("api/prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: text }),
      });
      const d = await res.json();
      setStatus(
        d.ok ? (d.is_custom ? " ✅ gespeichert (eigener Prompt)" : " ✅ auf Standard zurückgesetzt") : " ❌ " + (d.reason || res.status)
      );
    } catch (e) {
      setStatus(" ❌ " + e);
    }
  };
  return html`<details>
    <summary>Planungs-Prompt bearbeiten</summary>
    <p class="hint">Die Instruktion an die KI. Änderungen wirken sofort beim nächsten Plan – <strong>kein</strong>
      Git-Push/Add-on-Update nötig (gespeichert in der EP-Datenbank, übersteht Neustart & Update). Der Datenblock
      wird automatisch angehängt; das JSON-Antwortformat und die harten Grenzen bleiben fest erzwungen.</p>
    <textarea rows="14" value=${prompt} onInput=${(e) => setPrompt(e.target.value)}></textarea>
    <div class="toolbar">
      <button class="primary" onClick=${() => save(prompt)}>Speichern</button>
      <button onClick=${() => { setPrompt(def); save(""); }}>Auf Standard zurücksetzen</button>
      <span class="hint-inline">${status}</span>
    </div>
  </details>`;
}

function PlanTab() {
  const [plan, reloadPlan, setPlan] = usePoll(() => api("api/plan"), false);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setStatus(" … plane …");
    setBusy(true);
    try {
      const d = await api("api/plan/run", { method: "POST" });
      const errs = (d.validation && d.validation.errors) || (d.error ? [d.error] : []);
      setStatus(d.ok ? " ✅ Plan erzeugt" : ` ❌ ${errs.join("; ")}`);
      setPlan(d);
    } catch (e) {
      setStatus(" ❌ " + e);
    } finally {
      setBusy(false);
    }
  };
  const publish = async () => {
    setStatus(" … schreibe nach HA …");
    setBusy(true);
    try {
      const d = await api("api/plan/publish", { method: "POST" });
      setStatus(
        d.ok
          ? ` ✅ ${(d.written || []).length} Sensor(en) geschrieben`
          : ` ❌ ${d.reason || (d.failed || []).map((f) => f.entity_id).join(", ")}`
      );
    } catch (e) {
      setStatus(" ❌ " + e);
    } finally {
      setBusy(false);
    }
  };
  const testAi = async () => {
    setStatus(" … teste KI …");
    try {
      const d = await api("api/ai/test");
      setStatus(d.connected ? " ✅ KI verbunden" : ` ❌ ${d.reason || ""}`);
    } catch (e) {
      setStatus(" ❌ " + e);
    }
  };
  return html`<div class="ha-card">
    <div class="card-title">Plan<div class="card-actions">
      <button class="primary" disabled=${busy} onClick=${run}>Plan erzeugen</button>
      <button onClick=${publish}>Erneut nach HA schreiben</button>
      <button onClick=${reloadPlan}>Aktualisieren</button>
      <button onClick=${testAi}>KI-Verbindung testen</button>
    </div></div>
    <div class="toolbar"><span class="hint-inline">${status}</span></div>
    <p class="hint">Die KI erzeugt einen <strong>Vorschlagsplan</strong> (V1). Werte werden lokal gegen die harten
      Grenzen validiert und bei Gültigkeit als <code>sensor.ep_*_vorschlag</code> nach Home Assistant geschrieben
      (reine Anzeige zum manuellen Verdrahten) – aber <strong>nicht</strong> an HEMS übergeben.</p>
    <${PromptEditor} />
    <${PlanResult} data=${plan} />
  </div>`;
}

function PlanResult({ data }) {
  if (!data) return html`<p class="hint-inline">…</p>`;
  const v = data.validation || {};
  const errs = v.errors || [];
  const clamped = v.clamped || [];
  const p = data.plan;
  if (!p)
    return errs.length
      ? html`<p style="color:#c33;">${errs.map((e, i) => html`<${Fragment} key=${i}>${i ? html`<br />` : ""}${e}</${Fragment}>`)}</p>`
      : html`<p>Noch kein Plan erzeugt. Auf „Plan erzeugen“ klicken (KI-Schlüssel in der Addon-Config nötig).</p>`;
  const meta = [
    ["Status", v.ok ? "✅ gültig" : "❌ abgelehnt"],
    ["Provider / Modell", `${p.provider || "–"} / ${p.model || "–"}`],
    ["Konfidenz", p.confidence == null ? "–" : p.confidence + " %"],
    ["Gültig von", p.valid_from],
    ["Gültig bis", p.valid_until],
  ];
  if (data.ts) meta.push(["Erzeugt", data.ts]);
  if (data.ai_call && data.ai_call.tokens_in != null)
    meta.push(["Tokens (ein/aus)", `${data.ai_call.tokens_in} / ${data.ai_call.tokens_out}`]);
  const pub = data.published;
  return html`<${Fragment}>
    <${Kv} rows=${meta} />
    ${errs.length ? html`<p style="color:#c33;font-size:.85rem;">Fehler: ${errs.join("; ")}</p>` : ""}
    ${clamped.length ? html`<p style="color:#c93;font-size:.85rem;">Geklemmt: ${clamped.join("; ")}</p>` : ""}
    <h2 style="font-size:1rem;margin-top:1rem;">Geräte-Vorschläge</h2>
    ${(p.devices || []).map((d, di) => {
      const entries = Object.entries(d).filter(([k]) => k !== "name");
      return html`<${Fragment} key=${di}>
        <h3 style="font-size:.95rem;margin:.75rem 0 .25rem;">${deviceHeading(d.name)}</h3>
        <table><tbody>${entries.length
          ? entries.map(([k, val], i) => {
              const show =
                typeof val === "boolean" ? (val ? "Ja" : "Nein") : typeof val === "number" ? fmt(val) : String(val);
              return html`<tr key=${i}><td>${planFieldLabel(k)}</td><td class="num">${show}</td></tr>`;
            })
          : html`<tr><td>– keine Vorschläge –</td><td></td></tr>`}</tbody></table>
      </${Fragment}>`;
    })}
    ${pub ? html`<${PlanPublished} pub=${pub} />` : ""}
    ${p.reasoning
      ? html`<h3 style="font-size:.95rem;margin-top:1rem;">Begründung</h3><p style="font-size:.85rem;">${p.reasoning}</p>`
      : ""}
    ${(p.warnings || []).length
      ? html`<h3 style="font-size:.95rem;margin-top:1rem;">Warnungen</h3>
          <ul style="font-size:.85rem;">${p.warnings.map((w, i) => html`<li key=${i}>${w}</li>`)}</ul>`
      : ""}
    ${data.context
      ? html`<details style="margin-top:1rem;"><summary style="cursor:pointer;font-size:.85rem;">An die KI gesendete Daten</summary>
          <pre style="font-size:.75rem;overflow:auto;">${JSON.stringify(data.context, null, 2)}</pre></details>`
      : ""}
  </${Fragment}>`;
}

function PlanPublished({ pub }) {
  const written = pub.written && pub.written.length ? pub.written : null;
  const failed = pub.failed && pub.failed.length ? pub.failed : null;
  if (!written && !failed && !pub.reason) return "";
  return html`<${Fragment}>
    <h2 style="font-size:1rem;margin-top:1rem;">Nach HA geschrieben</h2>
    ${written
      ? html`<p style="font-size:.85rem;color:#2a8;">✅ Geschrieben: ${written.map(
          (e, i) => html`<${Fragment} key=${i}>${i ? ", " : ""}<code>${e}</code></${Fragment}>`
        )}</p>`
      : ""}
    ${failed
      ? html`<p style="font-size:.85rem;color:#c33;">❌ Fehlgeschlagen: ${failed.map(
          (f, i) => html`<${Fragment} key=${i}>${i ? ", " : ""}<code>${f.entity_id}</code> (${f.error})</${Fragment}>`
        )}</p>`
      : ""}
    ${!written && !failed && pub.reason ? html`<p style="font-size:.85rem;color:#888;">${pub.reason}</p>` : ""}
  </${Fragment}>`;
}

/* ============================================================
   Tab: HEMS
   ============================================================ */
function HemsTab() {
  const [data, reload] = usePoll(() => api("api/hems/status"), true);
  const [status, setStatus] = useState("");
  // „Aktualisieren" erzwingt einen Live-HEMS-Abruf (?refresh=1), sonst zeigt der Button nur den
  // gedrosselten Zwischenstand des Collectors – die HEMS-Ist-Werte blieben dann unverändert.
  const refresh = async () => {
    setStatus(" … aktualisiere HEMS …");
    try {
      await api("api/hems/status?refresh=1");
      setStatus("");
    } catch (e) {
      setStatus(" ❌ " + e);
    }
    reload();
  };
  const testHems = async () => {
    setStatus(" … prüfe HEMS …");
    try {
      const res = await fetch("api/hems/test");
      const d = await res.json();
      const r = d.result || {};
      setStatus(d.connected ? ` ✅ online (Zyklus ${r.cycle_count ?? "?"})` : ` ❌ ${r.reason || d.reason || res.status}`);
    } catch (e) {
      setStatus(" ❌ " + e);
    }
    reload();
  };
  const syncDevices = async () => {
    setStatus(" … lade Geräte vom HEMS …");
    try {
      const res = await fetch("api/hems/rediscover", { method: "POST" });
      const d = await res.json();
      setStatus(
        d.source === "hems" ? ` ✅ ${d.device_count} Gerät(e) vom HEMS übernommen` : " ❌ HEMS nicht erreichbar / keine Geräte"
      );
    } catch (e) {
      setStatus(" ❌ " + e);
    }
  };
  return html`<div class="ha-card">
    <div class="card-title">HEMS-Rückkopplung<div class="card-actions">
      <button onClick=${refresh}>Aktualisieren</button>
      <button onClick=${testHems}>Jetzt prüfen</button>
      <button onClick=${syncDevices}>Geräte von HEMS neu laden</button>
    </div></div>
    <div class="toolbar"><span class="hint-inline">${status}</span></div>
    <p class="hint">Status-Rückkopplung (M3): EP liest den HEMS-Zustand (<code>/api/status</code>) und vergleicht die
      KI-Vorschläge mit dem Ist-Zustand. Die Aussage ist <strong>beobachtend</strong>. Gespiegelt als
      <code>sensor.ep_plan_status</code> und <code>sensor.ep_hems_verbindung</code>. HEMS-URL in der Addon-Config
      (<code>hems_base_url</code>) setzen.</p>
    <${HemsBody} data=${data} />
  </div>`;
}

function HemsBody({ data }) {
  if (!data) return html`<p class="hint-inline">…</p>`;
  if (!data.configured)
    return html`<h3 class="sub-title">Verbindung & Regelzyklus</h3>
      <${Kv} rows=${[["Status", "HEMS nicht konfiguriert (hems_base_url leer)"]]} />`;
  const rows = [
    ["Verbindung", data.online ? "🟢 online" : "🔴 offline"],
    ["Letzter Abruf", tsDE(data.last_fetch_ts)],
    ["Letzter Regelzyklus", data.last_cycle_at || "–"],
    ["Zyklen", data.cycle_count ?? "–"],
    ["Regelintervall (s)", data.interval_s ?? "–"],
    ["Pool", data.pool_w == null ? "–" : fmt(data.pool_w) + " W"],
    ["Defizit", data.current_deficit_w == null ? "–" : fmt(data.current_deficit_w) + " W"],
    ["Globaler Modus", modeDe(data.global_mode)],
    ["HEMS-Fehler", data.error || data.last_error || "–"],
  ];
  return html`<${Fragment}>
    <h3 class="sub-title">Verbindung & Regelzyklus</h3>
    <${Kv} rows=${rows} />
    <h3 class="sub-title">Plan-Rückkopplung</h3>
    <${HemsFeedback} fb=${data.feedback} />
    <h3 class="sub-title">HEMS-Gerätezustände</h3>
    <${HemsDevices} devices=${data.devices || []} />
  </${Fragment}>`;
}

function HemsFeedback({ fb }) {
  if (!fb) return html`<p>Keine Daten.</p>`;
  const [label, color] = HEMS_OVERALL[fb.overall] || [fb.overall, "#888"];
  const meta = [];
  if (fb.plan_id) meta.push(`Plan ${fb.plan_id}`);
  if (fb.valid_until) meta.push(`gültig bis ${fb.valid_until}`);
  if (fb.reason) meta.push(fb.reason);
  return html`<${Fragment}>
    <p>Gesamt: <span style="font-weight:bold;color:${color};">${label}</span>
      <span style="font-size:.8rem;color:#888;">${meta.join(" · ")}</span></p>
    ${(fb.devices || []).length
      ? (fb.devices || []).map((d, di) => {
          const vColor = d.verdict === "abweichend" ? "#c33" : d.verdict === "konform" ? "#2a8" : "#c93";
          return html`<${Fragment} key=${di}>
            <h3 style="font-size:.95rem;margin:.6rem 0 .25rem;">${d.label}
              <small style="font-weight:normal;color:${vColor};">(${d.verdict})</small>${d.matched
                ? ""
                : html` <small style="color:#c93;">nicht im HEMS gefunden</small>`}</h3>
            <table><thead><tr><th>Feld</th><th class="num">Vorschlag</th><th class="num">HEMS-Ist</th><th>✓</th></tr></thead>
              <tbody>${(d.fields || []).length
                ? (d.fields || []).map((f, i) => {
                    const sug = typeof f.vorschlag === "boolean" ? boolDe(f.vorschlag) : fmt(f.vorschlag);
                    const ist = f.ist == null ? "–" : typeof f.ist === "boolean" ? boolDe(f.ist) : fmt(f.ist);
                    return html`<tr key=${i}><td>${PLAN_FIELD_LABELS[f.feld] || f.feld}</td><td class="num">${sug}</td>
                      <td class="num">${ist}</td><td>${FIELD_STATUS[f.status] || f.status}</td></tr>`;
                  })
                : html`<tr><td>– keine vergleichbaren Felder –</td><td></td><td></td><td></td></tr>`}</tbody></table>
          </${Fragment}>`;
        })
      : html`<p>Keine Geräte im Plan.</p>`}
  </${Fragment}>`;
}

function HemsDevices({ devices }) {
  if (!devices.length) return html`<p>Keine Gerätezustände (HEMS offline oder ohne Geräte).</p>`;
  return html`<div class="table-wrap"><table>
    <thead><tr><th>Gerät</th><th>Typ</th><th class="num">Priorität</th><th>Freigegeben</th><th class="num">Ist</th></tr></thead>
    <tbody>${devices.map((d, i) => {
      const ist = d.type === "binary" ? (d.actual_on ? "an" : "aus") : d.actual_w == null ? "–" : fmt(d.actual_w) + " W";
      const typ = d.type === "binary" ? "binär" : d.type === "controllable" ? "regelbar" : d.type || "–";
      return html`<tr key=${i}><td>${d.label || d.id}</td><td>${typ}</td>
        <td class="num">${d.priority ?? "–"}</td><td>${boolDe(d.eligible)}</td><td class="num">${ist}</td></tr>`;
    })}</tbody>
  </table></div>`;
}

/* ============================================================
   Tab: Einstellungen
   ============================================================ */
function EinstellungenTab() {
  const [rows] = usePoll(() => api("api/entities"), false);
  const list = Array.isArray(rows) ? rows : [];
  return html`<div class="ha-card">
    <div class="card-title">Einstellungen (Anzeige)</div>
    <p class="hint">Die Zuordnung der Größen zu HA-Entitäten wird in der <strong>Addon-Konfiguration</strong> gepflegt
      (gleiche Seite wie das KI-Modell, Felder <code>entity_…</code>). Hier wird nur der
      aktuell geladene Stand angezeigt.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Größe</th><th>HA-Entität</th></tr></thead>
      <tbody>${list.map(
        (r, i) => html`<tr key=${i}><td>${r.label}${r.averaged ? "" : " *"}</td>
          <td><code>${r.entity_id ?? "–"}</code></td></tr>`
      )}</tbody>
    </table></div>
  </div>`;
}

/* ============================================================
   Tab: Logs
   ============================================================ */
function LogsTab() {
  const [rows, reload] = usePoll(() => api("api/logs?limit=200"), false);
  const list = Array.isArray(rows) ? [...rows].reverse() : [];
  return html`<div class="ha-card">
    <div class="card-title">Logs<div class="card-actions">
      <button onClick=${reload}>Aktualisieren</button>
      <a class="btn-link" href="api/logs/export">Export (JSONL)</a>
    </div></div>
    <div class="table-wrap"><table>
      <thead><tr><th>Zeit</th><th>Level</th><th>Komponente</th><th>Nachricht</th></tr></thead>
      <tbody>${list.map(
        (r, i) => html`<tr key=${i}><td>${r.ts}</td><td>${r.level}</td><td>${r.component}</td><td>${r.message}</td></tr>`
      )}</tbody>
    </table></div>
  </div>`;
}

/* ============================================================
   App-Schale: Kopfleiste, Tabs, aktiver Tab
   ============================================================ */
const TABS = [
  ["status", "Status", StatusTab],
  ["daten", "Daten", DatenTab],
  ["geraete", "Geräte", GeraeteTab],
  ["prognose", "Prognose", PrognoseTab],
  ["grenzen", "Grenzen & Ziele", GrenzenTab],
  ["plan", "Plan", PlanTab],
  ["hems", "HEMS", HemsTab],
  ["einstellungen", "Einstellungen", EinstellungenTab],
  ["logs", "Logs", LogsTab],
];

function App() {
  const [tab, setTab] = useState("status");
  // Handy: Tabellenzellen nach jedem Render/Poll mit Spaltenüberschriften versehen.
  useEffect(() => {
    const root = document.querySelector(".ha-content");
    if (!root) return undefined;
    const obs = new MutationObserver(() => labelizeTables(root));
    obs.observe(root, { childList: true, subtree: true });
    labelizeTables(root);
    return () => obs.disconnect();
  }, []);
  const Active = (TABS.find((t) => t[0] === tab) || TABS[0])[2];
  return html`
    <header class="ha-header">
      <div class="ha-header-top">
        <svg class="ha-logo" viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z"/></svg>
        <span class="ha-title">Skytech Energy Pilot</span>
      </div>
      <nav class="ha-tabs">
        ${TABS.map(
          ([id, lbl]) =>
            html`<button key=${id} data-tab=${id} class=${tab === id ? "active" : ""} onClick=${() => setTab(id)}>${lbl}</button>`
        )}
      </nav>
    </header>
    <main class="ha-content">
      <section class="tab active"><${Active} /></section>
    </main>`;
}

render(html`<${App} />`, document.getElementById("app"));
