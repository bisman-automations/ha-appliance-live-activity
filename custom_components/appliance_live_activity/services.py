"""Services exposed by the Appliance Live Activity integration.

Registered once from ``async_setup``, not when the first config entry loads.
The handler looks the appliance up on ``entry.runtime_data``.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

SERVICE_UPDATE = "update"

SERVICE_UPDATE_SCHEMA = vol.Schema({vol.Required("entry_id"): cv.string})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register ``appliance_live_activity.update``.

    Safe to call once at startup. Calling it again would raise because the
    service is already registered; ``async_setup`` is the only caller.
    """

    async def handle_update(call: ServiceCall) -> None:
        """Re-send one appliance's Live Activity.

        Unknown or unloaded entries are ignored so a stale dashboard button
        does not raise.
        """
        entry = hass.config_entries.async_get_entry(call.data["entry_id"])
        if entry is None or not hasattr(entry, "runtime_data"):
            return
        await entry.runtime_data.async_evaluate(send=True, force=True)

    hass.services.async_register(
        DOMAIN, SERVICE_UPDATE, handle_update, schema=SERVICE_UPDATE_SCHEMA
    )
