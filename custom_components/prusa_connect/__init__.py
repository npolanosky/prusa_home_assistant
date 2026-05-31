"""The Prusa Connect integration."""
from __future__ import annotations

import logging
import pathlib

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS, PRUSA_CONNECT_CARDS, URL_BASE
from .coordinator import PrusaConnectCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Prusa Connect from a config entry."""
    coordinator = PrusaConnectCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _async_register_frontend(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register the custom card frontend resources."""
    if hass.data.get(f"{DOMAIN}_frontend_registered"):
        return
    hass.data[f"{DOMAIN}_frontend_registered"] = True

    frontend_dir = pathlib.Path(__file__).parent / "frontend"

    try:
        hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(frontend_dir), False)]
        )
    except Exception:
        _LOGGER.debug("Static path %s already registered", URL_BASE)

    try:
        resources = hass.data.get("lovelace_resources")
        if resources is not None:
            for card in PRUSA_CONNECT_CARDS:
                url = f"{URL_BASE}/{card['filename']}?v={card['version']}"
                existing = [
                    r
                    for r in resources.async_items()
                    if card["filename"] in r.get("url", "")
                ]
                if not existing:
                    await resources.async_create_item(
                        {"res_type": "module", "url": url}
                    )
                else:
                    for r in existing:
                        if r.get("url") != url:
                            await resources.async_update_item(
                                r["id"], {"res_type": "module", "url": url}
                            )
    except Exception:
        _LOGGER.info(
            "Auto-registration of Prusa Connect card resource failed. "
            "You can add it manually as a Lovelace resource: %s/%s",
            URL_BASE,
            PRUSA_CONNECT_CARDS[0]["filename"],
        )
