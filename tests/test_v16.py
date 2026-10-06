"""v1.6.0: kitchen timer, meat probe, double ovens, dryer tumble, shared laundry
Live Activity, blocked vent, refill reminders, water filter."""
from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.appliance_live_activity.const import DOMAIN
from custom_components.appliance_live_activity.ge import discover_from_entity_ids, oven_cavities
from custom_components.appliance_live_activity.maintenance import supply_low


async def _ge_device(hass, ge, uid, name, states: dict[str, tuple[str, dict]]):
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=ge.entry_id, identifiers={("ge_home", uid)}, name=name
    )
    for eid, (state, attrs) in states.items():
        domain, obj = eid.split(".")
        ent_reg.async_get_or_create(domain, "ge_home", obj, suggested_object_id=obj,
                                    device_id=device.id, config_entry=ge)
        hass.states.async_set(eid, state, attrs)
    return device


@pytest.fixture
async def phone(hass: HomeAssistant, enable_custom_integrations):
    entry = MockConfigEntry(domain="mobile_app")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mobile_app", "p")}, name="My Phone"
    )
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    return device, ge, async_mock_service(hass, "notify", "mobile_app_my_phone")


async def _start(hass, device_id):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "ge_home"})
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"source_device": device_id})


async def _setup(hass, device_id, notify_input):
    result = await _start(hass, device_id)
    assert result["step_id"] == "notify", result
    result = await hass.config_entries.flow.async_configure(result["flow_id"], notify_input)
    await hass.async_block_till_done()
    assert result["type"] == "create_entry", result
    return result


async def _tick(hass, freezer, delta):
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _live(calls, tag=None):
    return [
        c for c in calls
        if c.data.get("data", {}).get("live_update") and (tag is None or c.data["data"]["tag"] == tag)
    ]


def _titled(calls, start):
    return [c for c in calls if str(c.data.get("title", "")).startswith(start)]


def _cleared(calls):
    return [c.data["data"]["tag"] for c in calls if c.data.get("message") == "clear_notification"]


# ---------------------------------------------------------------- discovery
DOUBLE_OVEN = [
    "sensor.kitchen_oven_upper_oven_current_state",
    "sensor.kitchen_oven_upper_oven_cook_mode",
    "sensor.kitchen_oven_upper_oven_cook_time_remaining",
    "sensor.kitchen_oven_upper_oven_kitchen_timer",
    "sensor.kitchen_oven_upper_oven_probe_display_temp",
    "sensor.kitchen_oven_lower_oven_current_state",
    "sensor.kitchen_oven_lower_oven_cook_mode",
    "sensor.kitchen_oven_lower_oven_cook_time_remaining",
    "sensor.kitchen_oven_lower_oven_kitchen_timer",
    "binary_sensor.kitchen_oven_cooktop_status",
]


def test_discovery():
    assert oven_cavities(DOUBLE_OVEN) == ["upper", "lower"]
    upper = discover_from_entity_ids(DOUBLE_OVEN, "upper")
    assert upper.state_entity == "sensor.kitchen_oven_upper_oven_current_state"
    assert upper.timer_entity == "sensor.kitchen_oven_upper_oven_kitchen_timer"
    assert upper.probe_entity == "sensor.kitchen_oven_upper_oven_probe_display_temp"
    assert upper.cooktop_entities == ["binary_sensor.kitchen_oven_cooktop_status"]
    lower = discover_from_entity_ids(DOUBLE_OVEN, "lower")
    assert lower.state_entity == "sensor.kitchen_oven_lower_oven_current_state"
    assert lower.remaining_entity == "sensor.kitchen_oven_lower_oven_cook_time_remaining"
    assert lower.timer_entity == "sensor.kitchen_oven_lower_oven_kitchen_timer"
    assert lower.probe_entity is None and lower.cooktop_entities == []

    single = discover_from_entity_ids(list(OVEN))
    assert single.cavities == [] and single.cavity is None
    assert single.timer_entity == "sensor.kitchen_oven_kitchen_timer"

    dryer = discover_from_entity_ids(list(DRYER))
    assert dryer.tumble_entity == "sensor.laundry_room_dryer_tumble_status"
    assert dryer.vent_entity == "binary_sensor.laundry_room_dryer_blocked_vent_fault"
    assert dryer.supply_entities == ["sensor.laundry_room_dryer_sheet_inventory"]

    washer = discover_from_entity_ids(list(WASHER))
    assert washer.supply_entities == ["sensor.laundry_room_washer_smart_dispense_loads_left"]

    dw = discover_from_entity_ids([
        "sensor.kitchen_dishwasher_operating_mode",
        "number.kitchen_dishwasher_pods_remaining_value",
        "sensor.kitchen_dishwasher_add_rinse_aid",
    ])
    assert dw.supply_entities == [
        "number.kitchen_dishwasher_pods_remaining_value",
        "sensor.kitchen_dishwasher_add_rinse_aid",
    ]

    fridge = discover_from_entity_ids([
        "binary_sensor.kitchen_refrigerator_freezer_door",
        "sensor.kitchen_refrigerator_water_filter_status",
    ])
    assert fridge.filter_entity == "sensor.kitchen_refrigerator_water_filter_status"


