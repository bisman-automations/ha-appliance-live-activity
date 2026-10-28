"""Buttons for manually updating an appliance's Live Activity.

The name is the ``update_live_activity`` translation. The unique id stays
``<entry_id>_update_live_activity``.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .device import attach_to_appliance


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the Update Live Activity button for one appliance."""
    async_add_entities([UpdateLiveActivityButton(entry.runtime_data, entry)])


class UpdateLiveActivityButton(ButtonEntity):
    """Re-send the current Live Activity state when pressed."""

    _attr_has_entity_name = True
    _attr_translation_key = "update_live_activity"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Refresh button for ``entry``."""
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_update_live_activity"
        attach_to_appliance(self, coordinator, entry)

    async def async_press(self) -> None:
        """Re-send the Live Activity even if nothing has changed."""
        await self.coordinator.async_evaluate(send=True, force=True)
