/**
 * Prusa Connect Card for Home Assistant
 * A custom Lovelace card for Prusa 3D printers via Prusa Connect
 */

const CARD_VERSION = "1.0.0";

const PRINTER_STATES = {
  IDLE: { label: "Idle", color: "#4caf50", icon: "mdi:printer-3d" },
  PRINTING: { label: "Printing", color: "#2196f3", icon: "mdi:printer-3d-nozzle" },
  BUSY: { label: "Busy", color: "#ff9800", icon: "mdi:printer-3d" },
  PAUSED: { label: "Paused", color: "#ff9800", icon: "mdi:pause-circle" },
  FINISHED: { label: "Finished", color: "#4caf50", icon: "mdi:check-circle" },
  STOPPED: { label: "Stopped", color: "#f44336", icon: "mdi:stop-circle" },
  ERROR: { label: "Error", color: "#f44336", icon: "mdi:alert-circle" },
  ATTENTION: { label: "Attention", color: "#ff9800", icon: "mdi:alert" },
  READY: { label: "Ready", color: "#4caf50", icon: "mdi:printer-3d" },
  ONLINE: { label: "Online", color: "#4caf50", icon: "mdi:printer-3d" },
  OFFLINE: { label: "Offline", color: "#9e9e9e", icon: "mdi:printer-3d-off" },
  UNKNOWN: { label: "Unknown", color: "#9e9e9e", icon: "mdi:help-circle" },
};

class PrusaConnectCard extends HTMLElement {
  static get properties() {
    return { hass: {}, config: {} };
  }

  set hass(hass) {
    this._hass = hass;
    if (this._initialized) {
      this._updateCard();
    } else {
      this._render();
      this._initialized = true;
    }
  }

  setConfig(config) {
    if (!config.entity_prefix) {
      throw new Error("Please define entity_prefix (e.g., sensor.prusa_mini)");
    }
    this._config = config;
    this._initialized = false;
  }

  getCardSize() {
    return 6;
  }

  static getConfigElement() {
    return document.createElement("prusa-connect-card-editor");
  }

  static getStubConfig() {
    return {
      entity_prefix: "sensor.prusa_connect",
      name: "Prusa Mini",
      show_camera: false,
    };
  }

  _getEntity(suffix) {
    const entityId = `${this._config.entity_prefix}_${suffix}`;
    return this._hass?.states[entityId];
  }

  _getVal(suffix, fallback = null) {
    const entity = this._getEntity(suffix);
    if (!entity || entity.state === "unavailable" || entity.state === "unknown") {
      return fallback;
    }
    return entity.state;
  }

  _getNumVal(suffix, fallback = null) {
    const val = this._getVal(suffix);
    if (val === null || val === undefined) return fallback;
    const num = parseFloat(val);
    return isNaN(num) ? fallback : num;
  }

