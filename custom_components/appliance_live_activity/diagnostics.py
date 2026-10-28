"""Download diagnostics: settings, what the appliance reports, and what the
integration is doing -- attach this to bug reports.

Personal data is redacted before the file is returned. Home Assistant's
``async_redact_data`` walks the tree and replaces every value whose key is
in ``TO_REDACT``. Picture URLs are in that set because an ``entity_picture``
link carries an access token that works until Home Assistant restarts, the
same set TV Mgmt uses. Phone names and "is this person home" are personal.
Config-entry data is included in the walk, so a custom title and the list
of chosen phones are redacted too; entity ids of the appliance sensors are
left, because a bug report needs them.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_ACTIVITY_TITLE,
    CONF_DEVICES,
    CONF_ESCALATION_DEVICES,
    CONF_LAUNDRY_TITLE,
    CONF_NAME,
)
from .notify import notify_services_for_device, phone_is_home

# Keys removed from the download. Modelled on TV Mgmt's TO_REDACT: picture
# URLs, plus the names and presence this integration adds.
TO_REDACT = {
    "entity_picture",
    "entity_picture_local",
    # Phone name, the appliance's configured name, and a name the user typed.
    "name",
    CONF_NAME,
    "name_by_user",
    # notify.mobile_app_<phone> is the phone's name with a prefix.
    "notify_services",
    "notify",
    # True/False: the Companion app says this phone's owner is home.
    "home",
    # Device ids of the phones picked at setup, and titles that may name a person.
    CONF_DEVICES,
    CONF_ESCALATION_DEVICES,
    CONF_ACTIVITY_TITLE,
    CONF_LAUNDRY_TITLE,
    "title",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Diagnostics for one appliance, with personal data redacted."""
    return async_redact_data(_diagnostics(hass, entry), TO_REDACT)


def _diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Build the diagnostics tree. Redaction happens in the caller."""
    coordinator = entry.runtime_data if hasattr(entry, "runtime_data") else None
    result: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
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
            {
                "state": state.state,
                "attributes": dict(state.attributes),
                "last_changed": state.last_changed.isoformat(),
            }
            if state
            else None
        )

    result.update(
        {
            "appliance_type": coordinator.appliance_type,
            "data": {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in (coordinator.data or {}).items()
            },
            "phones": phones,
            "entities": entities,
            "internal": coordinator.diagnostics(),
        }
    )
    return result
