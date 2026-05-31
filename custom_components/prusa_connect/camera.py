"""Camera platform for Prusa Connect."""
from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PrusaConnectCoordinator
from .entity import PrusaConnectEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Prusa Connect camera."""
    coordinator: PrusaConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.printer_data.camera_url:
        async_add_entities([PrusaConnectCamera(coordinator)])


class PrusaConnectCamera(PrusaConnectEntity, Camera):
    """Representation of a Prusa Connect camera."""

    _attr_translation_key = "printer_camera"

    def __init__(self, coordinator: PrusaConnectCoordinator) -> None:
        PrusaConnectEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._attr_unique_id = f"{self._printer_uuid}_camera"

    @property
    def is_streaming(self) -> bool:
        return self.printer_data.camera_url is not None

    async def stream_source(self) -> str | None:
        return self.printer_data.camera_url
