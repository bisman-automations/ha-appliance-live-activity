"""Cycle events for automations: one event entity per appliance.

Washers, dryers, dishwashers, ovens: started, scheduled (delayed start),
finished, cancelled. Fridges and doors: door_left_open (when critical alerts
start), door_closed. Event attributes carry details such as the cycle name
and how long it ran.

The translated name is "Cycle" or "Door". The unique id stays
``<entry_id>_event`` so an existing event entity keeps its entity ID.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CYCLE_EVENTS, DOOR_EVENTS, DOOR_TYPES
from .device import attach_to_appliance


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the cycle or door event entity for one appliance."""
    async_add_entities([ApplianceEvent(entry.runtime_data, entry)])


class ApplianceEvent(EventEntity):
    """Fires when a cycle starts / finishes or a door is left open."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Cycle event, or door event for refrigerators and plain doors."""
        self.coordinator = coordinator
        door = coordinator.appliance_type in DOOR_TYPES
        # Unique id is ``_event`` for both. The translation key only chooses
        # the name ("Cycle" vs "Door") and the icon.
        self._attr_unique_id = f"{entry.entry_id}_event"
        self._attr_translation_key = "door" if door else "cycle"
        self._attr_event_types = list(DOOR_EVENTS if door else CYCLE_EVENTS)
        attach_to_appliance(self, coordinator, entry)

    async def async_added_to_hass(self) -> None:
        """Subscribe to the coordinator's cycle/door events."""
        self.async_on_remove(self.coordinator.add_event_listener(self._handle))

    @callback
    def _handle(self, event_type: str, attributes: dict[str, Any]) -> None:
        """Fire ``event_type`` when it belongs to this entity."""
        if event_type in self._attr_event_types:
            self._trigger_event(event_type, attributes)
            self.async_write_ha_state()
