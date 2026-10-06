"""Services exposed by the Appliance Live Activity integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

SERVICE_UPDATE = "update"

SERVICE_UPDATE_SCHEMA = vol.Schema({vol.Required("entry_id"): cv.string})


async def async_setup_services(hass: HomeAssistant) -> None:
    async def handle_update(call: ServiceCall) -> None:
        coordinator = hass.data[DOMAIN].get(call.data["entry_id"])
        if coordinator is None:
            return
        await coordinator.async_evaluate(send=True, force=True)

    hass.services.async_register(DOMAIN, SERVICE_UPDATE, handle_update, schema=SERVICE_UPDATE_SCHEMA)


async def async_unload_services(hass: HomeAssistant) -> None:
    hass.services.async_remove(DOMAIN, SERVICE_UPDATE)
