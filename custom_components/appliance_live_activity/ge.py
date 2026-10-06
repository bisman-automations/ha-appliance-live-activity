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
    CONF_DELAY_ENTITY,
    CONF_DONE_ENTITY,
    CONF_DOOR_ENTITIES,
    CONF_DOOR_ENTITY,
    CONF_DRYER_ENTITY,
    CONF_DRYER_START_ENTITY,
    CONF_FILTER_ENTITY,
    CONF_OVEN_CAVITY,
    CONF_PROBE_ENTITY,
    CONF_SUPPLY_ENTITIES,
    CONF_TIMER_ENTITY,
    CONF_TUMBLE_ENTITY,
    CONF_VENT_ENTITY,
    CONF_LEAK_ENTITIES,
    CONF_PHASE_ENTITY,
    CONF_REMAINING_ENTITY,
    CONF_STATE_ENTITY,
    CONF_TARGET_TEMPERATURE_ENTITY,
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
    target_temperature_entity: str | None = None
    leak_entities: list[str] = field(default_factory=list)
    dryer_entity: str | None = None
    dryer_start_entity: str | None = None
    delay_entity: str | None = None
    start_button: str | None = None
    timer_entity: str | None = None
    probe_entity: str | None = None
    tumble_entity: str | None = None
    vent_entity: str | None = None
    filter_entity: str | None = None
    supply_entities: list[str] = field(default_factory=list)
    # Double ovens: ["upper", "lower"] (set up one entry per oven)
    cavities: list[str] = field(default_factory=list)
    cavity: str | None = None
    prefix: str = ""

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
            CONF_TARGET_TEMPERATURE_ENTITY: self.target_temperature_entity,
            CONF_DRYER_ENTITY: self.dryer_entity,
            CONF_DRYER_START_ENTITY: self.dryer_start_entity,
            CONF_DELAY_ENTITY: self.delay_entity,
            CONF_TIMER_ENTITY: self.timer_entity,
            CONF_PROBE_ENTITY: self.probe_entity,
            CONF_TUMBLE_ENTITY: self.tumble_entity,
            CONF_VENT_ENTITY: self.vent_entity,
            CONF_FILTER_ENTITY: self.filter_entity,
            CONF_OVEN_CAVITY: self.cavity,
        }
        result = {k: v for k, v in mapping.items() if v}
        if self.door_entities:
            result[CONF_DOOR_ENTITIES] = list(self.door_entities)
        if self.cooktop_entities:
            result[CONF_COOKTOP_ENTITIES] = list(self.cooktop_entities)
        if self.leak_entities:
            result[CONF_LEAK_ENTITIES] = list(self.leak_entities)
        if self.supply_entities:
            result[CONF_SUPPLY_ENTITIES] = list(self.supply_entities)
        return result


def _first(entity_ids: list[str], pattern: str, exclude: str | None = None) -> str | None:
    for entity_id in entity_ids:
        if re.search(pattern, entity_id) and not (exclude and re.search(exclude, entity_id)):
            return entity_id
    return None


CAVITIES = ("upper", "lower")


def oven_cavities(entity_ids: list[str]) -> list[str]:
    """['upper', 'lower'] for a GE double oven, else []."""
    found = [
        cavity
        for cavity in CAVITIES
        if any(re.search(rf"^sensor\..*{cavity}_oven_current_state$", e) for e in entity_ids)
    ]
    return found if len(found) == 2 else []


def discover_from_entity_ids(entity_ids: list[str], cavity: str | None = None) -> GEDiscovery:
    """Pure discovery logic (no Home Assistant objects) so it can be unit tested.

    ``cavity`` picks one oven of a double oven ("upper" / "lower").
    """
    ids = sorted(entity_ids)
    cavities = oven_cavities(ids)
    if cavities:
        cavity = cavity if cavity in cavities else cavities[0]
        other = next(c for c in cavities if c != cavity)
        # The other oven's entities -- and, for the lower oven, the cooktop
        # (it belongs to the range, alerted once by the upper oven's entry)
        ids = [
            e
            for e in ids
            if f"{other}_oven_" not in e
            and not (cavity == "lower" and e.endswith("_cooktop_status"))
        ]
    else:
        cavity = None

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
            filter_entity=_first(ids, r"^sensor\..*water_filter_status$"),
            prefix=entity_prefix(ids),
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
        target_temperature_entity=_first(ids, r"^water_heater\..*_set_temperature$"),
        # Washer / dryer / oven count down; GE dishwashers only report the
        # chosen delay (hours)
        delay_entity=_first(ids, r"^sensor\..*_delay_time_remaining$")
        or _first(ids, r"^sensor\..*_delay_hours$"),
        start_button=_first(ids, r"^button\..*_start_cycle$"),
        timer_entity=_first(ids, r"^sensor\..*_kitchen_timer$"),
        probe_entity=_first(ids, r"^sensor\..*_probe_display_temp$"),
        tumble_entity=_first(ids, r"^sensor\..*_tumble_status$"),
        vent_entity=_first(ids, r"^binary_sensor\..*_blocked_vent(_fault)?$"),
        supply_entities=_supplies(ids, appliance_type),
        # GE dishwashers: "Reminders Clean Filter"
        filter_entity=_first(ids, r"^sensor\..*_clean_filter$") if appliance_type == "dishwasher" else None,
        cavities=cavities,
        cavity=cavity,
        prefix=entity_prefix(ids),
    )


