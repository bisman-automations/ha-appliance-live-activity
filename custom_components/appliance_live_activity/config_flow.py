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
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .appliance import APPLIANCE_REGISTRY
from .const import (
    CONF_ALERT_LIGHTS,
    CONF_APPLIANCE_TYPE,
    CONF_CLEAN_ENTITY,
    CONF_COOKTOP_ALERT_MINUTES,
    CONF_COOKTOP_ENTITIES,
    CONF_COOKTOP_REPEAT_MINUTES,
    CONF_CRITICAL_AFTER_MINUTES,
    CONF_CRITICAL_REPEAT_MINUTES,
    CONF_COMBINE_LAUNDRY,
    CONF_CYCLE_ENTITY,
    CONF_DELAY_ENTITY,
    CONF_DELAY_START,
    CONF_DEVICES,
    CONF_DISMISS_MINUTES,
    CONF_DONE_ENTITY,
    CONF_DOOR_ENTITIES,
    CONF_DOOR_ENTITY,
    CONF_DRYER_ENTITY,
    CONF_DRYER_START_ENTITY,
    CONF_ESCALATE_AFTER,
    CONF_ESCALATION_DEVICES,
    CONF_FILTER_ENTITY,
    CONF_FINISHED_ALERT,
    CONF_FREEZER_MAX_TEMP,
    CONF_FREEZER_TEMP_ENTITY,
    CONF_FRIDGE_MAX_TEMP,
    CONF_FRIDGE_TEMP_ENTITY,
    CONF_ICE_ENTITY,
    CONF_ICE_FULL_ALERT,
    CONF_GE_DISCOVERY,
    CONF_ICON,
    CONF_ICON_COLOR,
    CONF_LEAK_ENTITIES,
    CONF_LEAK_REPEAT_MINUTES,
    CONF_MOVE_MAX_REMINDERS,
    CONF_MOVE_REMINDER_MINUTES,
    CONF_MOVE_REPEAT_MINUTES,
    CONF_NAME,
    CONF_NOTIFICATION_TAG,
    CONF_ONLY_HOME,
    CONF_OPEN_DELAY_SECONDS,
    CONF_OVEN_CAVITY,
    CONF_PHASE_ENTITY,
    CONF_PREHEAT_ALERT,
    CONF_PROBE_ENTITY,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_REMAINING_ENTITY,
    CONF_SNOOZE_MINUTES,
    CONF_SOURCE,
    CONF_SOURCE_DEVICE,
    CONF_SPEAKERS,
    CONF_STATE_ENTITY,
    CONF_SUPPLY_ENTITIES,
    CONF_SUPPLY_LOW,
    CONF_TARGET_TEMPERATURE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_TIMER_ENTITY,
    CONF_TTS_ENTITY,
    CONF_TUMBLE_ENTITY,
    CONF_VENT_ENTITY,
    CONF_WARM_MINUTES,
    DEFAULT_COOKTOP_ALERT_MINUTES,
    DEFAULT_COOKTOP_REPEAT_MINUTES,
    DEFAULT_CRITICAL_AFTER_MINUTES,
    DEFAULT_CRITICAL_REPEAT_MINUTES,
    DEFAULT_DISMISS_MINUTES,
    DEFAULT_DRYER_MAX_REMINDERS,
    DEFAULT_DRYER_REMINDER_MINUTES,
    DEFAULT_DRYER_REPEAT_MINUTES,
    DEFAULT_FREEZER_MAX_C,
    DEFAULT_FREEZER_MAX_F,
    DEFAULT_FRIDGE_MAX_C,
    DEFAULT_FRIDGE_MAX_F,
    DEFAULT_ESCALATE_AFTER,
    DEFAULT_LEAK_REPEAT_MINUTES,
    DEFAULT_MOVE_MAX_REMINDERS,
    DEFAULT_MOVE_REMINDER_MINUTES,
    DEFAULT_MOVE_REPEAT_MINUTES,
    DEFAULT_OPEN_DELAY_SECONDS,
    DEFAULT_SNOOZE_MINUTES,
    DEFAULT_SUPPLY_LOW,
    DEFAULT_WARM_MINUTES,
    DOMAIN,
    DOOR_TYPES,
    GE_HOME_DOMAIN,
    SOURCE_GE_HOME,
    SOURCE_MANUAL,
)
from .ge import async_discover, async_has_ge_devices, device_name

