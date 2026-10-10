"""Which device the appliance's entities live on.

When the appliance has its own device in Home Assistant -- the GE device
picked at setup, or for other brands the device the state sensor belongs
to (an LG washer, a door's contact sensor) -- this integration's sensors,
event and Probe Target are added to *that* device, the same way Home
Assistant's own helpers (Utility Meter, Derivative…) attach to their source.
One "Kitchen Oven" instead of two. Otherwise the integration has a device of
its own.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device import (
    async_device_info_to_link_from_device_id,
    async_remove_stale_devices_links_keep_current_device,
)
from homeassistant.helpers.device_registry import DeviceInfo

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


def appliance_device_info(coordinator, entry: ConfigEntry) -> DeviceInfo:
    link = async_device_info_to_link_from_device_id(
        coordinator.hass, appliance_device_id(coordinator.hass, coordinator)
    )
    if link is not None:
        return link
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=coordinator.name,
        manufacturer="Appliance Live Activity",
        model=coordinator.definition.display_name,
    )


@callback
def async_link_device(hass: HomeAssistant, coordinator, entry: ConfigEntry) -> None:
    """Before the entities are added: move entities made by older versions
    (which had a separate device) onto the appliance's device and drop the
    separate device."""
    target = appliance_device_id(hass, coordinator)
    if target is not None:
        async_remove_stale_devices_links_keep_current_device(hass, entry.entry_id, target)
