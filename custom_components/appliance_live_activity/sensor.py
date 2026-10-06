"""Sensor entities so appliance status/progress can be used on dashboards."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTime
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, DOOR_TYPES


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        ApplianceStatusSensor(coordinator, entry),
        ApplianceProgressSensor(coordinator, entry),
    ]
    if coordinator.appliance_type not in DOOR_TYPES:
        entities += [
            ApplianceTimeRemainingSensor(coordinator, entry),
            ApplianceFinishesAtSensor(coordinator, entry),
        ]
    async_add_entities(entities)


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
    """Current status: idle / delayed / running / paused / complete, with phase details."""

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
            **(
                {"open_minutes": self.coordinator.data["open_minutes"]}
                if "open_minutes" in self.coordinator.data
                else {}
            ),
            **(
                {
                    "cooktop_on": self.coordinator.cooktop.is_on,
                    "cooktop_on_minutes": round(self.coordinator.cooktop.minutes_on, 1),
                }
                if getattr(self.coordinator, "cooktop", None) is not None
                else {}
            ),
            **(
                {"starts_at": self.coordinator.data["starts_at"]}
                if self.coordinator.data.get("starts_at")
                else {}
            ),
            **(
                {"snoozed_until": self.coordinator.data["snoozed_until"]}
                if self.coordinator.data.get("snoozed_until")
                else {}
            ),
            **(
                {"kitchen_timer_minutes": round(self.coordinator.timer.remaining)}
                if getattr(self.coordinator, "timer", None) is not None
                else {}
            ),
            **(
                {
                    "probe_temperature": self.coordinator.probe.temperature or None,
                    "probe_target": self.coordinator.probe.target or None,
                }
                if getattr(self.coordinator, "probe", None) is not None
                else {}
            ),
            **(
                {"vent_blocked": self.coordinator.vent.blocked}
                if getattr(self.coordinator, "vent", None) is not None
                else {}
            ),
            **(
                {"leak_detected": bool(self.coordinator.leak.wet)}
                if getattr(self.coordinator, "leak", None) is not None
                else {}
            ),
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


class ApplianceTimeRemainingSensor(_ApplianceBaseSensor):
    """Minutes left in the current cycle (0 when nothing is running)."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_time_left"
        self._attr_icon = "mdi:timer-sand"

    @property
    def name(self) -> str:
        # "Time Left" (not "Time Remaining") so it never collides with the
        # appliance integration's own *_time_remaining entity
        return f"{self.coordinator.name} Time Left"

    @property
    def native_value(self):
        return self.coordinator.data.get("time_remaining", 0)


class ApplianceFinishesAtSensor(_ApplianceBaseSensor):
    """When the current cycle should finish (unknown when not running)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_finishes_at"
        self._attr_icon = "mdi:clock-end"

    @property
    def name(self) -> str:
        return f"{self.coordinator.name} Finishes At"

    @property
    def native_value(self):
        return self.coordinator.data.get("finishes_at")
