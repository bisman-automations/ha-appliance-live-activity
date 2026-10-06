"""v1.4.0: oven preheat, water leak alerts, washer -> dryer reminder."""
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
from custom_components.appliance_live_activity.ge import entity_prefix, leak_sensors_for_prefix


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


async def _setup(hass, device_id, notify_input):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "ge_home"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source_device": device_id})
    assert result["step_id"] == "notify", result
    suggested = {
        str(k): k.description.get("suggested_value")
        for k in result["data_schema"].schema
        if getattr(k, "description", None)
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], notify_input)
    await hass.async_block_till_done()
    return result, suggested


async def _tick(hass, freezer, delta):
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _titled(calls, start):
    return [c for c in calls if str(c.data.get("title", "")).startswith(start)]


# ---------------------------------------------------------------- pure
def test_prefix_and_leak_matching():
    assert entity_prefix(["sensor.kitchen_dishwasher_operating_mode",
                          "binary_sensor.kitchen_dishwasher_door"]) == "kitchen_dishwasher_"
    states = [
        ("binary_sensor.kitchen_dishwasher_leak_sensor_water_leak", "moisture"),
        ("binary_sensor.kitchen_refrigerator_leak_sensor_water_leak", "moisture"),
        ("binary_sensor.kitchen_dishwasher_door", "opening"),
    ]
    assert leak_sensors_for_prefix(states, "kitchen_dishwasher_") == [
        "binary_sensor.kitchen_dishwasher_leak_sensor_water_leak"
    ]


# ---------------------------------------------------------------- oven
OVEN = {
    "sensor.kitchen_oven_current_state": ("Off", {}),
    "sensor.kitchen_oven_cook_mode": ("Off", {}),
    "sensor.kitchen_oven_cook_time_remaining": ("0.0", {"unit_of_measurement": "h"}),
    "sensor.kitchen_oven_display_temperature": ("0", {"unit_of_measurement": "°F"}),
    "water_heater.kitchen_oven_set_temperature": ("off", {"temperature": 0}),
}


