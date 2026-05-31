/* Prusa Connect Card for Home Assistant
 *
 * A Lovelace card that displays Prusa printer status, temperatures, and print
 * progress. Pairs with the Prusa Connect integration.
 *
 * Usage:
 *   type: custom:prusa-connect-card
 *   entity_prefix: sensor.prusa_mini   # the common prefix of your sensors
 *   name: Prusa Mini                   # optional title
 */

const PRUSA_CARD_VERSION = "2.0.0";

// Sensor suffixes created by the integration (sensor.<prefix>_<suffix>).
const SUFFIX = {
  status: "status",
  nozzle: "nozzle_temperature",
  nozzleTarget: "nozzle_target_temperature",
  bed: "bed_temperature",
  bedTarget: "bed_target_temperature",
  progress: "progress",
  project: "project_name",
  material: "material",
  zHeight: "z_height",
  speed: "print_speed",
  flow: "flow",
  fanPrint: "fan_print",
  fanHotend: "fan_hotend",
  timeRemaining: "time_remaining",
  timePrinting: "time_printing",
};

class PrusaConnectCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
  }

  setConfig(config) {
    if (!config || !config.entity_prefix) {
      throw new Error(
        'You must define "entity_prefix" (e.g. sensor.prusa_mini).'
      );
    }
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 4;
  }

  static getConfigElement() {
    return document.createElement("prusa-connect-card-editor");
  }

  static getStubConfig() {
    return {
      type: "custom:prusa-connect-card",
      entity_prefix: "sensor.prusa_connect",
    };
  }

  // -- helpers ------------------------------------------------------------

  _entityId(suffix) {
    const prefix = (this._config.entity_prefix || "").replace(/\.$/, "");
    return `${prefix}_${suffix}`;
  }

  _state(suffix) {
    if (!this._hass) return null;
    const obj = this._hass.states[this._entityId(suffix)];
    if (!obj || obj.state === "unknown" || obj.state === "unavailable") {
      return null;
    }
    return obj.state;
  }

  _num(suffix) {
    const s = this._state(suffix);
    if (s === null) return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }

  _fmtDuration(seconds) {
    if (seconds === null) return "—";
    let s = Math.max(0, Math.round(seconds));
    const h = Math.floor(s / 3600);
    s -= h * 3600;
    const m = Math.floor(s / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  // -- rendering ----------------------------------------------------------

  _render() {
    if (!this._hass || !this._config.entity_prefix) {
      this.shadowRoot.innerHTML = "";
      return;
    }

    const status = this._state(SUFFIX.status) || "Unknown";
    const project = this._state(SUFFIX.project);
    const material = this._state(SUFFIX.material);
    const nozzle = this._num(SUFFIX.nozzle);
    const nozzleTarget = this._num(SUFFIX.nozzleTarget);
    const bed = this._num(SUFFIX.bed);
    const bedTarget = this._num(SUFFIX.bedTarget);
    const progress = this._num(SUFFIX.progress);
    const zHeight = this._num(SUFFIX.zHeight);
    const speed = this._num(SUFFIX.speed);
    const remaining = this._num(SUFFIX.timeRemaining);

    const title = this._config.name || "Prusa Printer";
    const pct = progress === null ? 0 : Math.max(0, Math.min(100, progress));
    const printing = ["Printing", "Busy"].includes(status);

    const temp = (cur, tgt) => {
      if (cur === null) return "—";
      const c = `${cur.toFixed(1)}°`;
      if (tgt && tgt > 0) return `${c} → ${tgt.toFixed(0)}°`;
      return c;
    };

    this.shadowRoot.innerHTML = `
      <style>
        ha-card {
          padding: 16px;
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .header {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          margin-bottom: 12px;
        }
        .title { font-size: 1.3em; font-weight: 500; }
        .status {
          font-size: 0.95em;
          padding: 2px 10px;
          border-radius: 12px;
          background: ${printing
            ? "var(--success-color, #43a047)"
            : "var(--secondary-background-color, #e0e0e0)"};
          color: ${printing ? "#fff" : "var(--primary-text-color)"};
        }
        .project {
          color: var(--secondary-text-color);
          font-size: 0.9em;
          margin-bottom: 12px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .progress-wrap {
          background: var(--divider-color, #bdbdbd);
          border-radius: 6px;
          height: 12px;
          overflow: hidden;
          margin-bottom: 4px;
        }
        .progress-bar {
          background: var(--primary-color, #ff6f00);
          height: 100%;
          width: ${pct}%;
          transition: width 0.5s ease;
        }
        .progress-row {
          display: flex;
          justify-content: space-between;
          font-size: 0.85em;
          color: var(--secondary-text-color);
          margin-bottom: 14px;
        }
        .grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 10px;
        }
        .stat {
          background: var(--secondary-background-color, #f5f5f5);
          border-radius: 8px;
          padding: 8px 12px;
        }
        .stat .label {
          font-size: 0.75em;
          color: var(--secondary-text-color);
          text-transform: uppercase;
          letter-spacing: 0.03em;
        }
        .stat .value { font-size: 1.05em; font-weight: 500; margin-top: 2px; }
      </style>
      <ha-card>
        <div class="header">
          <span class="title">${title}</span>
          <span class="status">${status}</span>
        </div>
        ${project ? `<div class="project">📄 ${project}</div>` : ""}
        ${
          printing || progress !== null
            ? `<div class="progress-wrap"><div class="progress-bar"></div></div>
               <div class="progress-row">
                 <span>${pct.toFixed(0)}%</span>
                 <span>${
                   remaining !== null
                     ? this._fmtDuration(remaining) + " left"
                     : ""
                 }</span>
               </div>`
            : ""
        }
        <div class="grid">
          <div class="stat">
            <div class="label">Nozzle</div>
            <div class="value">${temp(nozzle, nozzleTarget)}</div>
          </div>
          <div class="stat">
            <div class="label">Bed</div>
            <div class="value">${temp(bed, bedTarget)}</div>
          </div>
          ${
            material
              ? `<div class="stat"><div class="label">Material</div><div class="value">${material}</div></div>`
              : ""
          }
          ${
            zHeight !== null
              ? `<div class="stat"><div class="label">Z Height</div><div class="value">${zHeight.toFixed(
                  2
                )} mm</div></div>`
              : ""
          }
          ${
            speed !== null
              ? `<div class="stat"><div class="label">Speed</div><div class="value">${speed}%</div></div>`
              : ""
          }
        </div>
      </ha-card>
    `;
  }
}

class PrusaConnectCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  _render() {
    if (this.shadowRoot) {
      // already rendered
    } else {
      this.attachShadow({ mode: "open" });
    }
    const cfg = this._config || {};
    this.shadowRoot.innerHTML = `
      <style>
        .form { display: flex; flex-direction: column; gap: 12px; padding: 8px; }
        label { font-size: 0.85em; color: var(--secondary-text-color); }
        input {
          width: 100%; padding: 8px; box-sizing: border-box;
          border: 1px solid var(--divider-color, #bdbdbd); border-radius: 4px;
          background: var(--card-background-color); color: var(--primary-text-color);
        }
      </style>
      <div class="form">
        <div>
          <label>Entity prefix (e.g. sensor.prusa_mini)</label>
          <input id="entity_prefix" value="${cfg.entity_prefix || ""}" />
        </div>
        <div>
          <label>Card title (optional)</label>
          <input id="name" value="${cfg.name || ""}" />
        </div>
      </div>
    `;
    this.shadowRoot.querySelectorAll("input").forEach((el) => {
      el.addEventListener("input", () => this._valueChanged());
    });
  }

  _valueChanged() {
    const prefix = this.shadowRoot.getElementById("entity_prefix").value;
    const name = this.shadowRoot.getElementById("name").value;
    const newConfig = {
      ...this._config,
      type: "custom:prusa-connect-card",
      entity_prefix: prefix,
    };
    if (name) newConfig.name = name;
    else delete newConfig.name;
    this._config = newConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: newConfig },
        bubbles: true,
        composed: true,
      })
    );
  }
}

customElements.define("prusa-connect-card", PrusaConnectCard);
customElements.define("prusa-connect-card-editor", PrusaConnectCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "prusa-connect-card",
  name: "Prusa Connect Card",
  description: "Displays Prusa printer status, temperatures, and print progress.",
  preview: true,
  documentationURL: "https://github.com/npolanosky/prusa_home_assistant",
});

console.info(
  `%c PRUSA-CONNECT-CARD %c v${PRUSA_CARD_VERSION} `,
  "color: white; background: #ff6f00; font-weight: 700;",
  "color: #ff6f00; background: white; font-weight: 700;"
);
