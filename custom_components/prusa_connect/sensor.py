"""Sensor platform for Prusa Connect."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PrusaConnectCoordinator, PrusaConnectData
from .entity import PrusaConnectEntity


@dataclass(frozen=True, kw_only=True)
class PrusaConnectSensorDescription(SensorEntityDescription):
    """Describes a Prusa Connect sensor."""

    value_fn: Callable[[PrusaConnectData], Any]
    # By default a sensor is available whenever the coordinator's last update
    # succeeded; it shows "unknown" (not "unavailable") when its value is None.
    available_fn: Callable[[PrusaConnectData], bool] = lambda _data: True
    extra_attrs_fn: Callable[[PrusaConnectData], dict[str, Any]] | None = None


PRINTER_SENSORS: tuple[PrusaConnectSensorDescription, ...] = (
    PrusaConnectSensorDescription(
        key="status",
        translation_key="status",
        icon="mdi:printer-3d",
        value_fn=lambda data: data.state.title() if data.state else None,
    ),
    PrusaConnectSensorDescription(
        key="nozzle_temperature",
        translation_key="nozzle_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        icon="mdi:printer-3d-nozzle-heat-outline",
        value_fn=lambda data: data.nozzle_temp,
    ),
    PrusaConnectSensorDescription(
        key="nozzle_target_temperature",
        translation_key="nozzle_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        icon="mdi:printer-3d-nozzle-heat",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.nozzle_target_temp,
    ),
    PrusaConnectSensorDescription(
        key="bed_temperature",
        translation_key="bed_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        icon="mdi:radiator",
        value_fn=lambda data: data.bed_temp,
    ),
    PrusaConnectSensorDescription(
        key="bed_target_temperature",
        translation_key="bed_target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        icon="mdi:radiator",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.bed_target_temp,
    ),
    PrusaConnectSensorDescription(
        key="progress",
        translation_key="progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        icon="mdi:progress-check",
        value_fn=lambda data: data.progress,
    ),
    PrusaConnectSensorDescription(
        key="project_name",
        translation_key="project_name",
        icon="mdi:file-cad",
        value_fn=lambda data: data.project_name,
    ),
    PrusaConnectSensorDescription(
        key="material",
        translation_key="material",
        icon="mdi:printer-3d-nozzle-alert",
        value_fn=lambda data: data.material,
    ),
    PrusaConnectSensorDescription(
        key="z_height",
        translation_key="z_height",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:axis-z-arrow",
        value_fn=lambda data: data.z_height,
    ),
    PrusaConnectSensorDescription(
        key="print_speed",
        translation_key="print_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        value_fn=lambda data: data.print_speed,
    ),
    PrusaConnectSensorDescription(
        key="flow",
        translation_key="flow",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.flow_factor,
    ),
    PrusaConnectSensorDescription(
        key="fan_print",
        translation_key="fan_print",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.fan_print,
    ),
    PrusaConnectSensorDescription(
        key="fan_hotend",
        translation_key="fan_hotend",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fan",
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.fan_hotend,
    ),
    PrusaConnectSensorDescription(
        key="time_remaining",
        translation_key="time_remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-sand",
        value_fn=lambda data: data.time_remaining,
    ),
    PrusaConnectSensorDescription(
        key="time_printing",
        translation_key="time_printing",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer",
        value_fn=lambda data: data.time_printing,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Prusa Connect sensors."""
    coordinator: PrusaConnectCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PrusaConnectSensor(coordinator, description)
        for description in PRINTER_SENSORS
    )


class PrusaConnectSensor(PrusaConnectEntity, SensorEntity):
    """Representation of a Prusa Connect sensor."""

    entity_description: PrusaConnectSensorDescription

    def __init__(
        self,
        coordinator: PrusaConnectCoordinator,
        description: PrusaConnectSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._printer_uuid}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.printer_data)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.entity_description.available_fn(self.printer_data)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.extra_attrs_fn:
            return self.entity_description.extra_attrs_fn(self.printer_data)
        return None
