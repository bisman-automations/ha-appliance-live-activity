"""Cycle events for automations: one event entity per appliance.

Washers, dryers, dishwashers, ovens: started, scheduled (delayed start),
finished, cancelled. Fridges and doors: door_left_open (when critical alerts
start), door_closed. Event attributes carry details such as the cycle name
and how long it ran.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CYCLE_EVENTS, DOMAIN, DOOR_EVENTS, DOOR_TYPES


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([ApplianceEvent(hass.data[DOMAIN][entry.entry_id], entry)])


class ApplianceEvent(EventEntity):
    """Fires when a cycle starts / finishes or a door is left open."""

    _attr_has_entity_name = False

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        door = coordinator.appliance_type in DOOR_TYPES
        self._attr_unique_id = f"{entry.entry_id}_event"
        self._attr_name = f"{coordinator.name} {'Door' if door else 'Cycle'}"
        self._attr_event_types = list(DOOR_EVENTS if door else CYCLE_EVENTS)
        self._attr_icon = "mdi:door" if door else "mdi:bell-ring-outline"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.add_event_listener(self._handle))

    @callback
    def _handle(self, event_type: str, attributes: dict[str, Any]) -> None:
        if event_type in self._attr_event_types:
            self._trigger_event(event_type, attributes)
            self.async_write_ha_state()
