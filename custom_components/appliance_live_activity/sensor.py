"""Sensor entities so appliance status/progress can be used on dashboards.

Names come from translations (``has_entity_name``). Home Assistant prefixes
them with the device name, which is what keeps a linked appliance from
getting a doubled entity ID. The unique id is still
``<entry_id>_<key>`` -- the same value every previous release stored -- so
an entity ID already in the registry is left alone.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOOR_TYPES
from .device import attach_to_appliance


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the sensors for one appliance."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        ApplianceStatusSensor(coordinator, entry),
    ]
    if coordinator.appliance_type not in DOOR_TYPES:
        # Doors and fridges have no cycle: no progress, time left or history.
        entities += [
            ApplianceProgressSensor(coordinator, entry),
            ApplianceTimeRemainingSensor(coordinator, entry),
            ApplianceFinishesAtSensor(coordinator, entry),
            ApplianceCyclesWeekSensor(coordinator, entry),
            ApplianceAverageCycleSensor(coordinator, entry),
        ]
    async_add_entities(entities)


class _ApplianceSensor(CoordinatorEntity, SensorEntity):
    """A sensor named by ``translation_key``, on this integration's device.

    ``_attr_has_entity_name`` means the translated name is only the entity
    ("Time Left"), and the device name supplies the appliance. Do not set
    ``_attr_name``: a hardcoded name that already contains the appliance
    name is what Home Assistant then prefixes again.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry, key: str) -> None:
        """Bind the sensor to ``entry`` under the stable unique id for ``key``."""
        super().__init__(coordinator)
        self._attr_translation_key = key
        # Stable across the naming change. A new unique id would register a
        # second entity and leave the old one orphaned.
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        attach_to_appliance(self, coordinator, entry)


class ApplianceStatusSensor(_ApplianceSensor):
    """Current status: idle / delayed / running / paused / complete, with phase details.

    The icon follows the appliance (washer, oven, door, …), so it stays in
    code. The other sensors have one icon each, in ``icons.json``.
    """

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Status sensor for ``entry``."""
        super().__init__(coordinator, entry, "status")
        self._attr_icon = coordinator.icon

    @property
    def native_value(self):
        """The coordinator's status string."""
        return self.coordinator.data.get("status")

    @property
    def extra_state_attributes(self) -> dict:
        """Phase, cycle and whichever monitors this appliance has."""
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


class ApplianceProgressSensor(_ApplianceSensor):
    """Cycle progress percentage, for progress-bar cards."""

    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Progress sensor for ``entry``."""
        super().__init__(coordinator, entry, "progress")

    @property
    def native_value(self):
        """0–100 while a cycle is running, otherwise the coordinator's value."""
        return self.coordinator.data.get("progress")

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Off for appliance types that have no meaningful progress."""
        return self.coordinator.definition.supports_progress


class ApplianceTimeRemainingSensor(_ApplianceSensor):
    """Minutes left in the current cycle (0 when nothing is running)."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Time-left sensor for ``entry``.

        The translated name is "Time Left", not "Time Remaining", so the
        entity ID never collides with the appliance integration's own
        ``*_time_remaining`` entity.
        """
        super().__init__(coordinator, entry, "time_left")

    @property
    def native_value(self):
        """Minutes remaining, or 0 when idle."""
        return self.coordinator.data.get("time_remaining", 0)


class ApplianceFinishesAtSensor(_ApplianceSensor):
    """When the current cycle should finish (unknown when not running)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Finishes-at sensor for ``entry``."""
        super().__init__(coordinator, entry, "finishes_at")

    @property
    def native_value(self):
        """Timestamp the cycle should finish, or None."""
        return self.coordinator.data.get("finishes_at")


class ApplianceCyclesWeekSensor(_ApplianceSensor):
    """Finished cycles in the last 7 days."""

    _attr_native_unit_of_measurement = "cycles"
    _attr_state_class = "measurement"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Cycles-this-week sensor for ``entry``."""
        super().__init__(coordinator, entry, "cycles_week")

    @property
    def native_value(self):
        """Finished cycles in the last 7 days."""
        return self.coordinator.cycles_since(7)

    @property
    def extra_state_attributes(self) -> dict:
        """Today and the last 30 days, alongside the weekly state."""
        return {
            "today": self.coordinator.cycles_since(1),
            "last_30_days": self.coordinator.cycles_since(30),
        }


class ApplianceAverageCycleSensor(_ApplianceSensor):
    """Average length of the last 10 finished cycles."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Average-cycle sensor for ``entry``."""
        super().__init__(coordinator, entry, "average_cycle")

    @property
    def native_value(self):
        """Mean minutes of the recent finished cycles."""
        return self.coordinator.average_minutes()