def test_supply_low():
    assert supply_low("2", "loads", 3) is True
    assert supply_low("8", "loads", 3) is False
    assert supply_low("20", "%", 3) is True
    assert supply_low("50", "%", 3) is False
    assert supply_low("Low", None, 3) is True
    assert supply_low("Full", None, 3) is False
    assert supply_low("unavailable", None, 3) is None


# ---------------------------------------------------------------- oven
OVEN = {
    "sensor.kitchen_oven_current_state": ("Off", {}),
    "sensor.kitchen_oven_cook_mode": ("Off", {}),
    "sensor.kitchen_oven_cook_time_remaining": ("0.0", {"unit_of_measurement": "h"}),
    "sensor.kitchen_oven_kitchen_timer": ("0", {"unit_of_measurement": "min"}),
    "sensor.kitchen_oven_probe_display_temp": ("0", {"unit_of_measurement": "°F"}),
}


async def _oven(hass, phone):
    me, ge, calls = phone
    oven = await _ge_device(hass, ge, "oven", "Kitchen Oven", OVEN)
    result = await _setup(hass, oven.id, {"devices": [me.id]})
    assert result["data"]["timer_entity"] == "sensor.kitchen_oven_kitchen_timer"
    assert result["data"]["probe_entity"] == "sensor.kitchen_oven_probe_display_temp"
    return calls


def _timer(hass, minutes):
    hass.states.async_set("sensor.kitchen_oven_kitchen_timer", str(minutes), {"unit_of_measurement": "min"})


async def test_kitchen_timer(hass: HomeAssistant, phone, freezer):
    calls = await _oven(hass, phone)
    _timer(hass, 10)
    await hass.async_block_till_done()
    live = _live(calls, "kitchen_oven_timer")
    assert len(live) == 1
    assert live[0].data["data"]["when"] == 600
    assert live[0].data["title"] == "Kitchen Oven timer"

    # Counting down with the clock: no more pushes
    for left in range(9, 0, -1):
        await _tick(hass, freezer, timedelta(minutes=1))
        _timer(hass, left)
        await hass.async_block_till_done()
    assert len(_live(calls, "kitchen_oven_timer")) == 1
    assert hass.states.get("sensor.kitchen_oven_status").attributes["kitchen_timer_minutes"] == 1

    await _tick(hass, freezer, timedelta(minutes=1))
    _timer(hass, 0)
    await hass.async_block_till_done()
    assert "kitchen_oven_timer" in _cleared(calls)
    assert len(_titled(calls, "⏰ Kitchen Oven timer done")) == 1


async def test_kitchen_timer_cancelled(hass: HomeAssistant, phone, freezer):
    calls = await _oven(hass, phone)
    _timer(hass, 30)
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(minutes=2))
    _timer(hass, 0)
    await hass.async_block_till_done()
    assert "kitchen_oven_timer" in _cleared(calls)
    assert _titled(calls, "⏰") == []


def _probe(hass, temp):
    hass.states.async_set("sensor.kitchen_oven_probe_display_temp", str(temp), {"unit_of_measurement": "°F"})