async def test_oven_preheat(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    oven = await _ge_device(hass, ge, "oven", "Kitchen Oven", OVEN)
    result, _ = await _setup(hass, oven.id, {"devices": [me.id]})
    assert result["data"]["target_temperature_entity"] == "water_heater.kitchen_oven_set_temperature"

    hass.states.async_set("water_heater.kitchen_oven_set_temperature", "Bake", {"temperature": 350})
    hass.states.async_set("sensor.kitchen_oven_display_temperature", "100", {"unit_of_measurement": "°F"})
    hass.states.async_set("sensor.kitchen_oven_current_state", "Preheat")
    await hass.async_block_till_done()
    live = [c for c in calls if c.data["data"].get("live_update")]
    assert live[-1].data["data"]["critical_text"] == "Preheating"
    assert "100°F → 350°F" in live[-1].data["message"]

    # Climbing in small steps: only ~10 % progress steps are pushed
    for t in range(105, 330, 5):
        hass.states.async_set("sensor.kitchen_oven_display_temperature", str(t), {"unit_of_measurement": "°F"})
        await hass.async_block_till_done()
    live = [c for c in calls if c.data["data"].get("live_update")]
    assert len(live) <= 11
    assert _titled(calls, "🔥 Kitchen Oven preheated") == []

    # Reached: state switches to Bake
    hass.states.async_set("sensor.kitchen_oven_display_temperature", "350", {"unit_of_measurement": "°F"})
    hass.states.async_set("sensor.kitchen_oven_current_state", "Bake")
    await hass.async_block_till_done()
    alerts = _titled(calls, "🔥 Kitchen Oven preheated")
    assert len(alerts) == 1 and "350°F" in alerts[0].data["message"]

    # Temperature wobbling while baking: no more preheat alerts or pushes
    sent = len(calls)
    for t in ("345", "352", "348"):
        hass.states.async_set("sensor.kitchen_oven_display_temperature", t, {"unit_of_measurement": "°F"})
        await hass.async_block_till_done()
    assert len(calls) == sent

    # Oven off -> preheat alert removed
    hass.states.async_set("sensor.kitchen_oven_current_state", "Off")
    await hass.async_block_till_done()
    cleared = [c.data["data"]["tag"] for c in calls if c.data.get("message") == "clear_notification"]
    assert any(t.endswith("_preheat") for t in cleared)


# ---------------------------------------------------------------- leak
DW = {
    "sensor.kitchen_dishwasher_operating_mode": ("Off", {}),
    "sensor.kitchen_dishwasher_time_remaining": ("0.0", {"unit_of_measurement": "h"}),
    "binary_sensor.kitchen_dishwasher_door": ("off", {"device_class": "opening"}),
}


async def test_leak_auto_found_and_alerts(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    leak = "binary_sensor.kitchen_dishwasher_leak_sensor_water_leak"
    hass.states.async_set(leak, "off", {"device_class": "moisture",
                                        "friendly_name": "Kitchen Dishwasher Leak Sensor Water leak"})
    hass.states.async_set("binary_sensor.garage_leak_sensor_water_leak", "off", {"device_class": "moisture"})
    dw = await _ge_device(hass, ge, "dw", "Kitchen Dishwasher", DW)
    result, suggested = await _setup(hass, dw.id, {"devices": [me.id], "leak_entities": [leak]})
    assert suggested["leak_entities"] == [leak]  # pre-filled, garage sensor not included

    hass.states.async_set(leak, "on", {"device_class": "moisture",
                                       "friendly_name": "Kitchen Dishwasher Leak Sensor Water leak"})
    await hass.async_block_till_done()
    alerts = _titled(calls, "💧")
    assert len(alerts) == 1
    assert alerts[0].data["data"]["push"]["interruption-level"] == "critical"
    assert "Leak Sensor" in alerts[0].data["message"]

    await _tick(hass, freezer, timedelta(minutes=2))
    assert len(_titled(calls, "💧")) == 1
    await _tick(hass, freezer, timedelta(minutes=3, seconds=30))
    assert len(_titled(calls, "💧")) == 2

    hass.states.async_set(leak, "off", {"device_class": "moisture"})
    await hass.async_block_till_done()
    assert calls[-1].data["title"].endswith("leak cleared")
    assert calls[-1].data["data"]["tag"] == alerts[0].data["data"]["tag"]


# ---------------------------------------------------------------- laundry
WASHER = {
    "sensor.laundry_room_washer_state": ("Off", {}),
    "sensor.laundry_room_washer_sub_cycle": ("---", {}),
    "sensor.laundry_room_washer_cycle": ("Normal", {}),
    "sensor.laundry_room_washer_time_remaining": ("0", {"unit_of_measurement": "min"}),
    "binary_sensor.laundry_room_washer_end_of_cycle": ("off", {}),
    "binary_sensor.laundry_room_washer_door": ("off", {"device_class": "door"}),
}
DRYER = {
    "sensor.laundry_room_dryer_state": ("Off", {}),
    "sensor.laundry_room_dryer_sub_cycle": ("---", {}),
    "sensor.laundry_room_dryer_dryness_new_level": ("More Dry", {}),
    "sensor.laundry_room_dryer_time_remaining": ("0", {"unit_of_measurement": "min"}),
}


async def _washer(hass, phone):
    me, ge, calls = phone
    await _ge_device(hass, ge, "dryer", "Laundry Room Dryer", DRYER)
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    result, suggested = await _setup(
        hass, washer.id,
        {"devices": [me.id], "move_reminder_minutes": 15, "move_repeat_minutes": 15,
         "move_max_reminders": 3, "dryer_entity": "sensor.laundry_room_dryer_state"},
    )
    assert suggested["dryer_entity"] == "sensor.laundry_room_dryer_state"
    hass.states.async_set("sensor.laundry_room_washer_time_remaining", "40", {"unit_of_measurement": "min"})
    hass.states.async_set("sensor.laundry_room_washer_state", "Run")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.laundry_room_washer_time_remaining", "0", {"unit_of_measurement": "min"})
    hass.states.async_set("binary_sensor.laundry_room_washer_end_of_cycle", "on")
    hass.states.async_set("sensor.laundry_room_washer_state", "Finished")
    await hass.async_block_till_done()
    return calls


async def test_move_reminder_until_dryer_starts(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone)
    await _tick(hass, freezer, timedelta(minutes=14))
    assert _titled(calls, "🧺") == []
    await _tick(hass, freezer, timedelta(minutes=2))
    assert len(_titled(calls, "🧺")) == 1
    await _tick(hass, freezer, timedelta(minutes=15))
    assert len(_titled(calls, "🧺")) == 2

    hass.states.async_set("sensor.laundry_room_dryer_state", "Run")
    await hass.async_block_till_done()
    cleared = [c.data["data"]["tag"] for c in calls if c.data.get("message") == "clear_notification"]
    assert any(t.endswith("_move") for t in cleared)
    await _tick(hass, freezer, timedelta(minutes=30))
    assert len(_titled(calls, "🧺")) == 2


async def test_move_reminder_stops_when_door_opens(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone)
    await _tick(hass, freezer, timedelta(minutes=5))
    hass.states.async_set("binary_sensor.laundry_room_washer_door", "on")
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(minutes=60))
    assert _titled(calls, "🧺") == []


async def test_move_reminder_max(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone)
    for _ in range(12):
        await _tick(hass, freezer, timedelta(minutes=10))
    assert len(_titled(calls, "🧺")) == 3
