"""The Appliance Live Activity integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import appliances  # noqa: F401  (import registers all appliance plugins)
from .const import (
    CONF_APPLIANCE_TYPE,
    CONF_DELAY_ENTITY,
    CONF_DRYER_START_ENTITY,
    CONF_SOURCE,
    CONF_SOURCE_DEVICE,
    DOMAIN,
    DOOR_TYPES,
    PLATFORMS,
    SOURCE_GE_HOME,
)
from .coordinator import ApplianceCoordinator
from .door import DoorCoordinator
from .services import async_setup_services, async_unload_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


def _async_backfill_ge(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """GE appliances set up before 1.5.0: find the entities added since then
    (delay sensor, dryer start button) once, without another setup."""
    if entry.data.get(CONF_SOURCE) != SOURCE_GE_HOME or CONF_DELAY_ENTITY in entry.data:
        return
    device_id = entry.data.get(CONF_SOURCE_DEVICE)
    if not device_id:
        return
    from .ge import async_discover  # noqa: PLC0415

    found = async_discover(hass, device_id)
    new = {**entry.data, CONF_DELAY_ENTITY: found.delay_entity}
    if (
        entry.data.get(CONF_APPLIANCE_TYPE) == "washer"
        and CONF_DRYER_START_ENTITY not in entry.options
        and found.dryer_start_entity
    ):
        new[CONF_DRYER_START_ENTITY] = found.dryer_start_entity
    hass.config_entries.async_update_entry(entry, data=new)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    _async_backfill_ge(hass, entry)
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
