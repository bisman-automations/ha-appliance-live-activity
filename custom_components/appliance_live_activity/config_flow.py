"""Config flow.

GE Home (SmartHQ) appliances: pick the device -> entities are found
automatically -> pick phones.

Anything else: pick appliance type -> pick entities -> pick phones.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .appliance import APPLIANCE_REGISTRY
from .const import (
    CONF_APPLIANCE_TYPE,
    CONF_CYCLE_ENTITY,
    CONF_DEVICES,
    CONF_DISMISS_MINUTES,
    CONF_DONE_ENTITY,
    CONF_DOOR_ENTITY,
    CONF_FINISHED_ALERT,
    CONF_ICON,
    CONF_ICON_COLOR,
    CONF_NAME,
    CONF_NOTIFICATION_TAG,
    CONF_PHASE_ENTITY,
    CONF_REMAINING_ENTITY,
    CONF_SOURCE,
    CONF_SOURCE_DEVICE,
    CONF_STATE_ENTITY,
    DEFAULT_DISMISS_MINUTES,
    DOMAIN,
    GE_HOME_DOMAIN,
    SOURCE_GE_HOME,
    SOURCE_MANUAL,
)
from .ge import async_discover, async_has_ge_devices, device_name
from .helpers import slugify_tag

AUTO = "auto"


def _type_selector(include_auto: bool) -> selector.SelectSelector:
    options = [
        selector.SelectOptionDict(value=key, label=defn.display_name)
        for key, defn in APPLIANCE_REGISTRY.items()
    ]
    if include_auto:
        options.insert(0, selector.SelectOptionDict(value=AUTO, label="Detect automatically"))
    return selector.SelectSelector(
        selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
    )


def _phones_selector() -> selector.DeviceSelector:
    return selector.DeviceSelector(
        selector.DeviceSelectorConfig(
            filter=[selector.DeviceFilterSelectorConfig(integration="mobile_app")],
            multiple=True,
        )
    )


def _dismiss_selector() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=240, step=5, unit_of_measurement="min", mode=selector.NumberSelectorMode.BOX
        )
    )


class ApplianceLiveActivityConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Appliance Live Activity."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Choose GE Home auto-setup or manual setup."""
        if async_has_ge_devices(self.hass):
            return self.async_show_menu(step_id="user", menu_options=[SOURCE_GE_HOME, SOURCE_MANUAL])
        return await self.async_step_manual()

    # ------------------------------------------------------------------
    # GE Home (SmartHQ)
    # ------------------------------------------------------------------
    async def async_step_ge_home(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a GE appliance; its entities are discovered automatically."""
        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = user_input[CONF_SOURCE_DEVICE]
            found = async_discover(self.hass, device_id)
            chosen = user_input.get(CONF_APPLIANCE_TYPE, AUTO)
            appliance_type = found.appliance_type if chosen == AUTO else chosen

            if not found.state_entity:
                errors["base"] = "no_ge_entities"
            elif appliance_type not in APPLIANCE_REGISTRY:
                errors[CONF_APPLIANCE_TYPE] = "unknown_type"
            else:
                await self.async_set_unique_id(f"{GE_HOME_DOMAIN}_{device_id}")
                self._abort_if_unique_id_configured()
                name = (user_input.get(CONF_NAME) or "").strip() or (
                    device_name(self.hass, device_id) or APPLIANCE_REGISTRY[appliance_type].display_name
                )
                self._data = {
                    CONF_SOURCE: SOURCE_GE_HOME,
                    CONF_SOURCE_DEVICE: device_id,
                    CONF_APPLIANCE_TYPE: appliance_type,
                    CONF_NAME: name,
                    **found.as_config(),
                }
                return await self.async_step_notify()

        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE_DEVICE): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        filter=[selector.DeviceFilterSelectorConfig(integration=GE_HOME_DOMAIN)]
                    )
                ),
                vol.Optional(CONF_NAME): selector.TextSelector(),
                vol.Optional(CONF_APPLIANCE_TYPE, default=AUTO): _type_selector(include_auto=True),
            }
        )
        return self.async_show_form(
            step_id=SOURCE_GE_HOME,
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Manual (any brand)
    # ------------------------------------------------------------------
    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick appliance type and name."""
        if user_input is not None:
            self._data = {CONF_SOURCE: SOURCE_MANUAL, **user_input}
            return await self.async_step_entities()

        schema = vol.Schema(
            {
                vol.Required(CONF_APPLIANCE_TYPE): _type_selector(include_auto=False),
                vol.Required(CONF_NAME): selector.TextSelector(),
            }
        )
        return self.async_show_form(step_id=SOURCE_MANUAL, data_schema=schema)

    async def async_step_entities(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick the appliance's entities."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_notify()

        sensor = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        binary = selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor"))
        schema = vol.Schema(
            {
                vol.Required(CONF_STATE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
                ),
                vol.Optional(CONF_PHASE_ENTITY): sensor,
                vol.Optional(CONF_CYCLE_ENTITY): sensor,
                vol.Optional(CONF_REMAINING_ENTITY): sensor,
                vol.Optional(CONF_DONE_ENTITY): binary,
                vol.Optional(CONF_DOOR_ENTITY): binary,
            }
        )
        return self.async_show_form(step_id="entities", data_schema=schema)

    # ------------------------------------------------------------------
    # Notifications (shared)
    # ------------------------------------------------------------------
    async def async_step_notify(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick phones and notification options."""
        definition = APPLIANCE_REGISTRY[self._data[CONF_APPLIANCE_TYPE]]
        default_tag = f"{self._data[CONF_APPLIANCE_TYPE]}_{slugify_tag(self._data[CONF_NAME])}"

        if user_input is not None:
            self._data.update(user_input)
            if self._data.get(CONF_SOURCE) != SOURCE_GE_HOME:
                await self.async_set_unique_id(default_tag)
                self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICES, default=[]): _phones_selector(),
                vol.Optional(CONF_FINISHED_ALERT, default=True): selector.BooleanSelector(),
                vol.Optional(CONF_DISMISS_MINUTES, default=DEFAULT_DISMISS_MINUTES): _dismiss_selector(),
                vol.Optional(CONF_ICON, default=definition.icon): selector.IconSelector(),
                vol.Optional(CONF_ICON_COLOR, default=definition.color): selector.TextSelector(),
                vol.Optional(CONF_NOTIFICATION_TAG, default=default_tag): selector.TextSelector(),
            }
        )
        return self.async_show_form(step_id="notify", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ApplianceLiveActivityOptionsFlow()


class ApplianceLiveActivityOptionsFlow(OptionsFlow):
    """Change phones, alerts and appearance after setup."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        definition = APPLIANCE_REGISTRY[current[CONF_APPLIANCE_TYPE]]
        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICES, default=current.get(CONF_DEVICES, [])): _phones_selector(),
                vol.Optional(
                    CONF_FINISHED_ALERT, default=current.get(CONF_FINISHED_ALERT, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_DISMISS_MINUTES,
                    default=current.get(CONF_DISMISS_MINUTES, DEFAULT_DISMISS_MINUTES),
                ): _dismiss_selector(),
                vol.Optional(
                    CONF_ICON, default=current.get(CONF_ICON) or definition.icon
                ): selector.IconSelector(),
                vol.Optional(
                    CONF_ICON_COLOR, default=current.get(CONF_ICON_COLOR) or definition.color
                ): selector.TextSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