async def test_probe(hass: HomeAssistant, phone, freezer):
    calls = await _oven(hass, phone)
    number = "number.kitchen_oven_probe_target"
    assert hass.states.get(number) is not None

    # No target yet: shows the temperature, every 5 degrees
    _probe(hass, 60)
    await hass.async_block_till_done()
    live = _live(calls, "kitchen_oven_probe")
    assert len(live) == 1 and live[0].data["message"] == "Probe 60°F"
    _probe(hass, 62)
    await hass.async_block_till_done()
    assert len(_live(calls, "kitchen_oven_probe")) == 1

    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 145}, blocking=True)
    await hass.async_block_till_done()
    live = _live(calls, "kitchen_oven_probe")
    assert live[-1].data["message"] == "Probe 62°F → 145°F"
    assert "progress" in live[-1].data["data"]

    for t in range(70, 145, 3):
        _probe(hass, t)
        await hass.async_block_till_done()
    assert len(_live(calls, "kitchen_oven_probe")) <= 12
    assert _titled(calls, "🍖") == []

    _probe(hass, 146)
    await hass.async_block_till_done()
    alerts = _titled(calls, "🍖 Kitchen Oven: probe at 146°F")
    assert len(alerts) == 1 and "145°F" in alerts[0].data["message"]
    assert _live(calls, "kitchen_oven_probe")[-1].data["data"]["critical_text"] == "Ready"
    _probe(hass, 150)
    await hass.async_block_till_done()
    assert len(_titled(calls, "🍖")) == 1
    attrs = hass.states.get("sensor.kitchen_oven_status").attributes
    assert attrs["probe_temperature"] == 150 and attrs["probe_target"] == 145

    # Unplugged
    _probe(hass, 0)
    await hass.async_block_till_done()
    assert "kitchen_oven_probe" in _cleared(calls)
    assert "kitchen_oven_probe_done" in _cleared(calls)


async def test_double_oven_setup(hass: HomeAssistant, phone):
    me, ge, calls = phone
    states = {e: ("Off", {}) for e in DOUBLE_OVEN}
    oven = await _ge_device(hass, ge, "oven2", "Kitchen Oven", states)

    result = await _start(hass, oven.id)
    assert result["step_id"] == "oven_cavity"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"oven_cavity": "upper"})
    assert result["step_id"] == "notify"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"devices": [me.id]})
    await hass.async_block_till_done()
    assert result["title"] == "Kitchen Oven Upper"
    assert result["data"]["state_entity"] == "sensor.kitchen_oven_upper_oven_current_state"

    # Second time only the lower oven is offered
    result = await _start(hass, oven.id)
    assert result["step_id"] == "oven_cavity"
    options = result["data_schema"].schema["oven_cavity"].config["options"]
    assert [o["value"] for o in options] == ["lower"]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"oven_cavity": "lower"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"devices": [me.id]})
    await hass.async_block_till_done()
    assert result["title"] == "Kitchen Oven Lower"
    assert result["data"]["timer_entity"] == "sensor.kitchen_oven_lower_oven_kitchen_timer"
    assert "cooktop_entities" not in result["data"]

    result = await _start(hass, oven.id)
    assert result["type"] == "abort"


# ---------------------------------------------------------------- laundry
WASHER = {
    "sensor.laundry_room_washer_state": ("Off", {}),
    "sensor.laundry_room_washer_sub_cycle": ("---", {}),
    "sensor.laundry_room_washer_cycle": ("Normal", {}),
    "sensor.laundry_room_washer_time_remaining": ("0", {"unit_of_measurement": "min"}),
    "binary_sensor.laundry_room_washer_end_of_cycle": ("off", {}),
    "binary_sensor.laundry_room_washer_door": ("off", {"device_class": "door"}),
    "sensor.laundry_room_washer_smart_dispense_loads_left": ("2", {"unit_of_measurement": "loads"}),
}
DRYER = {
    "sensor.laundry_room_dryer_state": ("Off", {}),
    "sensor.laundry_room_dryer_sub_cycle": ("---", {}),
    "sensor.laundry_room_dryer_dryness_new_level": ("More Dry", {}),
    "sensor.laundry_room_dryer_time_remaining": ("0", {"unit_of_measurement": "min"}),
    "binary_sensor.laundry_room_dryer_end_of_cycle": ("off", {}),
    "binary_sensor.laundry_room_dryer_door": ("off", {"device_class": "door"}),
    "sensor.laundry_room_dryer_tumble_status": ("Enable", {}),
    "binary_sensor.laundry_room_dryer_blocked_vent_fault": ("off", {}),
    "sensor.laundry_room_dryer_sheet_inventory": ("20", {"unit_of_measurement": "sheets"}),
}


def _set(hass, entity, state, attrs=None):
    hass.states.async_set(entity, state, attrs or {})


async def _run(hass, prefix, minutes=40):
    _set(hass, f"sensor.{prefix}_time_remaining", str(minutes), {"unit_of_measurement": "min"})
    _set(hass, f"binary_sensor.{prefix}_end_of_cycle", "off")
    _set(hass, f"sensor.{prefix}_state", "Run")
    await hass.async_block_till_done()


async def _finish(hass, prefix, sub_cycle="---"):
    _set(hass, f"sensor.{prefix}_time_remaining", "0", {"unit_of_measurement": "min"})
    _set(hass, f"sensor.{prefix}_sub_cycle", sub_cycle)
    _set(hass, f"binary_sensor.{prefix}_end_of_cycle", "on")
    _set(hass, f"sensor.{prefix}_state", "Finished")
    await hass.async_block_till_done()


