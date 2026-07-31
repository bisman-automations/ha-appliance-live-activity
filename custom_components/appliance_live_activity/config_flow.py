"""Config flow: Add Integration -> pick appliance -> pick entities -> notify targets."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .appliance import APPLIANCE_REGISTRY
from .const import (
    CONF_APPLIANCE_TYPE,
    CONF_CYCLE_ENTITY,
    CONF_DEVICES,
    CONF_ICON,
    CONF_ICON_COLOR,
    CONF_NAME,
    CONF_NOTIFICATION_TAG,
    CONF_PHASE_ENTITY,
    CONF_REMAINING_ENTITY,
    CONF_STATE_ENTITY,
    DOMAIN,
)
from .helpers import slugify_tag


class ApplianceLiveActivityConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Three-step config flow: appliance type -> entities -> notification targets."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_entities()

        schema = vol.Schema(
            {
                vol.Required(CONF_APPLIANCE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=key, label=defn.display_name)
                            for key, defn in APPLIANCE_REGISTRY.items()
                        ],
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Required(CONF_NAME): selector.TextSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_entities(self, user_input: dict | None = None):
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notify()

        schema = vol.Schema(
            {
                vol.Required(CONF_STATE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_PHASE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_CYCLE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_REMAINING_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(step_id="entities", data_schema=schema)

    async def async_step_notify(self, user_input: dict | None = None):
        definition = APPLIANCE_REGISTRY[self._data[CONF_APPLIANCE_TYPE]]

        if user_input is not None:
            self._data.update(user_input)
            unique_id = f"{self._data[CONF_APPLIANCE_TYPE]}_{slugify_tag(self._data[CONF_NAME])}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        default_tag = f"{self._data[CONF_APPLIANCE_TYPE]}_{slugify_tag(self._data[CONF_NAME])}"
        schema = vol.Schema(
            {
                vol.Optional(CONF_ICON, default=definition.icon): selector.TextSelector(),
                vol.Optional(CONF_ICON_COLOR, default=definition.color): selector.TextSelector(),
                vol.Optional(CONF_NOTIFICATION_TAG, default=default_tag): selector.TextSelector(),
                vol.Optional(CONF_DEVICES, default=[]): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration="mobile_app", multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="notify", data_schema=schema)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return ApplianceLiveActivityOptionsFlow(config_entry)


class ApplianceLiveActivityOptionsFlow(config_entries.OptionsFlow):
    """Lets users change icon/color/notification devices after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Optional(CONF_ICON, default=current.get(CONF_ICON, "")): selector.TextSelector(),
                vol.Optional(
                    CONF_ICON_COLOR, default=current.get(CONF_ICON_COLOR, "")
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_DEVICES, default=current.get(CONF_DEVICES, [])
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration="mobile_app", multiple=True)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
