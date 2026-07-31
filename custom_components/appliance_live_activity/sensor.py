"""Sensor entities so appliance status/progress can be used on dashboards."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            ApplianceStatusSensor(coordinator, entry),
            ApplianceProgressSensor(coordinator, entry),
        ]
    )


class _ApplianceBaseSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=coordinator.name,
            manufacturer="Appliance Live Activity",
            model=coordinator.definition.display_name,
        )


class ApplianceStatusSensor(_ApplianceBaseSensor):
    """Current status: idle / running / paused / complete, with phase details."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_icon = coordinator.icon

    @property
    def name(self) -> str:
        return f"{self.coordinator.name} Status"

    @property
    def native_value(self):
        return self.coordinator.data.get("status")

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "phase": self.coordinator.data.get("phase"),
            "cycle": self.coordinator.data.get("cycle"),
            "remaining_minutes": self.coordinator.data.get("remaining"),
        }


class ApplianceProgressSensor(_ApplianceBaseSensor):
    """Cycle progress percentage, for progress-bar cards."""

    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_progress"
        self._attr_icon = "mdi:progress-clock"

    @property
    def name(self) -> str:
        return f"{self.coordinator.name} Progress"

    @property
    def native_value(self):
        return self.coordinator.data.get("progress")

    @property
    def entity_registry_enabled_default(self) -> bool:
        return self.coordinator.definition.supports_progress
