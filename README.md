# Prusa Connect for Home Assistant

A Home Assistant custom integration for Prusa 3D printers via **PrusaLink** (local) or **Prusa Connect** (cloud).

Includes a custom Lovelace card with a visual printer display, temperatures, print progress, and status information.

## Features

- **Dual connection modes**: Local PrusaLink (via printer IP + API key) or Prusa Connect cloud (via Bearer token)
- **UI Configuration**: Set up entirely through the Home Assistant UI — no YAML needed
- **Custom Lovelace Card**: Visual printer card showing temperatures, print progress, material, and status
- **Sensors**: Nozzle temp, bed temp, print progress, material, z-height, print speed, time remaining, and more
- **Camera**: Stream from your printer's camera (if configured)

## Installation

### HACS (Recommended)

1. Add this repository as a custom repository in HACS
2. Search for "Prusa Connect" and install
3. Restart Home Assistant
4. Go to Settings > Devices & Services > Add Integration > Prusa Connect

### Manual

1. Copy `custom_components/prusa_connect` to your `config/custom_components/` directory
2. Restart Home Assistant
3. Go to Settings > Devices & Services > Add Integration > Prusa Connect

## Setup

### Local Connection (PrusaLink)

1. Choose "Local (PrusaLink)" in the setup flow
2. Enter your printer's IP address (e.g., `192.168.1.100`)
3. Enter the API key from your printer's PrusaLink web interface (Settings page)
4. Optionally give it a name

### Cloud Connection (Prusa Connect)

1. Choose "Cloud (Prusa Connect)" in the setup flow
2. Enter your Prusa Connect API Bearer token
3. Select your printer from the list

## Custom Card

The integration includes a custom Lovelace card that auto-registers. To add it:

1. Go to your dashboard
2. Click the three-dot menu > Edit Dashboard
3. Click "+ Add Card"
4. Search for "Prusa Connect"
5. Configure the entity prefix (e.g., `sensor.prusa_connect` or `sensor.prusa_mini`)

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
| Nozzle Temperature | Current nozzle temperature |
| Bed Temperature | Current bed temperature |
| Nozzle Target Temperature | Target nozzle temperature |
| Bed Target Temperature | Target bed temperature |
| Progress | Print progress percentage |
| Material | Currently loaded filament type |
| Project Name | Current print file name |
| Z Height | Current Z axis position |
| Print Speed | Current print speed percentage |
| Time Remaining | Estimated time remaining |
| Time Printing | Elapsed print time |

## Compatibility

- Home Assistant 2024.1.0+
- Prusa Mini, Prusa MK3S+, Prusa MK4, Prusa XL (any printer with PrusaLink or Prusa Connect)
- HACS compatible

## Acknowledgments & Disclosure

This project is based on [prusa_mini_home_assistant](https://github.com/sq3tle/prusa_mini_home_assistant) by [@sq3tle](https://github.com/sq3tle), licensed under MIT. The custom Lovelace card design was inspired by the card included in [ha-bambulab](https://github.com/greghesp/ha-bambulab) by [@greghesp](https://github.com/greghesp).

This integration was developed with the assistance of LLM tools (Anthropic Claude). All code was reviewed and tested by the maintainer.

## License

MIT — see [LICENSE](LICENSE) for details.
