"""Buttons for manually updating an appliance's Live Activity."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .device import attach_to_appliance


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([UpdateLiveActivityButton(coordinator, entry)])


class UpdateLiveActivityButton(ButtonEntity):
    """Re-send the current Live Activity state when pressed."""

    _attr_has_entity_name = False
    _attr_icon = "mdi:send"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_update_live_activity"
        self._attr_name = f"{coordinator.name} Update Live Activity"
        attach_to_appliance(self, coordinator, entry)

    async def async_press(self) -> None:
        await self.coordinator.async_evaluate(send=True, force=True)