async def _dryer_only(hass, phone, **extra):
    me, ge, calls = phone
    dryer = await _ge_device(hass, ge, "dryer", "Laundry Room Dryer", DRYER)
    result = await _setup(hass, dryer.id, {"devices": [me.id], "dismiss_minutes": 30, **extra})
    assert result["data"]["tumble_entity"] == "sensor.laundry_room_dryer_tumble_status"
    return calls


async def test_dryer_extended_tumble(hass: HomeAssistant, phone, freezer):
    calls = await _dryer_only(hass, phone)
    await _run(hass, "laundry_room_dryer")
    # GE: cycle over, the drum tumbles now and then
    _set(hass, "sensor.laundry_room_dryer_time_remaining", "0", {"unit_of_measurement": "min"})
    _set(hass, "sensor.laundry_room_dryer_sub_cycle", "Extended Tumble")
    await hass.async_block_till_done()
    done = _live(calls)[-1]
    assert done.data["data"]["critical_text"] == "Done"
    assert "tumbling to prevent wrinkles" in done.data["message"]

    # Not dismissed while still tumbling
    await _tick(hass, freezer, timedelta(minutes=45))
    assert "laundry_room_dryer" not in _cleared(calls)
    # Door opens -> dismissed
    _set(hass, "binary_sensor.laundry_room_dryer_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    assert "laundry_room_dryer" in _cleared(calls)


async def test_dryer_no_tumble_dismisses(hass: HomeAssistant, phone, freezer):
    calls = await _dryer_only(hass, phone)
    _set(hass, "sensor.laundry_room_dryer_tumble_status", "Disable")
    await _run(hass, "laundry_room_dryer")
    await _finish(hass, "laundry_room_dryer")
    assert "tumbling" not in _live(calls)[-1].data["message"]
    await _tick(hass, freezer, timedelta(minutes=31))
    assert "laundry_room_dryer" in _cleared(calls)


async def test_dryer_tumble_setting_until_off(hass: HomeAssistant, phone, freezer):
    """Tumble option on: 'Done · tumbling' until the dryer stops, then the normal delay."""
    calls = await _dryer_only(hass, phone)
    await _run(hass, "laundry_room_dryer")
    await _finish(hass, "laundry_room_dryer")
    assert "tumbling" in _live(calls)[-1].data["message"]
    await _tick(hass, freezer, timedelta(minutes=31))
    assert "laundry_room_dryer" not in _cleared(calls)
    _set(hass, "sensor.laundry_room_dryer_state", "Off")
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(minutes=31))
    assert "laundry_room_dryer" in _cleared(calls)


async def test_blocked_vent(hass: HomeAssistant, phone, freezer):
    calls = await _dryer_only(hass, phone, vent_entity="binary_sensor.laundry_room_dryer_blocked_vent_fault")
    _set(hass, "binary_sensor.laundry_room_dryer_blocked_vent_fault", "on")
    await hass.async_block_till_done()
    alerts = _titled(calls, "🔥 Laundry Room Dryer: vent blocked")
    assert len(alerts) == 1
    assert alerts[0].data["data"]["push"]["interruption-level"] == "critical"
    await _tick(hass, freezer, timedelta(minutes=10))
    assert len(_titled(calls, "🔥")) == 1
    await _tick(hass, freezer, timedelta(minutes=21))
    assert len(_titled(calls, "🔥")) == 2
    _set(hass, "binary_sensor.laundry_room_dryer_blocked_vent_fault", "off")
    await hass.async_block_till_done()
    assert "laundry_room_dryer_vent" in _cleared(calls)
    assert hass.states.get("sensor.laundry_room_dryer_status").attributes["vent_blocked"] is False


async def _laundry_pair(hass, phone, combine=True):
    me, ge, calls = phone
    dryer = await _ge_device(hass, ge, "dryer", "Laundry Room Dryer", DRYER)
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    await _setup(hass, dryer.id, {"devices": [me.id]})
    await _setup(hass, washer.id, {
        "devices": [me.id], "dryer_entity": "sensor.laundry_room_dryer_state",
        "combine_laundry": combine,
        "supply_entities": ["sensor.laundry_room_washer_smart_dispense_loads_left"],
    })
    return calls


