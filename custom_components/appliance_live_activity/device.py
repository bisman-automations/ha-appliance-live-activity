"""The integration's device for an appliance, linked to the appliance itself.

Our device is shown as "Connected via" the appliance, so each device page
links to the other, and it starts out in the appliance's area. The appliance
is the GE device picked at setup, or -- for any other brand -- the device
the appliance's state sensor belongs to (e.g. an LG or Samsung washer).
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, GE_HOME_DOMAIN


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


def _source_identifier(hass: HomeAssistant, device_id: str | None) -> tuple[str, str] | None:
    if not device_id:
        return None
    device = dr.async_get(hass).async_get(device_id)
    if device is None or not device.identifiers:
        return None
    # Prefer the GE Home identifier when the device has several
    return next(
        (i for i in device.identifiers if i[0] == GE_HOME_DOMAIN),
        next(iter(sorted(device.identifiers))),
    )


def appliance_device_info(coordinator, entry: ConfigEntry) -> DeviceInfo:
    info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=coordinator.name,
        manufacturer="Appliance Live Activity",
        model=coordinator.definition.display_name,
    )
    via = _source_identifier(coordinator.hass, appliance_device_id(coordinator.hass, coordinator))
    if via is not None:
        info["via_device"] = via
    return info


@callback
def async_link_device(hass: HomeAssistant, coordinator, entry: ConfigEntry) -> None:
    """Make sure our device is connected via the appliance (also for devices
    created by older versions) and, if it has no area yet, use the appliance's."""
    dev_reg = dr.async_get(hass)
    own = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    source_id = appliance_device_id(hass, coordinator)
    source = dev_reg.async_get(source_id) if source_id else None
    if own is None or source is None:
        return
    changes = {}
    if own.via_device_id != source.id:
        changes["via_device_id"] = source.id
    if own.area_id is None and source.area_id is not None:
        changes["area_id"] = source.area_id
    if changes:
        dev_reg.async_update_device(own.id, **changes)
