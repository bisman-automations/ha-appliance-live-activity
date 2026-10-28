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
    CONFIG_MINOR_VERSION,
    DOMAIN,
    DOOR_TYPES,
    PLATFORMS,
    SOURCE_GE_HOME,
)
from .coordinator import ApplianceConfigEntry, ApplianceCoordinator
from .door import DoorCoordinator
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once, for the lifetime of Home Assistant.

    Doing this when the first config entry loads (and removing them when the
    last one unloads) races two entries setting up together and drops the
    service while an entry is still loaded. The service handler no-ops when
    the requested appliance is not set up.
    """
    await async_setup_services(hass)
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
        new = {
            **stored,
            CONF_SUPPLY_ENTITIES: [e for e in supplies if e not in filters] or None,
        }
        if not stored.get(CONF_FILTER_ENTITY):
            new[CONF_FILTER_ENTITY] = filters[0]
        hass.config_entries.async_update_entry(entry, **{update: new})


# Pickers that 1.7.0 / 1.8.0 could wipe when saving Configure (the grouped
# sections weren't submitted by the frontend). Where setup had found a value,
# drop the wiped None so it applies again.
_WIPEABLE = (
    "leak_entities",
    "dryer_entity",
    "dryer_start_entity",
    "supply_entities",
    "filter_entity",
    "vent_entity",
)


def _async_restore_wiped(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if entry.data.get("options_restored"):
        return
    options = dict(entry.options)
    for key in _WIPEABLE:
        if key in options and options[key] is None and entry.data.get(key):
            options.pop(key)
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "options_restored": 1}, options=options
    )


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Upgrade stored config once per minor version.

    The GE backfill, the filter-field move and the wiped-options restore used
    to run on every start. They are idempotent, but they also rewrote the
    config entry during setup. Home Assistant's minor version runs each step
    a single time, before the entry is set up, and a later repair is a new
    step rather than more work on the startup path.

    ``GE_DISCOVERY_VERSION`` still records how far discovery got. Bumping it
    is not enough on its own: add a minor step below that calls
    ``_async_backfill_ge`` again.
    """
    if entry.version > 1:
        return False

    if entry.minor_version < 2:
        _async_backfill_ge(hass, entry)
        _async_move_filter_out_of_supplies(hass, entry)
        _async_restore_wiped(hass, entry)
        hass.config_entries.async_update_entry(entry, minor_version=2)

    if entry.minor_version != CONFIG_MINOR_VERSION:
        # A step above should have landed on the current minor. If it did
        # not, refuse to start rather than silently skip a migration.
        return False
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ApplianceConfigEntry) -> bool:
    """Create the coordinator, link the device, and forward platforms.

    The coordinator is stored on ``entry.runtime_data``. If forwarding a
    platform raises, the platforms that did load are unloaded and the
    coordinator's listeners and timers are cancelled before the error
    propagates. Home Assistant does not call ``async_unload_entry`` when
    setup raises, so leaving them running would leak a timer.
    """
    cfg = {**entry.data, **entry.options}
    coordinator_cls = (
        DoorCoordinator
        if cfg.get(CONF_APPLIANCE_TYPE) in DOOR_TYPES
        else ApplianceCoordinator
    )
    coordinator = coordinator_cls(hass, entry)
    # Assigned before async_setup so a partner appliance can see this one
    # while startup listeners run. Cleared again if setup does not finish;
    # Home Assistant only drops runtime_data after a successful unload.
    entry.runtime_data = coordinator
    try:
        await coordinator.async_setup()
        from .device import async_link_device  # noqa: PLC0415

        async_link_device(hass, coordinator, entry)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        await coordinator.async_unload()
        object.__delattr__(entry, "runtime_data")
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ApplianceConfigEntry) -> bool:
    """Unload platforms and cancel the coordinator's listeners and timers."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ApplianceConfigEntry) -> None:
    """Appliance deleted: remove its Repairs issues."""
    from .health import async_remove_issues  # noqa: PLC0415

    async_remove_issues(hass, entry)
