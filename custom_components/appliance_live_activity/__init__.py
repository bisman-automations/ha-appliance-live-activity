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
    CONF_FILTER_ENTITY,
    CONF_GE_DISCOVERY,
    CONF_OVEN_CAVITY,
    CONF_SOURCE,
    CONF_SOURCE_DEVICE,
    CONF_SUPPLY_ENTITIES,
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


# Bump when GE discovery learns new entities, so existing entries pick them up
GE_DISCOVERY_VERSION = 5


def _async_backfill_ge(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """GE appliances set up with an older version: add the entities discovery
    has learned since (delay sensor, dryer start button, kitchen timer,
    probe...) once, without another setup. Nothing the user set or cleared
    in Configure is touched."""
    if entry.data.get(CONF_SOURCE) != SOURCE_GE_HOME:
        return
    if entry.data.get(CONF_GE_DISCOVERY, 0) >= GE_DISCOVERY_VERSION:
        return
    device_id = entry.data.get(CONF_SOURCE_DEVICE)
    if not device_id:
        return
    from .ge import async_discover  # noqa: PLC0415

    found = async_discover(hass, device_id, entry.data.get(CONF_OVEN_CAVITY))
    new = dict(entry.data)
    for key, value in found.as_config().items():
        if key not in entry.data and key not in entry.options:
            new[key] = value
    new.setdefault(CONF_DELAY_ENTITY, None)
    new[CONF_GE_DISCOVERY] = GE_DISCOVERY_VERSION
    hass.config_entries.async_update_entry(entry, data=new)


def _async_move_filter_out_of_supplies(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A dishwasher 'clean filter' reminder picked as a refill supply belongs in
    the Filter field (1.6.0 put both in one picker)."""
    for source, update in (("data", "data"), ("options", "options")):
        stored = getattr(entry, source)
        supplies = list(stored.get(CONF_SUPPLY_ENTITIES) or [])
        filters = [e for e in supplies if e.endswith("_clean_filter")]
        if not filters:
            continue
        new = {**stored, CONF_SUPPLY_ENTITIES: [e for e in supplies if e not in filters] or None}
        if not stored.get(CONF_FILTER_ENTITY):
            new[CONF_FILTER_ENTITY] = filters[0]
        hass.config_entries.async_update_entry(entry, **{update: new})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    _async_backfill_ge(hass, entry)
    _async_move_filter_out_of_supplies(hass, entry)
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


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Appliance deleted: remove its Repairs issues."""
    from .health import async_remove_issues  # noqa: PLC0415

    async_remove_issues(hass, entry)
