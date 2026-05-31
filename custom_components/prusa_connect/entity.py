"""Base entity for Prusa Connect."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_PRINTER_NAME, CONF_PRINTER_TYPE, CONF_PRINTER_UUID, DOMAIN, MANUFACTURER
from .coordinator import PrusaConnectCoordinator, PrusaConnectData


class PrusaConnectEntity(CoordinatorEntity[PrusaConnectCoordinator]):
    """Base class for Prusa Connect entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PrusaConnectCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._printer_uuid = entry.data[CONF_PRINTER_UUID]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._printer_uuid)},
            name=entry.data.get(CONF_PRINTER_NAME, "Prusa Printer"),
            manufacturer=MANUFACTURER,
            model=entry.data.get(CONF_PRINTER_TYPE, ""),
            sw_version=coordinator.printer_data.firmware_version or None,
        )

    @property
    def printer_data(self) -> PrusaConnectData:
        return self.coordinator.printer_data