GE_DISCOVERY_VERSION = 5  # keep in sync with __init__.GE_DISCOVERY_VERSION
from .helpers import hex_to_rgb, slugify_tag

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


def _number(min_: float, max_: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_, max=max_, step=step, unit_of_measurement=unit, mode=selector.NumberSelectorMode.BOX
        )
    )


def _make_tag(appliance_type: str, name: str) -> str:
    """Notification tag, e.g. 'kitchen_refrigerator' (no repeated type prefix)."""
    slug = slugify_tag(name) or appliance_type
    return slug if appliance_type in slug.split("_") else f"{appliance_type}_{slug}"


def _current_rgb(value, fallback_hex: str) -> list[int]:
    """Stored color (RGB list, or hex from older versions) as an RGB list."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return [int(c) for c in value]
    return hex_to_rgb(value or fallback_hex)


def _announce_fields() -> dict:
    return {
        vol.Optional(CONF_TTS_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="tts")
        ),
        vol.Optional(CONF_SPEAKERS): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="media_player", multiple=True)
        ),
    }


# Optional fields without defaults: cleared in Configure -> stored as None
CLEARABLE = (
    CONF_LEAK_ENTITIES,
    CONF_DRYER_ENTITY,
    CONF_DRYER_START_ENTITY,
    CONF_TTS_ENTITY,
    CONF_SPEAKERS,
    CONF_ESCALATION_DEVICES,
    CONF_ALERT_LIGHTS,
    CONF_SUPPLY_ENTITIES,
    CONF_FILTER_ENTITY,
    CONF_VENT_ENTITY,
    CONF_QUIET_START,
    CONF_QUIET_END,
)

# Which collapsible section of the form each setting lives in (anything not
# listed stays at the top). Order = order on screen; True = collapsed.
SECTIONS: dict[str, bool] = {
    "laundry": False,
    "cooking": False,
    "fridge": False,
    "escalation": True,
    "health": True,
    "leaks": True,
    "announcements": True,
    "quiet_hours": True,
    "appearance": True,
}
SECTION_OF: dict[str, str] = {
    CONF_MOVE_REMINDER_MINUTES: "laundry",
    CONF_MOVE_REPEAT_MINUTES: "laundry",
    CONF_MOVE_MAX_REMINDERS: "laundry",
    CONF_DRYER_ENTITY: "laundry",
    CONF_DRYER_START_ENTITY: "laundry",
    CONF_COMBINE_LAUNDRY: "laundry",
    CONF_PREHEAT_ALERT: "cooking",
    CONF_COOKTOP_ALERT_MINUTES: "cooking",
    CONF_COOKTOP_REPEAT_MINUTES: "cooking",
    CONF_FRIDGE_MAX_TEMP: "fridge",
    CONF_FREEZER_MAX_TEMP: "fridge",
    CONF_WARM_MINUTES: "fridge",
    CONF_ICE_FULL_ALERT: "fridge",
    CONF_ESCALATE_AFTER: "escalation",
    CONF_ESCALATION_DEVICES: "escalation",
    CONF_ALERT_LIGHTS: "escalation",
    CONF_SUPPLY_ENTITIES: "health",
    CONF_SUPPLY_LOW: "health",
    CONF_FILTER_ENTITY: "health",
    CONF_VENT_ENTITY: "health",
    CONF_LEAK_ENTITIES: "leaks",
    CONF_LEAK_REPEAT_MINUTES: "leaks",
    CONF_TTS_ENTITY: "announcements",
    CONF_SPEAKERS: "announcements",
    CONF_QUIET_START: "quiet_hours",
    CONF_QUIET_END: "quiet_hours",
    CONF_ICON: "appearance",
    CONF_ICON_COLOR: "appearance",
}


def _key_name(key) -> str:
    return str(key.schema if isinstance(key, vol.Marker) else key)


def _sectioned(fields: dict) -> vol.Schema:
    """Group a flat field dict into collapsible sections."""
    top: dict = {}
    grouped: dict[str, dict] = {name: {} for name in SECTIONS}
    for key, value in fields.items():
        name = SECTION_OF.get(_key_name(key))
        (grouped[name] if name else top)[key] = value
    for name, collapsed in SECTIONS.items():
        if grouped[name]:
            # Must be Required: the frontend neither shows nor submits the
            # values of a section whose key is Optional
            top[vol.Required(name)] = section(
                vol.Schema(grouped[name]), {"collapsed": collapsed}
            )
    return vol.Schema(top)


def _nest(values: dict[str, Any]) -> dict[str, Any]:
    """Flat stored values -> suggested values shaped like the sectioned form."""
    nested: dict[str, Any] = {name: {} for name in SECTIONS}
    for key, value in values.items():
        name = SECTION_OF.get(key)
        if name:
            nested[name][key] = value
        else:
            nested[key] = value
    return nested


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Sectioned form input -> the flat settings that are stored."""
    flat: dict[str, Any] = {}
    for key, value in user_input.items():
        if key in SECTIONS and isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def _temperature_defaults(hass) -> tuple[float, float]:
    if hass.config.units.temperature_unit == "°F":
        return DEFAULT_FRIDGE_MAX_F, DEFAULT_FREEZER_MAX_F
    return DEFAULT_FRIDGE_MAX_C, DEFAULT_FREEZER_MAX_C


