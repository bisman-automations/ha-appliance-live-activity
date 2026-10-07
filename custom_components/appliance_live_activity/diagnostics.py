"""Download diagnostics: settings, what the appliance reports, and what the
integration is doing -- attach this to bug reports."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .notify import notify_services_for_device, phone_is_home


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    result: dict[str, Any] = {
        "entry": {"title": entry.title, "data": dict(entry.data), "options": dict(entry.options)},
    }
    if coordinator is None:
        return result

    dev_reg = dr.async_get(hass)
    phones = {}
    for device_id in coordinator.devices:
        device = dev_reg.async_get(device_id)
        phones[device_id] = {
            "name": (device.name_by_user or device.name) if device else None,
            "notify_services": notify_services_for_device(hass, device_id, warn=False),
            "home": phone_is_home(hass, device_id),
        }

    entities = {}
    for entity_id in coordinator.configured_entities():
        state = hass.states.get(entity_id)
        entities[entity_id] = (
            {"state": state.state, "attributes": dict(state.attributes), "last_changed": state.last_changed.isoformat()}
            if state
            else None
        )

    result.update(
        {
            "appliance_type": coordinator.appliance_type,
            "data": {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in (coordinator.data or {}).items()},
            "phones": phones,
            "entities": entities,
            "internal": coordinator.diagnostics(),
        }
    )
    return result
