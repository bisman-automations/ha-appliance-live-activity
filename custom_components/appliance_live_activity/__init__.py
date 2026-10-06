"""The Appliance Live Activity integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import appliances  # noqa: F401  (import registers all appliance plugins)
from .const import DOMAIN, PLATFORMS
from .const import CONF_APPLIANCE_TYPE, DOOR_TYPES
from .coordinator import ApplianceCoordinator
from .door import DoorCoordinator
from .services import async_setup_services, async_unload_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    cfg = {**entry.data, **entry.options}
    coordinator_cls = (
        DoorCoordinator
        if cfg.get(CONF_APPLIANCE_TYPE) in DOOR_TYPES
        else ApplianceCoordinator
    )
    coordinator = coordinator_cls(hass, entry)
    await coordinator.async_setup()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass)

    return True


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: ApplianceCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_unload()
        if not hass.data[DOMAIN]:
            await async_unload_services(hass)
    return unloaded