def _behaviour_fields(
    appliance_type: str,
    current: dict[str, Any],
    has_cooktop: bool,
    temperature_defaults: tuple[float, float] = (DEFAULT_FRIDGE_MAX_F, DEFAULT_FREEZER_MAX_F),
) -> dict:
    """Alert settings for the appliance type, flat (see _sectioned). Entity
    pickers are pre-filled via suggested values."""
    fields: dict = {}
    if appliance_type in DOOR_TYPES:
        fields.update(
            {
                vol.Optional(
                    CONF_OPEN_DELAY_SECONDS,
                    default=current.get(CONF_OPEN_DELAY_SECONDS, DEFAULT_OPEN_DELAY_SECONDS),
                ): _number(0, 600, 5, "s"),
                vol.Optional(
                    CONF_CRITICAL_AFTER_MINUTES,
                    default=current.get(CONF_CRITICAL_AFTER_MINUTES, DEFAULT_CRITICAL_AFTER_MINUTES),
                ): _number(1, 120, 1, "min"),
                vol.Optional(
                    CONF_CRITICAL_REPEAT_MINUTES,
                    default=current.get(CONF_CRITICAL_REPEAT_MINUTES, DEFAULT_CRITICAL_REPEAT_MINUTES),
                ): _number(1, 60, 1, "min"),
                vol.Optional(
                    CONF_SNOOZE_MINUTES,
                    default=current.get(CONF_SNOOZE_MINUTES, DEFAULT_SNOOZE_MINUTES),
                ): _number(0, 120, 5, "min"),
                vol.Optional(
                    CONF_ESCALATE_AFTER,
                    default=current.get(CONF_ESCALATE_AFTER, DEFAULT_ESCALATE_AFTER),
                ): _number(0, 50, 1, "alerts"),
                vol.Optional(CONF_ESCALATION_DEVICES): _phones_selector(),
                vol.Optional(CONF_ALERT_LIGHTS): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="light", multiple=True)
                ),
            }
        )
    else:
        fields.update(
            {
                vol.Optional(
                    CONF_FINISHED_ALERT, default=current.get(CONF_FINISHED_ALERT, True)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_ONLY_HOME, default=current.get(CONF_ONLY_HOME, False)
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_DISMISS_MINUTES,
                    default=current.get(CONF_DISMISS_MINUTES, DEFAULT_DISMISS_MINUTES),
                ): _dismiss_selector(),
                vol.Optional(
                    CONF_DELAY_START, default=current.get(CONF_DELAY_START, True)
                ): selector.BooleanSelector(),
            }
        )
        if appliance_type in ("washer", "dryer", "dishwasher"):
            fields.update(
                {
                    vol.Optional(CONF_SUPPLY_ENTITIES): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["sensor", "number", "binary_sensor"], multiple=True
                        )
                    ),
                    vol.Optional(
                        CONF_SUPPLY_LOW, default=current.get(CONF_SUPPLY_LOW, DEFAULT_SUPPLY_LOW)
                    ): _number(0, 50, 1, "left"),
                }
            )
    if appliance_type in ("refrigerator", "dishwasher"):
        fields[vol.Optional(CONF_FILTER_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        )
    if appliance_type == "dryer":
        fields[vol.Optional(CONF_VENT_ENTITY)] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        )
    if appliance_type == "oven":
        fields[
            vol.Optional(CONF_PREHEAT_ALERT, default=current.get(CONF_PREHEAT_ALERT, True))
        ] = selector.BooleanSelector()
    if appliance_type in ("washer", "dryer"):
        if appliance_type == "dryer":
            defaults = (DEFAULT_DRYER_REMINDER_MINUTES, DEFAULT_DRYER_REPEAT_MINUTES, DEFAULT_DRYER_MAX_REMINDERS)
        else:
            defaults = (DEFAULT_MOVE_REMINDER_MINUTES, DEFAULT_MOVE_REPEAT_MINUTES, DEFAULT_MOVE_MAX_REMINDERS)
        fields.update(
            {
                vol.Optional(
                    CONF_MOVE_REMINDER_MINUTES,
                    default=current.get(CONF_MOVE_REMINDER_MINUTES, defaults[0]),
                ): _number(0, 240, 5, "min"),
                vol.Optional(
                    CONF_MOVE_REPEAT_MINUTES,
                    default=current.get(CONF_MOVE_REPEAT_MINUTES, defaults[1]),
                ): _number(5, 120, 5, "min"),
                vol.Optional(
                    CONF_MOVE_MAX_REMINDERS,
                    default=current.get(CONF_MOVE_MAX_REMINDERS, defaults[2]),
                ): _number(1, 10, 1, "reminders"),
            }
        )
    if appliance_type == "refrigerator":
        fridge_max, freezer_max = temperature_defaults
        fields.update(
            {
                vol.Optional(
                    CONF_FRIDGE_MAX_TEMP, default=current.get(CONF_FRIDGE_MAX_TEMP, fridge_max)
                ): _number(-10, 70, 1, "°"),
                vol.Optional(
                    CONF_FREEZER_MAX_TEMP, default=current.get(CONF_FREEZER_MAX_TEMP, freezer_max)
                ): _number(-40, 40, 1, "°"),
                vol.Optional(
                    CONF_WARM_MINUTES, default=current.get(CONF_WARM_MINUTES, DEFAULT_WARM_MINUTES)
                ): _number(5, 240, 5, "min"),
                vol.Optional(
                    CONF_ICE_FULL_ALERT, default=current.get(CONF_ICE_FULL_ALERT, False)
                ): selector.BooleanSelector(),
            }
        )
    if appliance_type == "washer":
        fields.update(
            {
                vol.Optional(CONF_DRYER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_DRYER_START_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="button")
                ),
                vol.Optional(
                    CONF_COMBINE_LAUNDRY, default=current.get(CONF_COMBINE_LAUNDRY, True)
                ): selector.BooleanSelector(),
            }
        )
    if has_cooktop:
        fields.update(
            {
                vol.Optional(
                    CONF_COOKTOP_ALERT_MINUTES,
                    default=current.get(CONF_COOKTOP_ALERT_MINUTES, DEFAULT_COOKTOP_ALERT_MINUTES),
                ): _number(1, 240, 1, "min"),
                vol.Optional(
                    CONF_COOKTOP_REPEAT_MINUTES,
                    default=current.get(CONF_COOKTOP_REPEAT_MINUTES, DEFAULT_COOKTOP_REPEAT_MINUTES),
                ): _number(1, 120, 1, "min"),
            }
        )
    # Every appliance: leak sensors + speaker announcements
    fields.update(
        {
            vol.Optional(CONF_LEAK_ENTITIES): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor", device_class="moisture", multiple=True
                )
            ),
            vol.Optional(
                CONF_LEAK_REPEAT_MINUTES,
                default=current.get(CONF_LEAK_REPEAT_MINUTES, DEFAULT_LEAK_REPEAT_MINUTES),
            ): _number(1, 60, 1, "min"),
            **_announce_fields(),
            vol.Optional(CONF_QUIET_START): selector.TimeSelector(),
            vol.Optional(CONF_QUIET_END): selector.TimeSelector(),
        }
    )
    return fields


