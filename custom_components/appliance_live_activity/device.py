"""Which device the appliance's entities live on.

When the appliance has its own device in Home Assistant -- the GE device
picked at setup, or for other brands the device the state sensor belongs
to (an LG washer, a door's contact sensor) -- this integration's sensors,
event and Probe Target are linked to *that* device, so each appliance is one
device. Otherwise the integration has a device of its own.

Home Assistant 2026.9+ gives every device a single owning integration; an
entity links to another integration's device by setting ``device_entry``
(not by repeating that device's identifiers in ``device_info``, which now
creates a separate copy). That works on older versions too.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


def appliance_device_id(hass: HomeAssistant, coordinator) -> str | None:
    """The appliance's own device: the GE device chosen at setup, else the
    device of the state sensor (never this integration's own device)."""
    dev_reg = dr.async_get(hass)
    if coordinator.source_device and dev_reg.async_get(coordinator.source_device):
        return coordinator.source_device
    if not coordinator.state_entity:
        return None
    entry = er.async_get(hass).async_get(coordinator.state_entity)
    if entry is None or entry.device_id is None:
        return None
    device = dev_reg.async_get(entry.device_id)
    if device is None or any(i[0] == DOMAIN for i in device.identifiers):
        return None
    return device.id


def own_device_info(coordinator, entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=coordinator.name,
        manufacturer="Appliance Live Activity",
        model=coordinator.definition.display_name,
    )


def attach_to_appliance(entity: Entity, coordinator, entry: ConfigEntry) -> None:
    """Put an entity on the appliance's device, or on our own device."""
    target = appliance_device_id(coordinator.hass, coordinator)
    if target is not None:
        entity._attr_device_info = None
        entity.device_entry = dr.async_get(coordinator.hass).async_get(target)
    else:
        entity._attr_device_info = own_device_info(coordinator, entry)


@callback
def async_link_device(hass: HomeAssistant, coordinator, entry: ConfigEntry) -> None:
    """Before the entities are added: move entities that older versions put on
    a device of this integration's own onto the appliance's device, and
    remove that separate device."""
    target = appliance_device_id(hass, coordinator)
    if target is None:
        return
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity.device_id != target:
            ent_reg.async_update_entity(entity.entity_id, device_id=target)
    # Devices this integration owns for the appliance (the separate "Kitchen
    # Oven" of 1.9.x, or a copy Home Assistant split off a device co-owned on
    # an older version) are no longer needed
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        if device.id == target:
            if getattr(device, "config_entry_id", None) is None and len(device.config_entries) > 1:
                # Home Assistant before 2026.9: co-owned by older versions
                dev_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
            continue
        dev_reg.async_remove_device(device.id)