async def test_shared_laundry_activity(hass: HomeAssistant, phone, freezer):
    calls = await _laundry_pair(hass, phone)
    await _run(hass, "laundry_room_washer")
    await _finish(hass, "laundry_room_washer")
    done = _live(calls)[-1]
    assert done.data["title"] == "Laundry"
    assert done.data["data"]["tag"] == "laundry_room_washer"
    assert "move to the dryer" in done.data["message"]

    # Moving the laundry (washer door) keeps the shared activity up
    _set(hass, "binary_sensor.laundry_room_washer_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    assert "laundry_room_washer" not in _cleared(calls)

    # The dryer takes over the same Live Activity
    await _run(hass, "laundry_room_dryer", 60)
    drying = _live(calls)[-1]
    assert drying.data["data"]["tag"] == "laundry_room_washer"
    assert drying.data["title"] == "Laundry"
    assert drying.data["data"]["when"] == 3600

    # The washer's dismiss timer must not end the dryer's activity
    await _tick(hass, freezer, timedelta(minutes=31))
    assert "laundry_room_washer" not in _cleared(calls)

    await _finish(hass, "laundry_room_dryer")
    _set(hass, "binary_sensor.laundry_room_dryer_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    assert "laundry_room_washer" in _cleared(calls)
    assert "laundry_room_dryer" not in _cleared(calls)


async def test_separate_laundry_activities(hass: HomeAssistant, phone, freezer):
    calls = await _laundry_pair(hass, phone, combine=False)
    await _run(hass, "laundry_room_dryer")
    assert _live(calls)[-1].data["data"]["tag"] == "laundry_room_dryer"
    assert _live(calls)[-1].data["title"] == "Laundry Room Dryer"


async def test_refill_reminder(hass: HomeAssistant, phone, freezer):
    calls = await _laundry_pair(hass, phone)
    await _run(hass, "laundry_room_washer")
    await _finish(hass, "laundry_room_washer")
    refill = _titled(calls, "🧴 Laundry Room Washer: time to refill")
    assert len(refill) == 1
    assert refill[0].data["message"] == "Detergent: 2 loads left"

    # Next load: not mentioned again until it's refilled
    _set(hass, "binary_sensor.laundry_room_washer_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    await _run(hass, "laundry_room_washer")
    await _finish(hass, "laundry_room_washer")
    assert len(_titled(calls, "🧴")) == 1

    _set(hass, "sensor.laundry_room_washer_smart_dispense_loads_left", "30", {"unit_of_measurement": "loads"})
    await _tick(hass, freezer, timedelta(minutes=2))
    _set(hass, "sensor.laundry_room_washer_smart_dispense_loads_left", "3", {"unit_of_measurement": "loads"})
    await _tick(hass, freezer, timedelta(minutes=2))
    await _run(hass, "laundry_room_washer")
    await _finish(hass, "laundry_room_washer")
    assert len(_titled(calls, "🧴")) == 2


# ---------------------------------------------------------------- fridge
async def test_water_filter(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    fridge = await _ge_device(hass, ge, "fridge", "Kitchen Refrigerator", {
        "binary_sensor.kitchen_refrigerator_freezer_door": ("off", {"device_class": "door"}),
        "sensor.kitchen_refrigerator_water_filter_status": ("Good", {}),
    })
    await _setup(hass, fridge.id, {
        "devices": [me.id], "filter_entity": "sensor.kitchen_refrigerator_water_filter_status",
    })
    _set(hass, "sensor.kitchen_refrigerator_water_filter_status", "Replace")
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(minutes=5))
    assert len(_titled(calls, "🚰 Kitchen Refrigerator: replace the water filter")) == 1
    _set(hass, "sensor.kitchen_refrigerator_water_filter_status", "Leak Detected")
    await hass.async_block_till_done()
    leak = _titled(calls, "💧 Kitchen Refrigerator: water filter leak")
    assert leak[0].data["data"]["push"]["interruption-level"] == "critical"
    _set(hass, "sensor.kitchen_refrigerator_water_filter_status", "Good")
    await hass.async_block_till_done()
    assert "kitchen_refrigerator_filter" in _cleared(calls)


async def test_existing_entry_backfills_v16(hass: HomeAssistant, phone):
    me, ge, calls = phone
    oven = await _ge_device(hass, ge, "oven", "Kitchen Oven", OVEN)
    # As created by 1.5.0 (delay key present, no discovery version)
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "ge_home", "source_device": oven.id, "appliance_type": "oven",
        "name": "Kitchen Oven", "state_entity": "sensor.kitchen_oven_current_state",
        "notification_tag": "kitchen_oven", "devices": [me.id], "delay_entity": None,
    }, options={"probe_entity": None})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.data["timer_entity"] == "sensor.kitchen_oven_kitchen_timer"
    assert "probe_entity" not in entry.data  # cleared in Configure: left alone
    assert entry.data["ge_discovery"] == 3