  _formatTime(seconds) {
    if (seconds === null || seconds === undefined) return "--:--";
    const s = parseInt(seconds, 10);
    if (isNaN(s) || s < 0) return "--:--";
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  _getStateInfo() {
    const state = (this._getVal("status", "UNKNOWN") || "UNKNOWN").toUpperCase();
    return PRINTER_STATES[state] || PRINTER_STATES.UNKNOWN;
  }

  _render() {
    if (!this._config || !this._hass) return;

    const shadow = this.shadowRoot || this.attachShadow({ mode: "open" });
    shadow.innerHTML = "";

    const card = document.createElement("ha-card");
    card.innerHTML = `
      <style>
        :host {
          --pc-primary: #fa6831;
          --pc-bg: var(--card-background-color, #1c1c1c);
          --pc-text: var(--primary-text-color, #e0e0e0);
          --pc-text-secondary: var(--secondary-text-color, #999);
          --pc-border: rgba(255,255,255,0.06);
        }
        ha-card {
          background: var(--pc-bg);
          color: var(--pc-text);
          border-radius: 12px;
          overflow: hidden;
          font-family: var(--ha-card-font-family, 'Roboto', sans-serif);
        }
        .card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 16px 8px;
        }
        .printer-name {
          font-size: 16px;
          font-weight: 500;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .printer-name img {
          height: 20px;
        }
        .status-badge {
          font-size: 12px;
          font-weight: 500;
          padding: 4px 10px;
          border-radius: 12px;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .printer-visual {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 12px 20px;
          min-height: 160px;
        }
        .printer-svg {
          width: 140px;
          height: 140px;
          opacity: 0.9;
        }
        .temp-display {
          position: absolute;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .temp-display.left {
          left: 20px;
          top: 50%;
          transform: translateY(-50%);
        }
        .temp-display.right {
          right: 20px;
          top: 50%;
          transform: translateY(-50%);
        }
        .temp-item {
          text-align: center;
          padding: 8px 12px;
          border-radius: 8px;
          background: rgba(255,255,255,0.04);
          min-width: 72px;
        }
        .temp-label {
          font-size: 10px;
          color: var(--pc-text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 2px;
        }
        .temp-value {
          font-size: 22px;
          font-weight: 600;
          font-variant-numeric: tabular-nums;
        }
        .temp-target {
          font-size: 11px;
          color: var(--pc-text-secondary);
          margin-top: 1px;
        }
        .progress-section {
          padding: 0 16px 12px;
        }
        .progress-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 6px;
          font-size: 13px;
        }
        .progress-file {
          color: var(--pc-text);
          font-weight: 500;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 200px;
        }
        .progress-pct {
          font-weight: 600;
          color: var(--pc-primary);
          font-size: 15px;
          font-variant-numeric: tabular-nums;
        }
        .progress-bar-bg {
          height: 6px;
          background: rgba(255,255,255,0.08);
          border-radius: 3px;
          overflow: hidden;
        }
        .progress-bar-fill {
          height: 100%;
          border-radius: 3px;
          background: linear-gradient(90deg, var(--pc-primary), #ff8a50);
          transition: width 1s ease;
        }
        .progress-times {
          display: flex;
          justify-content: space-between;
          margin-top: 6px;
          font-size: 12px;
          color: var(--pc-text-secondary);
        }
        .info-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 1px;
          background: var(--pc-border);
          border-top: 1px solid var(--pc-border);
        }
        .info-item {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 16px;
          background: var(--pc-bg);
        }
        .info-icon {
          color: var(--pc-text-secondary);
          --mdi-icon-size: 18px;
          width: 18px;
          height: 18px;
        }
        .info-content {
          display: flex;
          flex-direction: column;
        }
        .info-label {
          font-size: 10px;
          color: var(--pc-text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .info-value {
          font-size: 13px;
          font-weight: 500;
          font-variant-numeric: tabular-nums;
        }
        .camera-section {
          border-top: 1px solid var(--pc-border);
          padding: 0;
        }
        .camera-section img {
          width: 100%;
          display: block;
        }
        .no-data {
          padding: 24px;
          text-align: center;
          color: var(--pc-text-secondary);
          font-size: 14px;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }
        .printing .status-badge {
          animation: pulse 2s ease-in-out infinite;
        }
      </style>

      <div class="card-content" id="card-content">
        <div class="no-data">Loading printer data...</div>
      </div>
    `;

    shadow.appendChild(card);
    this._card = card;
    this._contentEl = card.querySelector("#card-content");
    this._updateCard();
  }

  _updateCard() {
    if (!this._contentEl || !this._hass || !this._config) return;

    const stateInfo = this._getStateInfo();
    const isPrinting = ["PRINTING", "BUSY"].includes(
      (this._getVal("status", "") || "").toUpperCase()
    );
    const name = this._config.name || "Prusa Mini";
    const nozzleTemp = this._getNumVal("nozzle_temperature");
    const bedTemp = this._getNumVal("bed_temperature");
    const nozzleTarget = this._getNumVal("nozzle_target_temperature");
    const bedTarget = this._getNumVal("bed_target_temperature");
    const progress = this._getNumVal("progress", 0);
    const projectName = this._getVal("project_name");
    const timeRemaining = this._getVal("time_remaining");
    const timePrinting = this._getVal("time_printing");
    const material = this._getVal("material", "--");
    const zHeight = this._getNumVal("z_height");
    const printSpeed = this._getNumVal("print_speed");

    const nozzleTempStr = nozzleTemp !== null ? `${Math.round(nozzleTemp)}°C` : "--";
    const bedTempStr = bedTemp !== null ? `${Math.round(bedTemp)}°C` : "--";
    const nozzleTargetStr = nozzleTarget !== null ? `→ ${Math.round(nozzleTarget)}°C` : "";
    const bedTargetStr = bedTarget !== null ? `→ ${Math.round(bedTarget)}°C` : "";

    this._contentEl.innerHTML = `
      <div class="card-header ${isPrinting ? "printing" : ""}">
        <div class="printer-name">
          <ha-icon icon="mdi:printer-3d"></ha-icon>
          ${name}
        </div>
        <span class="status-badge" style="background: ${stateInfo.color}22; color: ${stateInfo.color};">
          ${stateInfo.label}
        </span>
      </div>

      <div class="printer-visual">
        <div class="temp-display left">
          <div class="temp-item">
            <div class="temp-label">Nozzle</div>
            <div class="temp-value">${nozzleTempStr}</div>
            ${nozzleTargetStr ? `<div class="temp-target">${nozzleTargetStr}</div>` : ""}
          </div>
        </div>

        <svg class="printer-svg" viewBox="0 0 200 200" fill="none" xmlns="http://www.w3.org/2000/svg">
          <!-- Prusa Mini simplified illustration -->
          <!-- Frame -->
          <rect x="50" y="30" width="8" height="140" rx="2" fill="#555"/>
          <rect x="142" y="30" width="8" height="140" rx="2" fill="#555"/>
          <rect x="46" y="26" width="108" height="10" rx="3" fill="#666"/>

          <!-- Z-axis rod -->
          <rect x="96" y="36" width="4" height="130" rx="1" fill="#888"/>

          <!-- X-axis bar (moves up/down) -->
          <rect x="54" y="${isPrinting ? 80 + (100 - progress) * 0.6 : 80}" width="92" height="6" rx="2" fill="var(--pc-primary, #fa6831)" opacity="0.9"/>

          <!-- Print head -->
          <rect x="${isPrinting ? 80 + Math.sin(Date.now() / 500) * 15 : 90}" y="${isPrinting ? 72 + (100 - progress) * 0.6 : 72}" width="16" height="16" rx="3" fill="#ddd"/>
          <!-- Nozzle -->
          <polygon points="${isPrinting ? 85 + Math.sin(Date.now() / 500) * 15 : 95},${isPrinting ? 88 + (100 - progress) * 0.6 : 88} ${isPrinting ? 91 + Math.sin(Date.now() / 500) * 15 : 101},${isPrinting ? 88 + (100 - progress) * 0.6 : 88} ${isPrinting ? 88 + Math.sin(Date.now() / 500) * 15 : 98},${isPrinting ? 94 + (100 - progress) * 0.6 : 94}" fill="${nozzleTemp && nozzleTemp > 50 ? '#ff6b35' : '#aaa'}"/>

          <!-- Bed -->
          <rect x="40" y="170" width="120" height="8" rx="2" fill="${bedTemp && bedTemp > 30 ? '#ff8a50' : '#444'}"/>
          <rect x="44" y="168" width="112" height="4" rx="1" fill="${bedTemp && bedTemp > 30 ? '#ffab76' : '#555'}" opacity="0.6"/>

          <!-- Base -->
          <rect x="30" y="178" width="140" height="12" rx="3" fill="#444"/>

          <!-- LCD Screen -->
          <rect x="60" y="182" width="30" height="6" rx="1" fill="#1a3a2a"/>
          <rect x="61" y="183" width="28" height="4" rx="1" fill="#2d5a3d" opacity="0.6"/>

          <!-- Spool holder -->
          <circle cx="160" cy="50" r="18" stroke="#666" stroke-width="3" fill="none"/>
          <circle cx="160" cy="50" r="6" fill="#555"/>
          <circle cx="160" cy="50" r="16" stroke="${material === 'PLA' ? '#4caf50' : material === 'PETG' ? '#2196f3' : material === 'ASA' ? '#ff9800' : '#888'}" stroke-width="5" fill="none" opacity="0.5"
            stroke-dasharray="${isPrinting ? `${80 - progress * 0.6} 100` : '80 100'}"/>
        </svg>

        <div class="temp-display right">
          <div class="temp-item">
            <div class="temp-label">Bed</div>
            <div class="temp-value">${bedTempStr}</div>
            ${bedTargetStr ? `<div class="temp-target">${bedTargetStr}</div>` : ""}
          </div>
        </div>
      </div>

      ${isPrinting ? `
        <div class="progress-section">
          <div class="progress-header">
            <span class="progress-file" title="${projectName || ''}">${projectName || "Printing..."}</span>
            <span class="progress-pct">${progress}%</span>
          </div>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" style="width: ${progress}%"></div>
          </div>
          <div class="progress-times">
            <span>Elapsed: ${this._formatTime(timePrinting)}</span>
            <span>Remaining: ${this._formatTime(timeRemaining)}</span>
          </div>
        </div>
      ` : ""}

      <div class="info-grid">
        <div class="info-item">
          <ha-icon class="info-icon" icon="mdi:circle-slice-8"></ha-icon>
          <div class="info-content">
            <span class="info-label">Material</span>
            <span class="info-value">${material || "--"}</span>
          </div>
        </div>
        <div class="info-item">
          <ha-icon class="info-icon" icon="mdi:speedometer"></ha-icon>
          <div class="info-content">
            <span class="info-label">Speed</span>
            <span class="info-value">${printSpeed !== null ? printSpeed + "%" : "--"}</span>
          </div>
        </div>
        ${isPrinting ? `
          <div class="info-item">
            <ha-icon class="info-icon" icon="mdi:axis-z-arrow"></ha-icon>
            <div class="info-content">
              <span class="info-label">Z Height</span>
              <span class="info-value">${zHeight !== null ? zHeight.toFixed(1) + " mm" : "--"}</span>
            </div>
          </div>
          <div class="info-item">
            <ha-icon class="info-icon" icon="mdi:file-cad"></ha-icon>
            <div class="info-content">
              <span class="info-label">File</span>
              <span class="info-value" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;" title="${projectName || ""}">${projectName || "--"}</span>
            </div>
          </div>
        ` : `
          <div class="info-item">
            <ha-icon class="info-icon" icon="mdi:axis-z-arrow"></ha-icon>
            <div class="info-content">
              <span class="info-label">Z Height</span>
              <span class="info-value">${zHeight !== null ? zHeight.toFixed(1) + " mm" : "--"}</span>
            </div>
          </div>
          <div class="info-item">
            <ha-icon class="info-icon" icon="mdi:information-outline"></ha-icon>
            <div class="info-content">
              <span class="info-label">Firmware</span>
              <span class="info-value">${this._getVal("firmware", "--") || "--"}</span>
            </div>
          </div>
        `}
      </div>
    `;
  }
}

class PrusaConnectCardEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  _render() {
    if (!this._config) return;

