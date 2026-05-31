/* Prusa Connect Card for Home Assistant
 *
 * A Lovelace card styled after the ha-bambulab print_status card: a Prusa Mini
 * illustration with live temperature/progress pills overlaid on it, the current
 * print's thumbnail on the bed, and a progress bar with time remaining.
 *
 * Configure by picking your Prusa printer DEVICE in the visual editor; the card
 * resolves all entities from that device automatically. An entity_prefix is
 * still accepted for backwards compatibility.
 */

const PRUSA_CARD_VERSION = "3.0.0";

// Entity registry translation_keys created by the integration.
const KEYS = [
  "status",
  "nozzle_temperature",
  "nozzle_target_temperature",
  "bed_temperature",
  "bed_target_temperature",
  "progress",
  "project_name",
  "material",
  "z_height",
  "print_speed",
  "flow",
  "fan_print",
  "fan_hotend",
  "time_remaining",
  "time_printing",
];

// Inline SVG illustration of a Prusa Mini (orange cantilever, single Z arm).
function prusaMiniSvg(nozzleHot, bedHot, accent) {
  const nozzleColor = nozzleHot ? "#ff6b35" : "#b0b0b0";
  const bedColor = bedHot ? "#ff8a50" : "#3a3a3a";
  return `
  <svg viewBox="0 0 260 240" xmlns="http://www.w3.org/2000/svg">
    <!-- base -->
    <rect x="40" y="196" width="180" height="20" rx="4" fill="#2b2b2b"/>
    <rect x="46" y="190" width="168" height="10" rx="3" fill="#383838"/>
    <!-- bed -->
    <rect x="60" y="182" width="150" height="10" rx="2" fill="${bedColor}"/>
    <rect x="64" y="180" width="142" height="4" rx="2" fill="${bedColor}" opacity="0.5"/>
    <!-- vertical Z tower (right side, Mini's signature) -->
    <rect x="196" y="40" width="20" height="156" rx="3" fill="${accent}"/>
    <rect x="201" y="44" width="10" height="148" rx="2" fill="#00000022"/>
    <!-- top cap -->
    <rect x="190" y="34" width="32" height="12" rx="3" fill="#2b2b2b"/>
    <!-- X arm (cantilever) -->
    <rect x="70" y="70" width="132" height="14" rx="3" fill="${accent}"/>
    <!-- carriage + extruder -->
    <rect x="96" y="64" width="34" height="40" rx="4" fill="#d8d8d8"/>
    <rect x="100" y="68" width="26" height="22" rx="2" fill="#9a9a9a"/>
    <!-- nozzle -->
    <polygon points="106,104 120,104 113,118" fill="${nozzleColor}"/>
    <!-- spool holder -->
    <circle cx="232" cy="60" r="4" fill="#2b2b2b"/>
  </svg>`;
}

class PrusaConnectCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._entities = {};
    this._resolvedFor = null;
  }

  setConfig(config) {
    if (!config || (!config.device_id && !config.entity_prefix)) {
      throw new Error(
        "Pick your Prusa printer device (or set entity_prefix)."
      );
    }
    this._config = config;
    this._resolvedFor = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._resolveEntities();
    this._render();
  }

  getCardSize() {
    return 6;
  }

  static getConfigElement() {
    return document.createElement("prusa-connect-card-editor");
  }

  static getStubConfig() {
    return { type: "custom:prusa-connect-card" };
  }

  // -- entity resolution --------------------------------------------------

  _resolveEntities() {
    if (!this._hass) return;
    // Resolve once per (device_id|prefix) unless config changed.
    const sig = this._config.device_id || this._config.entity_prefix || "";
    if (this._resolvedFor === sig) return;
    this._resolvedFor = sig;

    const map = {};
    if (this._config.device_id && this._hass.entities) {
      // Walk the entity registry, keep entities on the chosen device,
      // key them by translation_key (robust against entity_id renames).
      for (const entId in this._hass.entities) {
        const reg = this._hass.entities[entId];
        if (reg.device_id !== this._config.device_id) continue;
        const key = reg.translation_key;
        if (key && KEYS.includes(key)) {
          map[key] = reg.entity_id;
        }
      }
      // Camera / job-preview live on the same device.
      for (const entId in this._hass.entities) {
        const reg = this._hass.entities[entId];
        if (reg.device_id !== this._config.device_id) continue;
        if (reg.entity_id.startsWith("camera.")) {
          if (reg.translation_key === "printer_camera") map.camera = reg.entity_id;
          else if (!map.preview) map.preview = reg.entity_id;
        }
      }
    } else if (this._config.entity_prefix) {
      const prefix = this._config.entity_prefix.replace(/\.$/, "");
      for (const key of KEYS) map[key] = `${prefix}_${key}`;
    }
    this._entities = map;
  }

  // -- value helpers ------------------------------------------------------

  _obj(key) {
    if (!this._hass) return null;
    const id = this._entities[key];
    if (!id) return null;
    return this._hass.states[id] || null;
  }

  _state(key) {
    const o = this._obj(key);
    if (!o || o.state === "unknown" || o.state === "unavailable") return null;
    return o.state;
  }

  _num(key) {
    const s = this._state(key);
    if (s === null) return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  _fmtDuration(seconds) {
    if (seconds === null) return null;
    let s = Math.max(0, Math.round(seconds));
    const h = Math.floor(s / 3600);
    s -= h * 3600;
    const m = Math.floor(s / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  _previewUrl() {
    const o = this._obj("preview") || this._obj("camera");
    if (!o || !o.attributes || !o.attributes.entity_picture) return null;
    return `${o.attributes.entity_picture}&state=${o.state}`;
  }

  // -- rendering ----------------------------------------------------------

  _render() {
    if (!this._hass || !this._config) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const accent = "#fa6831";
    const status = this._state("status") || "Unknown";
    const printing = ["Printing", "Busy"].includes(status);
    const paused = status === "Paused";
    const project = this._state("project_name");
    const material = this._state("material");
    const nozzle = this._num("nozzle_temperature");
    const nozzleTgt = this._num("nozzle_target_temperature");
    const bed = this._num("bed_temperature");
    const bedTgt = this._num("bed_target_temperature");
    const progress = this._num("progress");
    const zHeight = this._num("z_height");
    const speed = this._num("print_speed");
    const remaining = this._fmtDuration(this._num("time_remaining"));
    const preview = this._previewUrl();

    const title = this._config.name || "Prusa Mini";
    const pct = progress === null ? 0 : Math.max(0, Math.min(100, progress));
    const nozzleHot = nozzle !== null && nozzle > 50;
    const bedHot = bed !== null && bed > 30;

    const statusColor = printing
      ? "#43a047"
      : paused
      ? "#fb8c00"
      : status === "Error"
      ? "#e53935"
      : "#9e9e9e";

    const tempStr = (cur, tgt) => {
      if (cur === null) return "—";
      const c = `${Math.round(cur)}°`;
      if (tgt && tgt > 0) return `${c} → ${Math.round(tgt)}°`;
      return c;
    };

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          --pc-accent: ${accent};
          --pc-bg: var(--card-background-color, #1c1c1c);
          --pc-text: var(--primary-text-color, #e8e8e8);
          --pc-text2: var(--secondary-text-color, #9aa0a6);
        }
        ha-card {
          background: var(--pc-bg);
          color: var(--pc-text);
          border-radius: 12px;
          overflow: hidden;
          padding: 0;
        }
        .hdr {
          display: flex; align-items: center; justify-content: space-between;
          padding: 14px 16px 6px;
        }
        .title { font-size: 1.15em; font-weight: 600; }
        .badge {
          font-size: 0.72em; font-weight: 700; letter-spacing: 0.06em;
          text-transform: uppercase; padding: 4px 10px; border-radius: 12px;
          color: #fff; background: ${statusColor};
        }
        .stage {
          position: relative; width: 100%;
          aspect-ratio: 13 / 10; max-height: 260px;
          display: flex; align-items: center; justify-content: center;
        }
        .stage svg { width: 86%; height: 86%; }
        .pill {
          position: absolute; transform: translate(-50%, -50%);
          background: rgba(0,0,0,0.34); border-radius: 10px;
          padding: 5px 9px; text-align: center; line-height: 1.15;
          box-shadow: 0 0 8px rgba(0,0,0,0.35); z-index: 2;
        }
        .pill .lbl {
          font-size: 0.6em; text-transform: uppercase; letter-spacing: 0.05em;
          color: var(--pc-text2);
        }
        .pill .val { font-size: 0.95em; font-weight: 600; }
        .pill.hot { background: rgba(255,100,0,0.22); box-shadow: 0 0 18px rgba(255,100,0,0.45); }
        .cover {
          position: absolute; left: 50%; top: 78%;
          transform: translate(-50%, -50%);
          width: 54%; aspect-ratio: 1; z-index: 1;
          border-radius: 6px; overflow: hidden;
          box-shadow: 0 2px 10px rgba(0,0,0,0.5);
          background: #00000033;
        }
        .cover img { width: 100%; height: 100%; object-fit: contain; display: block; }
        .footer { padding: 6px 16px 16px; }
        .proj {
          color: var(--pc-text2); font-size: 0.85em; margin-bottom: 8px;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .bar { background: rgba(255,255,255,0.12); border-radius: 6px; height: 10px; overflow: hidden; }
        .fill {
          height: 100%; width: ${pct}%;
          background: linear-gradient(90deg, var(--pc-accent), #ff9a5c);
          transition: width 0.6s ease;
        }
        .barrow {
          display: flex; justify-content: space-between;
          font-size: 0.82em; color: var(--pc-text2); margin-top: 5px;
        }
        .pct { color: var(--pc-accent); font-weight: 700; }
        .chips { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
        .chip {
          flex: 1; min-width: 64px; background: rgba(255,255,255,0.05);
          border-radius: 8px; padding: 7px 10px; text-align: center;
        }
        .chip .lbl {
          font-size: 0.62em; text-transform: uppercase; letter-spacing: 0.05em;
          color: var(--pc-text2);
        }
        .chip .val { font-size: 0.98em; font-weight: 600; margin-top: 2px; }
      </style>
      <ha-card>
        <div class="hdr">
          <span class="title">${title}</span>
          <span class="badge">${status}</span>
        </div>

        <div class="stage">
          ${prusaMiniSvg(nozzleHot, bedHot, accent)}
          <div class="pill ${nozzleHot ? "hot" : ""}" style="left:30%; top:34%;">
            <div class="lbl">Nozzle</div>
            <div class="val">${tempStr(nozzle, nozzleTgt)}</div>
          </div>
          <div class="pill ${bedHot ? "hot" : ""}" style="left:70%; top:91%;">
            <div class="lbl">Bed</div>
            <div class="val">${tempStr(bed, bedTgt)}</div>
          </div>
          ${
            preview
              ? `<div class="cover"><img src="${preview}" alt="print preview"/></div>`
              : ""
          }
        </div>

        <div class="footer">
          ${project ? `<div class="proj">📄 ${project}</div>` : ""}
          ${
            printing || paused || progress !== null
              ? `<div class="bar"><div class="fill"></div></div>
                 <div class="barrow">
                   <span class="pct">${pct.toFixed(0)}%</span>
                   <span>${remaining ? remaining + " left" : ""}</span>
                 </div>`
              : ""
          }
          <div class="chips">
            ${material ? `<div class="chip"><div class="lbl">Material</div><div class="val">${material}</div></div>` : ""}
            ${zHeight !== null ? `<div class="chip"><div class="lbl">Z Height</div><div class="val">${zHeight.toFixed(2)} mm</div></div>` : ""}
            ${speed !== null ? `<div class="chip"><div class="lbl">Speed</div><div class="val">${speed}%</div></div>` : ""}
          </div>
        </div>
      </ha-card>
    `;
  }
}

class PrusaConnectCardEditor extends HTMLElement {
  constructor() {
    super();
    this._config = {};
  }

  setConfig(config) {
    this._config = config || {};
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  _schema() {
    return [
      {
        name: "device_id",
        label: "Prusa printer",
        selector: { device: { integration: "prusa_connect" } },
      },
      { name: "name", label: "Card title (optional)", selector: { text: {} } },
    ];
  }

  _render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => s.label || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        const val = { ...this._config, ...ev.detail.value };
        val.type = "custom:prusa-connect-card";
        if (!val.name) delete val.name;
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: val },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.shadowRoot.appendChild(this._form);
    }
    if (this._hass) this._form.hass = this._hass;
    this._form.data = this._config;
    this._form.schema = this._schema();
  }
}

customElements.define("prusa-connect-card", PrusaConnectCard);
customElements.define("prusa-connect-card-editor", PrusaConnectCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "prusa-connect-card",
  name: "Prusa Connect Card",
  description: "Prusa printer status, temperatures, progress, and print preview.",
  preview: true,
  documentationURL: "https://github.com/npolanosky/prusa_home_assistant",
});

console.info(
  `%c PRUSA-CONNECT-CARD %c v${PRUSA_CARD_VERSION} `,
  "color: white; background: #fa6831; font-weight: 700;",
  "color: #fa6831; background: #1c1c1c; font-weight: 700;"
);
