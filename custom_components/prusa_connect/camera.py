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
    """Set up Prusa Connect cameras."""
    coordinator: PrusaConnectCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[Camera] = []

    # Webcam stream, if the printer exposes one.
    if coordinator.printer_data.camera_url:
        entities.append(PrusaConnectCamera(coordinator))

    # Current-print thumbnail preview (works for both local PrusaLink via
    # file.refs.thumbnail and cloud via job_info.preview_url).
    entities.append(PrusaConnectJobPreviewCamera(coordinator))

    async_add_entities(entities)


class PrusaConnectCamera(PrusaConnectEntity, Camera):
    """Representation of a Prusa Connect webcam stream."""

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


class PrusaConnectJobPreviewCamera(PrusaConnectEntity, Camera):
    """Thumbnail preview of the currently printing G-code file."""

    _attr_name = "Current print"
    _attr_icon = "mdi:image"

    def __init__(self, coordinator: PrusaConnectCoordinator) -> None:
        PrusaConnectEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._attr_unique_id = f"{self._printer_uuid}_job_preview"
        self._last_path: str | None = None
        self._last_image: bytes | None = None

    @property
    def available(self) -> bool:
        return super().available and self.printer_data.thumbnail_ref is not None

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        ref = self.printer_data.thumbnail_ref
        if not ref:
            return None
        # The preview is static for the duration of a print — cache by ref.
        if ref == self._last_path and self._last_image is not None:
            return self._last_image
        image = await self.coordinator.async_get_thumbnail()
        if image is not None:
            self._last_path = ref
            self._last_image = image
        return image
