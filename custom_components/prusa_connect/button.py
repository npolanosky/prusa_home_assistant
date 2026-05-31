"""Button platform for Prusa Connect — pause / resume / stop the print.

Job control is only available over the local PrusaLink API (the cloud API does
not reliably expose these commands), so these buttons are created for local
connections only.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PrusaConnectCoordinator, PrusaConnectData
from .entity import PrusaConnectEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PrusaConnectButtonDescription(ButtonEntityDescription):
    """Describes a Prusa Connect control button."""

    action: str
    available_fn: Callable[[PrusaConnectData], bool]


BUTTONS: tuple[PrusaConnectButtonDescription, ...] = (
    PrusaConnectButtonDescription(
        key="pause",
        name="Pause",
        icon="mdi:pause",
        action="pause",
        available_fn=lambda data: data.is_printing,
    ),
    PrusaConnectButtonDescription(
        key="resume",
        name="Resume",
        icon="mdi:play",
        action="resume",
        available_fn=lambda data: data.is_paused,
    ),
    PrusaConnectButtonDescription(
        key="stop",
        name="Stop",
        icon="mdi:stop",
        action="stop",
        available_fn=lambda data: data.is_printing or data.is_paused,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Prusa Connect control buttons (local connections only)."""
    coordinator: PrusaConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    if not coordinator.is_local:
        return
    async_add_entities(
        PrusaConnectButton(coordinator, desc) for desc in BUTTONS
    )


class PrusaConnectButton(PrusaConnectEntity, ButtonEntity):
    """A pause/resume/stop control button."""

    entity_description: PrusaConnectButtonDescription

    def __init__(
        self,
        coordinator: PrusaConnectCoordinator,
        description: PrusaConnectButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._printer_uuid}_{description.key}"

    @property
    def available(self) -> bool:
        return super().available and self.entity_description.available_fn(
            self.printer_data
        )

    async def async_press(self) -> None:
        await self.coordinator.async_send_command(self.entity_description.action)
