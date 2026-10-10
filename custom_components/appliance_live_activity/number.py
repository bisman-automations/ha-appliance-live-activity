"""Probe Target number: the meat probe's target temperature (GE ovens don't
report the one set on the oven)."""
from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .device import attach_to_appliance
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if getattr(coordinator, "probe", None) is not None:
        async_add_entities([ProbeTargetNumber(coordinator, entry)])


class ProbeTargetNumber(RestoreNumber):
    """Target temperature for the probe Live Activity / alert (0 = off)."""

    _attr_has_entity_name = False
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_icon = "mdi:thermometer-probe"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_probe_target"
        self._attr_name = f"{coordinator.name} Probe Target"
        unit = coordinator.hass.config.units.temperature_unit
        self._attr_native_unit_of_measurement = unit
        self._attr_native_max_value = 300 if unit == UnitOfTemperature.FAHRENHEIT else 150
        self._attr_native_value = 0
        attach_to_appliance(self, coordinator, entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._attr_native_value = last.native_value
            await self.coordinator.probe.async_set_target(last.native_value)

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
        await self.coordinator.probe.async_set_target(value)
