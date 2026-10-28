"""The integration's device for each appliance, linked to the appliance's own.

Every appliance gets a device of this integration ("Kitchen Oven Live
Activity") holding its sensors, event and Probe Target. When the appliance
also has a device of its own -- the GE device picked at setup, or for other
brands the device the state sensor belongs to (an LG washer, a door's
contact sensor) -- our device repeats that device's identifiers and
connections. Home Assistant 2026.8 gives every device a single owning
config entry (``config_entry_id``) and lists devices that share an
identifier or connection under **Linked devices** ("These devices share
hardware with this device and are managed by other integrations"), the same
way UniFi Network's client device shows up on a Rain Bird controller. So
each page links to the other.

The minimum supported release is 2026.8, so there is no fallback that
co-owns the appliance device (``config_entries`` / ``remove_config_entry_id``)
or that looks a device up with ``async_get_device``. Identifiers are shared
on purpose and are no longer unique across config entries; that lookup is
ambiguous and Home Assistant 2026.10 reports it (it raises when the caller
cannot be tied to an integration, and it is removed in 2027.8).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.util import slugify

from .const import DOMAIN

# English names used only to suggest an entity id. The name Home Assistant
# shows still comes from the translation of the same key (strings.json).
# These strings have to match those translations: tests/test_v1120.py checks.
# They are fixed here because the id is chosen in ``__init__``, before
# translations are available on the entity.
SUGGESTED_ENTITY_NAMES: dict[tuple[str, str], str] = {
    ("sensor", "status"): "Status",
    ("sensor", "progress"): "Progress",
    ("sensor", "time_left"): "Time Left",
    ("sensor", "finishes_at"): "Finishes At",
    ("sensor", "cycles_week"): "Cycles This Week",
    ("sensor", "average_cycle"): "Average Cycle",
    ("number", "probe_target"): "Probe Target",
    ("event", "cycle"): "Cycle",
    ("event", "door"): "Door",
    ("button", "update_live_activity"): "Update Live Activity",
}


def appliance_device_id(hass: HomeAssistant, coordinator) -> str | None:
    """The appliance's own device: the GE device chosen at setup, else the
    device of the state sensor (never this integration's own device)."""
    dev_reg = dr.async_get(hass)
    if coordinator.source_device:
        device = dev_reg.async_get(coordinator.source_device)
        if device is not None and not _is_ours(device):
            return device.id
    if not coordinator.state_entity:
        return None
    entry = er.async_get(hass).async_get(coordinator.state_entity)
    if entry is None or entry.device_id is None:
        return None
    device = dev_reg.async_get(entry.device_id)
    if device is None or _is_ours(device):
        return None
    return device.id


def _is_ours(device) -> bool:
    return any(i[0] == DOMAIN for i in device.identifiers)


def own_device_info(coordinator, entry: ConfigEntry) -> DeviceInfo:
    """Our device, sharing the appliance device's hardware keys when linked."""
    info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=coordinator.name,
        manufacturer="Appliance Live Activity",
        model=coordinator.definition.display_name,
        entry_type=DeviceEntryType.SERVICE,
    )
    target = appliance_device_id(coordinator.hass, coordinator)
    if target is None:
        return info
    appliance = dr.async_get(coordinator.hass).async_get(target)
    if appliance is None:
        return info
    # Distinct from the appliance's own device in the Linked devices list.
    info["name"] = f"{coordinator.name} Live Activity"
    # Share the appliance's hardware keys, but never our own domain: that
    # identifier already names this device, and copying it back would make
    # the two devices indistinguishable.
    info["identifiers"] = {(DOMAIN, entry.entry_id)} | {
        identifier for identifier in appliance.identifiers if identifier[0] != DOMAIN
    }
    if appliance.connections:
        info["connections"] = set(appliance.connections)
    return info


def own_device(hass: HomeAssistant, entry: ConfigEntry) -> dr.DeviceEntry | None:
    """This integration's device for the appliance, if it has been created.

    Looked up by our own identifier *and* our config entry.
    ``async_get_device`` searches by identifier alone. Once this device
    repeats the appliance's identifiers, that search matches both devices.
    Home Assistant 2026.10 reports the call and, when it cannot see which
    integration made it, raises ``RuntimeError``. ``async_get_device_by_identifier``
    takes the owning entry, so the match is the device this entry created.
    """
    return dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )


def devices_sharing_identifier(
    hass: HomeAssistant, identifier: tuple[str, str]
) -> list[dr.DeviceEntry]:
    """Every device that carries ``identifier``, across config entries.

    Used where a single identifier is intentionally shared (our device and
    the appliance's). ``async_get_devices`` returns all of them;
    ``async_get_device`` would have to guess.
    """
    return dr.async_get(hass).async_get_devices(identifiers={identifier})


def attach_to_appliance(
    entity: Entity,
    coordinator,
    entry: ConfigEntry,
    platform: str,
    translation_key: str,
) -> None:
    """Put an entity on this integration's device and suggest its entity id.

    The displayed name is the translation (``has_entity_name``): Home
    Assistant shows "<device> Status". A linked device is named
    "<appliance> Live Activity", and with no suggestion that device name
    becomes the entity id
    (``sensor.kitchen_dishwasher_live_activity_status``) or, when the
    entity's own name also contains the appliance name, the doubled
    ``sensor.kitchen_dishwasher_live_activity_kitchen_dishwasher_status``.

    Setting ``entity_id`` before the entity is added is Home Assistant's
    suggested object id. A suggestion is not prefixed with the device name,
    so a new entity is ``sensor.kitchen_dishwasher_status`` -- the appliance
    name plus the entity's own name ("Status", "Time Left", …).

    The suggestion is used only when the unique id is not already in the
    registry. An entity id that is already stored, including one the user
    renamed and including a doubled id from an earlier install, is kept.
    The unique id itself does not change.
    """
    entity._attr_device_info = own_device_info(coordinator, entry)
    own_name = SUGGESTED_ENTITY_NAMES[(platform, translation_key)]
    entity.entity_id = f"{platform}.{slugify(f'{coordinator.name} {own_name}')}"


@callback
def async_link_device(hass: HomeAssistant, coordinator, entry: ConfigEntry) -> None:
    """Before the entities are added: create our device for the appliance,
    move our entities onto it (1.9.4 put them on the appliance's device) and
    remove any other device this entry owns."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    target = appliance_device_id(hass, coordinator)

    ours = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, **own_device_info(coordinator, entry)
    )
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity.device_id != ours.id:
            ent_reg.async_update_entity(entity.entity_id, device_id=ours.id)
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if device.id in (ours.id, target):
            continue
        dev_reg.async_remove_device(device.id)