def _supplies(ids: list[str], appliance_type: str | None) -> list[str]:
    """Detergent, pods, rinse aid and dryer-sheet sensors for refill reminders."""
    patterns = {
        "washer": [r"^sensor\..*_smart_dispense_loads_left$", r"^sensor\..*_tank_status$"],
        "dishwasher": [r"^(number|sensor)\..*_pods_remaining(_value)?$", r"^sensor\..*_add_rinse_aid$"],
        "dryer": [r"^(number|sensor)\..*_sheet_inventory$"],
    }.get(appliance_type or "", [])
    found: list[str] = []
    for pattern in patterns:
        match = _first(ids, pattern)
        if match and match not in found:
            found.append(match)
    if appliance_type == "washer" and len(found) > 1:
        # Loads left is the better signal when the washer has both
        found = found[:1]
    return found


def entity_prefix(entity_ids: list[str]) -> str:
    """Common object-id prefix of a device's entities, e.g. 'kitchen_dishwasher_'."""
    objects = [e.split(".", 1)[1] for e in entity_ids if "." in e]
    if not objects:
        return ""
    prefix = objects[0]
    for obj in objects[1:]:
        while not obj.startswith(prefix):
            prefix = prefix[:-1]
    cut = prefix.rfind("_")
    return prefix[: cut + 1] if cut > 0 else ""


def leak_sensors_for_prefix(states: list[tuple[str, str | None]], prefix: str) -> list[str]:
    """Moisture sensors named after the appliance, e.g. a SwitchBot sensor called
    'Kitchen Dishwasher Leak Sensor' -> binary_sensor.kitchen_dishwasher_leak_sensor_water_leak.

    ``states`` is a list of (entity_id, device_class).
    """
    if not prefix:
        return []
    return sorted(
        entity_id
        for entity_id, device_class in states
        if entity_id.startswith(f"binary_sensor.{prefix}") and device_class == "moisture"
    )


def async_discover(hass: HomeAssistant, device_id: str, cavity: str | None = None) -> GEDiscovery:
    """Discover entities for a ge_home device from the entity registry."""
    ent_reg = er.async_get(hass)
    entity_ids = [
        entry.entity_id
        for entry in er.async_entries_for_device(ent_reg, device_id)
        if not entry.disabled_by
    ]
    found = discover_from_entity_ids(entity_ids, cavity)

    # Leak sensors live on their own (non-GE) device, so match them by name
    moisture = [
        (state.entity_id, state.attributes.get("device_class"))
        for state in hass.states.async_all("binary_sensor")
    ]
    found.leak_entities = leak_sensors_for_prefix(moisture, found.prefix)

    # Washer: stop the "move the laundry" reminder when the GE dryer starts
    if found.appliance_type == "washer":
        dryer = async_find_ge_appliance(hass, "dryer")
        if dryer is not None:
            found.dryer_entity = dryer.state_entity
            found.dryer_start_entity = dryer.start_button
    return found


def async_find_ge_appliance(hass: HomeAssistant, appliance_type: str) -> GEDiscovery | None:
    """Entities of the first GE appliance of this type (e.g. the dryer)."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    for entry in hass.config_entries.async_entries(GE_HOME_DOMAIN):
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
            ids = [e.entity_id for e in er.async_entries_for_device(ent_reg, device.id)]
            found = discover_from_entity_ids(ids)
            if found.appliance_type == appliance_type and found.state_entity:
                return found
    return None


def async_find_ge_state_entity(hass: HomeAssistant, appliance_type: str) -> str | None:
    """State sensor of the first GE appliance of this type (e.g. the dryer)."""
    found = async_find_ge_appliance(hass, appliance_type)
    return found.state_entity if found else None


def async_remote_status_entity(hass: HomeAssistant, entity_id: str) -> str | None:
    """The 'remote start enabled' sensor on the same device as ``entity_id``
    (GE: binary_sensor.<dryer>_remote_status)."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if entry is None or entry.device_id is None:
        return None
    for other in er.async_entries_for_device(ent_reg, entry.device_id):
        if re.search(r"^binary_sensor\..*_remote_(status|enable|enabled)$", other.entity_id):
            return other.entity_id
    return None


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
