"""The integration's device for each appliance, linked to the appliance's own.

Every appliance gets a device of this integration ("Kitchen Oven Live
Activity") holding its sensors, event and Probe Target. When the appliance
also has a device of its own -- the GE device picked at setup, or for other
brands the device the state sensor belongs to (an LG washer, a door's
contact sensor) -- our device repeats that device's identifiers and
connections. Home Assistant 2026.8+ gives every device a single owning
integration and lists devices that share an identifier or connection under
**Linked devices** ("These devices share hardware with this device and are
managed by other integrations"), the same way UniFi Network's client device
shows up on a Rain Bird controller. So each page links to the other.

Before 2026.8 devices with shared identifiers were merged into one, so
there our device keeps only its own identifier.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

# Device registry v3 (Home Assistant 2026.8): one config entry per device,
# shared identifiers/connections across integrations become "Linked devices"
LINKED_DEVICES_SUPPORTED = getattr(dr, "STORAGE_VERSION_MAJOR", 1) >= 3


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
    )
    target = appliance_device_id(coordinator.hass, coordinator)
    if target is None:
        return info
    appliance = dr.async_get(coordinator.hass).async_get(target)
    # Distinct from the appliance's own device in the Linked devices list
    info["name"] = f"{coordinator.name} Live Activity"
    if LINKED_DEVICES_SUPPORTED:
        info["identifiers"] = {(DOMAIN, entry.entry_id)} | {
            i for i in appliance.identifiers if i[0] != DOMAIN
        }
        if appliance.connections:
            info["connections"] = set(appliance.connections)
    return info


def attach_to_appliance(entity: Entity, coordinator, entry: ConfigEntry) -> None:
    """Put an entity on this integration's device for the appliance."""
    entity._attr_device_info = own_device_info(coordinator, entry)


@callback
def async_link_device(hass: HomeAssistant, coordinator, entry: ConfigEntry) -> None:
    """Before the entities are added: create our device for the appliance,
    move our entities onto it (1.9.4 put them on the appliance's device) and
    remove any other device this entry owns."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    target = appliance_device_id(hass, coordinator)

    # Before 2026.8, versions before 1.9.4 co-owned the GE device: let go of it
    # first, or registering our device would find and reuse it
    if target is not None and not LINKED_DEVICES_SUPPORTED:
        device = dev_reg.async_get(target)
        if device is not None and entry.entry_id in device.config_entries:
            dev_reg.async_update_device(target, remove_config_entry_id=entry.entry_id)

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
