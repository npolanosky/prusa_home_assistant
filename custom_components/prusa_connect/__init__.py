"""The Prusa Connect integration."""
from __future__ import annotations

import logging
import pathlib

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import DOMAIN, PLATFORMS, PRUSA_CONNECT_CARDS, URL_BASE
from .coordinator import PrusaConnectCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Prusa Connect from a config entry."""
    coordinator = PrusaConnectCoordinator(hass, entry)

    # Try first refresh but don't fail setup if the printer is unreachable.
    # The coordinator will keep retrying on its update interval.
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "Prusa Connect: initial connection failed (%s). "
            "The integration will keep retrying. "
            "You can update the configuration in the integration options.",
            err,
        )

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await _async_register_frontend(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the integration."""
    _LOGGER.warning("Prusa Connect: config updated, reloading integration")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve and load the bundled custom Lovelace card.

    Uses ``frontend.add_extra_js_url`` so the card module is imported on every
    dashboard page (storage *and* YAML mode). This is what defines the custom
    element and makes the card appear in the graphical card picker. The old
    ``lovelace_resources`` approach silently no-op'd because that hass.data key
    does not exist in current Home Assistant.
    """
    if hass.data.get(f"{DOMAIN}_frontend_registered"):
        return
    hass.data[f"{DOMAIN}_frontend_registered"] = True

    frontend_dir = pathlib.Path(__file__).parent / "frontend"

    # 1. Serve the bundled JS over HTTP (version-busted URL → safe to cache).
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, str(frontend_dir), True)]
        )
    except RuntimeError:
        _LOGGER.debug("Static path %s already registered", URL_BASE)

    # 2. Force the frontend to import() the module on every dashboard page.
    for card in PRUSA_CONNECT_CARDS:
        url = f"{URL_BASE}/{card['filename']}?v={card['version']}"
        add_extra_js_url(hass, url)
        _LOGGER.debug("Prusa Connect: registered frontend module %s", url)