REDISCOVER = "rediscover"


def _entity_fields(appliance_type: str) -> dict:
    """The appliance's sensors (Reconfigure)."""
    sensor = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
    binary = selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor"))
    if appliance_type in DOOR_TYPES:
        fields: dict = {
            vol.Required(CONF_STATE_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
            ),
            vol.Optional(CONF_DOOR_ENTITIES): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
            ),
        }
        if appliance_type == "refrigerator":
            fields.update(
                {
                    vol.Optional(CONF_FRIDGE_TEMP_ENTITY): sensor,
                    vol.Optional(CONF_FREEZER_TEMP_ENTITY): sensor,
                    vol.Optional(CONF_ICE_ENTITY): sensor,
                }
            )
        return fields
    fields = {
        vol.Required(CONF_STATE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        ),
        vol.Optional(CONF_PHASE_ENTITY): sensor,
        vol.Optional(CONF_CYCLE_ENTITY): sensor,
        vol.Optional(CONF_REMAINING_ENTITY): sensor,
        vol.Optional(CONF_DELAY_ENTITY): sensor,
        vol.Optional(CONF_DONE_ENTITY): binary,
        vol.Optional(CONF_DOOR_ENTITY): binary,
    }
    if appliance_type == "oven":
        fields.update(
            {
                vol.Optional(CONF_COOKTOP_ENTITIES): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
                ),
                vol.Optional(CONF_TEMPERATURE_ENTITY): sensor,
                vol.Optional(CONF_TARGET_TEMPERATURE_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["water_heater", "climate", "number", "sensor"])
                ),
                vol.Optional(CONF_TIMER_ENTITY): sensor,
                vol.Optional(CONF_PROBE_ENTITY): sensor,
            }
        )
    if appliance_type == "dryer":
        fields[vol.Optional(CONF_TUMBLE_ENTITY)] = sensor
    if appliance_type == "dishwasher":
        fields[vol.Optional(CONF_CLEAN_ENTITY)] = binary
    return fields


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
                name = (user_input.get(CONF_NAME) or "").strip()
                self._data = {
                    CONF_SOURCE: SOURCE_GE_HOME,
                    CONF_SOURCE_DEVICE: device_id,
                    CONF_APPLIANCE_TYPE: appliance_type,
                    CONF_NAME: name,
                }
                if appliance_type == "oven" and found.cavities:
                    # Double oven: one entry per oven
                    return await self.async_step_oven_cavity()
                return await self._async_ge_finish(None)

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

    async def async_step_oven_cavity(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Double oven: choose the upper or lower oven."""
        if user_input is not None:
            return await self._async_ge_finish(user_input[CONF_OVEN_CAVITY])
        configured = {
            entry.data.get(CONF_OVEN_CAVITY)
            for entry in self._async_current_entries(include_ignore=False)
            if entry.data.get(CONF_SOURCE_DEVICE) == self._data[CONF_SOURCE_DEVICE]
        }
        options = [
            selector.SelectOptionDict(value=c, label=f"{c.title()} oven")
            for c in ("upper", "lower")
            if c not in configured
        ]
        if not options:
            return self.async_abort(reason="already_configured")
        schema = vol.Schema(
            {
                vol.Required(CONF_OVEN_CAVITY, default=options[0]["value"]): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=options)
                )
            }
        )
        return self.async_show_form(step_id="oven_cavity", data_schema=schema)

    async def _async_ge_finish(self, cavity: str | None) -> ConfigFlowResult:
        device_id = self._data[CONF_SOURCE_DEVICE]
        appliance_type = self._data[CONF_APPLIANCE_TYPE]
        found = async_discover(self.hass, device_id, cavity)
        unique = f"{GE_HOME_DOMAIN}_{device_id}" + (f"_{cavity}" if cavity else "")
        await self.async_set_unique_id(unique)
        self._abort_if_unique_id_configured()
        name = self._data.get(CONF_NAME) or (
            device_name(self.hass, device_id) or APPLIANCE_REGISTRY[appliance_type].display_name
        )
        if cavity and not self._data.get(CONF_NAME):
            name = f"{name} {cavity.title()}"
        self._data.update(
            {CONF_NAME: name, **found.as_config(), CONF_GE_DISCOVERY: GE_DISCOVERY_VERSION}
        )
        return await self.async_step_notify()

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
                vol.Optional(CONF_DELAY_ENTITY): sensor,
            }
        )
        if self._data[CONF_APPLIANCE_TYPE] == "oven":
            schema = schema.extend(
                {
                    vol.Optional(CONF_COOKTOP_ENTITIES): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
                    ),
                    vol.Optional(CONF_TEMPERATURE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                    ),
                    vol.Optional(CONF_TARGET_TEMPERATURE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["water_heater", "climate", "number", "sensor"]
                        )
                    ),
                    vol.Optional(CONF_TIMER_ENTITY): sensor,
                    vol.Optional(CONF_PROBE_ENTITY): sensor,
                }
            )
        if self._data[CONF_APPLIANCE_TYPE] == "dryer":
            schema = schema.extend({vol.Optional(CONF_TUMBLE_ENTITY): sensor})
        if self._data[CONF_APPLIANCE_TYPE] in DOOR_TYPES:
            # Doors only: the state entity is the first door, add more here
            schema = vol.Schema(
                {
                    vol.Required(CONF_STATE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["binary_sensor", "sensor"])
                    ),
                    vol.Optional(CONF_DOOR_ENTITIES): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)
                    ),
                }
            )
        return self.async_show_form(step_id="entities", data_schema=schema)

    # ------------------------------------------------------------------
    # Notifications (shared)
    # ------------------------------------------------------------------
    async def async_step_notify(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick phones and notification options."""
        definition = APPLIANCE_REGISTRY[self._data[CONF_APPLIANCE_TYPE]]
        default_tag = _make_tag(self._data[CONF_APPLIANCE_TYPE], self._data[CONF_NAME])

        if user_input is not None:
            self._data.update(_flatten(user_input))
            # Internal: identifies this appliance's notifications on the phone
            self._data[CONF_NOTIFICATION_TAG] = default_tag
            if self._data.get(CONF_SOURCE) != SOURCE_GE_HOME:
                await self.async_set_unique_id(default_tag)
                self._abort_if_unique_id_configured()
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)

        schema = _sectioned(
            {
                vol.Required(CONF_DEVICES, default=[]): _phones_selector(),
                **_behaviour_fields(
                    self._data[CONF_APPLIANCE_TYPE],
                    {},
                    bool(self._data.get(CONF_COOKTOP_ENTITIES)),
                    _temperature_defaults(self.hass),
                ),
                vol.Optional(CONF_ICON, default=definition.icon): selector.IconSelector(),
                vol.Optional(CONF_ICON_COLOR, default=hex_to_rgb(definition.color)): selector.ColorRGBSelector(),
            }
        )
        return self.async_show_form(
            step_id="notify",
            data_schema=self.add_suggested_values_to_schema(schema, _nest(self._data)),
        )

    # ------------------------------------------------------------------
    # Reconfigure: change the appliance's sensors after setup
    # ------------------------------------------------------------------
    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        appliance_type = entry.data[CONF_APPLIANCE_TYPE]
        is_ge = entry.data.get(CONF_SOURCE) == SOURCE_GE_HOME and entry.data.get(CONF_SOURCE_DEVICE)
        fields = _entity_fields(appliance_type)

        if user_input is not None:
            data = dict(entry.data)
            for key in fields:
                name = _key_name(key)
                data[name] = user_input.get(name) or None
            if is_ge and user_input.get(REDISCOVER):
                found = async_discover(
                    self.hass, entry.data[CONF_SOURCE_DEVICE], entry.data.get(CONF_OVEN_CAVITY)
                )
                data.update(found.as_config())
                data[CONF_GE_DISCOVERY] = GE_DISCOVERY_VERSION
            return self.async_update_reload_and_abort(entry, data=data)

        schema_fields: dict = {}
        if is_ge:
            schema_fields[vol.Optional(REDISCOVER, default=False)] = selector.BooleanSelector()
        schema_fields.update(fields)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(schema_fields), {k: v for k, v in entry.data.items() if v is not None}
            ),
            description_placeholders={"name": entry.title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ApplianceLiveActivityOptionsFlow()


class ApplianceLiveActivityOptionsFlow(OptionsFlow):
    """Change phones, alerts and appearance after setup."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input = _flatten(user_input)
            # A cleared picker is simply missing from user_input; store None so
            # it doesn't fall back to the value discovered at setup
            for key in CLEARABLE:
                user_input.setdefault(key, None)
            return self.async_create_entry(data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        definition = APPLIANCE_REGISTRY[current[CONF_APPLIANCE_TYPE]]
        schema = _sectioned(
            {
                vol.Required(CONF_DEVICES, default=current.get(CONF_DEVICES, [])): _phones_selector(),
                **_behaviour_fields(
                    current[CONF_APPLIANCE_TYPE],
                    current,
                    bool(current.get(CONF_COOKTOP_ENTITIES)),
                    _temperature_defaults(self.hass),
                ),
                vol.Optional(
                    CONF_ICON, default=current.get(CONF_ICON) or definition.icon
                ): selector.IconSelector(),
                vol.Optional(
                    CONF_ICON_COLOR, default=_current_rgb(current.get(CONF_ICON_COLOR), definition.color)
                ): selector.ColorRGBSelector(),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                _nest(
                    {
                        **current,
                        # Older entries stored a hex string; the color picker needs RGB
                        CONF_ICON_COLOR: _current_rgb(current.get(CONF_ICON_COLOR), definition.color),
                    }
                ),
            ),
        )
