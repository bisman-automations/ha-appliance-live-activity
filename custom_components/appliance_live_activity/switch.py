"""Power switch for washers, dryers and dishwashers.

Home Assistant Matter Hub bridges these appliances to Matter (Dishwasher,
Laundry Washer, Laundry Dryer) by mapping a power switch, and reads the cycle
from an enum sensor on the same device: our Status sensor. The switch is on
while a cycle is running, paused or waiting to start. GE appliances can't be
started or stopped from Home Assistant, so turning it on or off is refused.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MATTER_APPLIANCE_TYPES,
    STATUS_DELAYED,
    STATUS_PAUSED,
    STATUS_RUNNING,
)
from .device import attach_to_appliance

ON_STATUSES = (STATUS_RUNNING, STATUS_PAUSED, STATUS_DELAYED)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the Power switch for a washer, dryer or dishwasher."""
    coordinator = entry.runtime_data
    if coordinator.appliance_type in MATTER_APPLIANCE_TYPES:
        async_add_entities([AppliancePowerSwitch(coordinator, entry)])


class AppliancePowerSwitch(CoordinatorEntity, SwitchEntity):
    """On while the appliance is in a cycle."""

    _attr_has_entity_name = True
    _attr_translation_key = "power"
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Power switch for ``entry``."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_power"
        attach_to_appliance(self, coordinator, entry, Platform.SWITCH, "power")

    @property
    def is_on(self) -> bool:
        """In a cycle: running, paused, or waiting for a delayed start."""
        return self.coordinator.data.get("status") in ON_STATUSES

    async def async_turn_on(self, **kwargs: Any) -> None:
        """The appliance can't be started from Home Assistant."""
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="no_remote_control",
            translation_placeholders={"name": self.coordinator.name},
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """The appliance can't be stopped from Home Assistant."""
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="no_remote_control",
            translation_placeholders={"name": self.coordinator.name},
        )
