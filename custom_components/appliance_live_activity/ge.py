"""GE Home Appliances (SmartHQ) profile.

Finds the right entities on a ``ge_home`` device so users only pick the
appliance, not six sensors. ha_gehome names entities
``<device prefix>_<measurement>``, e.g. ``sensor.laundry_room_washer_state``,
``sensor.kitchen_dishwasher_operating_mode``, so suffix matching works for
both friendly-named and serial-named devices.

"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_COOKTOP_ENTITIES,
    CONF_CYCLE_ENTITY,
    CONF_DONE_ENTITY,
    CONF_DOOR_ENTITIES,
    CONF_DOOR_ENTITY,
    CONF_PHASE_ENTITY,
    CONF_REMAINING_ENTITY,
    CONF_STATE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    GE_HOME_DOMAIN,
)


@dataclass
class GEDiscovery:
    """Entities found on a GE appliance device."""

    appliance_type: str | None
    state_entity: str | None = None
    phase_entity: str | None = None
    cycle_entity: str | None = None
    remaining_entity: str | None = None
    done_entity: str | None = None
    door_entity: str | None = None
    temperature_entity: str | None = None
    door_entities: list[str] = field(default_factory=list)
    cooktop_entities: list[str] = field(default_factory=list)

    def as_config(self) -> dict[str, str]:
        """Config-entry keys for every entity that was found."""
        mapping = {
            CONF_STATE_ENTITY: self.state_entity,
            CONF_PHASE_ENTITY: self.phase_entity,
            CONF_CYCLE_ENTITY: self.cycle_entity,
            CONF_REMAINING_ENTITY: self.remaining_entity,
            CONF_DONE_ENTITY: self.done_entity,
            CONF_DOOR_ENTITY: self.door_entity,
            CONF_TEMPERATURE_ENTITY: self.temperature_entity,
        }
        result = {k: v for k, v in mapping.items() if v}
        if self.door_entities:
            result[CONF_DOOR_ENTITIES] = list(self.door_entities)
        if self.cooktop_entities:
            result[CONF_COOKTOP_ENTITIES] = list(self.cooktop_entities)
        return result


def _first(entity_ids: list[str], pattern: str, exclude: str | None = None) -> str | None:
    for entity_id in entity_ids:
        if re.search(pattern, entity_id) and not (exclude and re.search(exclude, entity_id)):
            return entity_id
    return None


def discover_from_entity_ids(entity_ids: list[str]) -> GEDiscovery:
    """Pure discovery logic (no Home Assistant objects) so it can be unit tested."""
    ids = sorted(entity_ids)

    def has(pattern: str) -> bool:
        return any(re.search(pattern, e) for e in ids)

    if has(r"^sensor\..*_operating_mode$"):
        appliance_type = "dishwasher"
    elif has(r"^sensor\..*_sub_cycle$"):
        appliance_type = "dryer" if has(r"_(dryness|tumble|sheet_)") else "washer"
    elif has(r"^sensor\..*_cook_mode$") or has(r"^sensor\..*_current_state$"):
        appliance_type = "oven"
    elif has(r"_(freezer_door|ice_bucket|water_filter)"):
        appliance_type = "refrigerator"
    else:
        appliance_type = None

    if appliance_type == "refrigerator":
        # Every door: fridge (single or left/right) and freezer
        doors = [e for e in ids if re.search(r"^binary_sensor\..*_door$", e)]
        return GEDiscovery(
            appliance_type=appliance_type,
            state_entity=doors[0] if doors else None,
            door_entities=doors,
        )

    state = (
        _first(ids, r"^sensor\..*_operating_mode$")
        or _first(ids, r"^sensor\..*_current_state$")
        or _first(ids, r"^sensor\..*_state$", r"_(cycle|current)_state$")
    )
    phase = (
        _first(ids, r"^sensor\..*_sub_cycle$")
        or _first(ids, r"^sensor\..*_cook_mode$")
        or _first(ids, r"^sensor\..*_cycle_state$")
    )
    cycle = _first(ids, r"^sensor\..*_cycle_name$") or _first(
        ids, r"^sensor\..*_cycle$", r"_sub_cycle$"
    )
    remaining = _first(ids, r"^sensor\..*_cook_time_remaining$") or _first(
        ids, r"^sensor\..*_time_remaining$", r"_(delay|cook)_time_remaining$"
    )
    return GEDiscovery(
        appliance_type=appliance_type,
        state_entity=state,
        phase_entity=phase,
        cycle_entity=cycle,
        remaining_entity=remaining,
        done_entity=_first(ids, r"^binary_sensor\..*_end_of_cycle$"),
        door_entity=_first(ids, r"^binary_sensor\..*_door$"),
        temperature_entity=_first(ids, r"^sensor\..*_display_temperature$"),
        cooktop_entities=[e for e in ids if re.search(r"^binary_sensor\..*_cooktop_status$", e)],
    )


def async_discover(hass: HomeAssistant, device_id: str) -> GEDiscovery:
    """Discover entities for a ge_home device from the entity registry."""
    ent_reg = er.async_get(hass)
    entity_ids = [
        entry.entity_id
        for entry in er.async_entries_for_device(ent_reg, device_id)
        if not entry.disabled_by
    ]
    return discover_from_entity_ids(entity_ids)


def async_has_ge_devices(hass: HomeAssistant) -> bool:
    """True if the GE Home integration has at least one device."""
    entries = hass.config_entries.async_entries(GE_HOME_DOMAIN)
    if not entries:
        return False
    dev_reg = dr.async_get(hass)
    return any(dr.async_entries_for_config_entry(dev_reg, entry.entry_id) for entry in entries)


def device_name(hass: HomeAssistant, device_id: str) -> str | None:
    """User-facing name of a device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    return device.name_by_user or device.name
