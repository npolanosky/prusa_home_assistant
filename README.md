# Prusa Connect for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/npolanosky/prusa_home_assistant)](https://github.com/npolanosky/prusa_home_assistant/releases)
[![License: MIT](https://img.shields.io/github/license/npolanosky/prusa_home_assistant)](LICENSE)

A Home Assistant custom integration for Prusa 3D printers via **PrusaLink** (local network) or **Prusa Connect** (cloud API).

Includes a custom Lovelace card with an SVG printer visualization, live temperatures, print progress, and status.

![Prusa Connect Card](https://img.shields.io/badge/Custom_Card-Included-brightgreen)

## Features

- 🔌 **Dual connection modes**
  - **Local (PrusaLink)** — connect directly to your printer's IP with its API key
  - **Cloud (Prusa Connect)** — connect via connect.prusa3d.com with your per-printer API key and printer UUID
- 🖥️ **UI Configuration** — set up entirely through the Home Assistant UI, no YAML needed
- 🎨 **Custom Lovelace Card** — visual SVG printer card showing temperatures, print progress, material, speed, z-height, and status
- 📊 **12 Sensors** — nozzle/bed temps & targets, print progress, material, project name, z-height, print speed, time remaining, time printing
- 📷 **Camera** — stream from your printer's camera (if configured)
- 🔄 **Options Flow** — edit API key, host, UUID, printer name, and polling interval after setup without removing the integration
- 💾 **Save on failure** — integration saves even if the initial connection fails, so you can troubleshoot via the options menu

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three-dot menu → **Custom repositories**
3. Add `https://github.com/npolanosky/prusa_home_assistant` as an **Integration**
4. Search for **"Prusa Connect"** and install
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → + Add Integration → Prusa Connect**

### Manual

1. Copy the `custom_components/prusa_connect` folder to your `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → + Add Integration → Prusa Connect**

## Setup

### Local Connection (PrusaLink)

1. Choose **"Local (PrusaLink)"** in the setup flow
2. Enter your printer's IP address (e.g., `192.168.1.100`)
3. Enter the API key from your printer's web interface → Settings → API Key
4. Optionally give it a friendly name

### Cloud Connection (Prusa Connect)

1. Choose **"Cloud (Prusa Connect)"** in the setup flow
2. Enter your **Prusa Connect API Key** — this is a per-printer key, not an account-wide token
3. Enter your **Printer UUID** — find it in the browser URL when viewing your printer on connect.prusa3d.com (e.g., `connect.prusa3d.com/printer/`**`abc123-def456`**`/settings`)
4. Optionally give it a friendly name (auto-detected if left blank)

> **Finding your API Key & UUID:**
> Go to [connect.prusa3d.com](https://connect.prusa3d.com) → select your printer → **Settings** tab. The API key is listed under the API keys section. The printer UUID is visible in the URL bar.

### Troubleshooting Connection Issues

- If the connection fails during setup, the integration **saves anyway** on the second submit — you can then fix settings via the integration's **Configure** (options) menu
- Error details are shown **inline** in the setup form
- Connection warnings are logged at the WARNING level, visible in the default Home Assistant logs (no debug mode needed)

## Custom Card

The integration includes a custom Lovelace card that auto-registers. To add it:

1. Go to your dashboard → three-dot menu → **Edit Dashboard**
2. Click **+ Add Card**
3. Search for **"Prusa Connect"**
4. Configure the entity prefix (e.g., `sensor.prusa_connect` or `sensor.prusa_mini`)

If the card doesn't appear automatically, add it as a Lovelace resource manually:
- URL: `/prusa_connect/prusa-connect-card.js`
- Type: JavaScript Module

### Card Configuration

```yaml
type: custom:prusa-connect-card
entity_prefix: sensor.prusa_connect
name: Prusa Mini
```

## Sensors

| Sensor | Description |
|--------|-------------|
| Status | Printer state (Idle, Printing, Paused, etc.) |
| Nozzle Temperature | Current nozzle temperature (°C) |
| Bed Temperature | Current bed temperature (°C) |
| Nozzle Target | Target nozzle temperature (°C) |
| Bed Target | Target bed temperature (°C) |
| Progress | Print progress (%) |
| Material | Currently loaded filament type |
| Project Name | Current print file name |
| Z Height | Current Z axis position (mm) |
| Print Speed | Current print speed (%) |
| Time Remaining | Estimated time remaining |
| Time Printing | Elapsed print time |

## Compatibility

- **Home Assistant** 2024.1.0+
- **Printers**: Prusa Mini, MK3S+, MK4, XL — any printer with PrusaLink or Prusa Connect support
- **HACS** compatible

## Acknowledgments & Disclosure

This project is a fork of [prusa_mini_home_assistant](https://github.com/sq3tle/prusa_mini_home_assistant) by [@sq3tle](https://github.com/sq3tle), licensed under MIT. The custom Lovelace card design was inspired by [ha-bambulab](https://github.com/greghesp/ha-bambulab) by [@greghesp](https://github.com/greghesp).

API endpoint patterns and authentication methods were documented by referencing [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) (AGPL-3.0) and [OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer) (AGPL-3.0). No source code was copied from either project; only publicly available API interface details (URLs, header names, endpoint paths) were used.

**This integration was developed with the assistance of LLM tools (Anthropic Claude).** All code was reviewed and tested by the maintainer.

## License

MIT — see [LICENSE](LICENSE) for details.