    this.innerHTML = `
      <style>
        .editor-row {
          display: flex;
          flex-direction: column;
          margin-bottom: 12px;
        }
        .editor-row label {
          font-weight: 500;
          margin-bottom: 4px;
          font-size: 14px;
        }
        .editor-row input {
          padding: 8px;
          border: 1px solid var(--divider-color, #333);
          border-radius: 4px;
          background: var(--card-background-color, #1c1c1c);
          color: var(--primary-text-color, #e0e0e0);
          font-size: 14px;
        }
        .editor-row .hint {
          font-size: 12px;
          color: var(--secondary-text-color, #888);
          margin-top: 4px;
        }
      </style>
      <div class="editor-row">
        <label>Entity Prefix</label>
        <input id="entity_prefix" type="text" value="${this._config.entity_prefix || ""}" />
        <span class="hint">The prefix for your Prusa sensor entities (e.g., sensor.prusa_connect)</span>
      </div>
      <div class="editor-row">
        <label>Printer Name</label>
        <input id="name" type="text" value="${this._config.name || "Prusa Mini"}" />
      </div>
    `;

    this.querySelector("#entity_prefix").addEventListener("change", (e) => {
      this._config = { ...this._config, entity_prefix: e.target.value };
      this._fireChanged();
    });
    this.querySelector("#name").addEventListener("change", (e) => {
      this._config = { ...this._config, name: e.target.value };
      this._fireChanged();
    });
  }

  _fireChanged() {
    const event = new CustomEvent("config-changed", {
      detail: { config: this._config },
      bubbles: true,
      composed: true,
    });
    this.dispatchEvent(event);
  }
}

customElements.define("prusa-connect-card", PrusaConnectCard);
customElements.define("prusa-connect-card-editor", PrusaConnectCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "prusa-connect-card",
  name: "Prusa Connect",
  description: "A card for monitoring Prusa 3D printers via Prusa Connect",
  preview: true,
  documentationURL: "https://github.com/npolanosky/prusa_home_assistant",
});

console.info(
  `%c PRUSA-CONNECT-CARD %c v${CARD_VERSION} `,
  "color: white; background: #fa6831; font-weight: bold; padding: 2px 6px; border-radius: 4px 0 0 4px;",
  "color: #fa6831; background: #1c1c1c; font-weight: bold; padding: 2px 6px; border-radius: 0 4px 4px 0; border: 1px solid #fa6831;"
);
