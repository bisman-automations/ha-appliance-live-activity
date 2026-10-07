"""v1.8.0: who's home, dishwasher ready to unload, events, history, Repairs, diagnostics."""
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
from homeassistant.helpers import issue_registry as ir

from custom_components.appliance_live_activity.const import DOMAIN
from custom_components.appliance_live_activity.diagnostics import async_get_config_entry_diagnostics


async def _ge_device(hass, ge, uid, name, states):
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


def _phone(hass, entry, uid, name, tracker_state=None):
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mobile_app", uid)}, name=name
    )
    if tracker_state is not None:
        obj = name.lower().replace(" ", "_")
        er.async_get(hass).async_get_or_create(
            "device_tracker", "mobile_app", uid, suggested_object_id=obj,
            device_id=device.id, config_entry=entry,
        )
        hass.states.async_set(f"device_tracker.{obj}", tracker_state)
    return device


@pytest.fixture
async def env(hass: HomeAssistant, enable_custom_integrations):
    mobile = MockConfigEntry(domain="mobile_app")
    mobile.add_to_hass(hass)
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    return mobile, ge


async def _setup(hass, device_id, notify_input):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "ge_home"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source_device": device_id})
    assert result["step_id"] == "notify", result
    result = await hass.config_entries.flow.async_configure(result["flow_id"], notify_input)
    await hass.async_block_till_done()
    assert result["type"] == "create_entry", result
    return result


async def _tick(hass, freezer, delta):
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _titled(calls, start):
    return [c for c in calls if str(c.data.get("title", "")).startswith(start)]


def _set(hass, entity, state, attrs=None):
    hass.states.async_set(entity, state, attrs or {})


WASHER = {
    "sensor.laundry_room_washer_state": ("Off", {}),
    "sensor.laundry_room_washer_sub_cycle": ("---", {}),
    "sensor.laundry_room_washer_cycle": ("Normal", {}),
    "sensor.laundry_room_washer_time_remaining": ("0", {"unit_of_measurement": "min"}),
    "binary_sensor.laundry_room_washer_end_of_cycle": ("off", {}),
    "binary_sensor.laundry_room_washer_door": ("off", {"device_class": "door"}),
}


async def _cycle(hass, freezer=None, minutes=40, prefix="laundry_room_washer"):
    _set(hass, f"binary_sensor.{prefix}_end_of_cycle", "off")
    _set(hass, f"sensor.{prefix}_time_remaining", str(minutes), {"unit_of_measurement": "min"})
    _set(hass, f"sensor.{prefix}_state", "Run")
    await hass.async_block_till_done()
    if freezer is not None:
        await _tick(hass, freezer, timedelta(minutes=minutes))
    _set(hass, f"sensor.{prefix}_time_remaining", "0", {"unit_of_measurement": "min"})
    _set(hass, f"binary_sensor.{prefix}_end_of_cycle", "on")
    _set(hass, f"sensor.{prefix}_state", "Finished")
    await hass.async_block_till_done()


# ---------------------------------------------------------------- who's home
async def test_only_people_who_are_home(hass: HomeAssistant, env, freezer):
    mobile, ge = env
    mine = _phone(hass, mobile, "a", "My Phone", "home")
    theirs = _phone(hass, mobile, "b", "Partner Phone", "not_home")
    mine_calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    their_calls = async_mock_service(hass, "notify", "mobile_app_partner_phone")
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    await _setup(hass, washer.id, {"devices": [mine.id, theirs.id], "only_home": True})

    await _cycle(hass)
    assert len(_titled(mine_calls, "✅ Laundry Room Washer finished")) == 1
    assert _titled(their_calls, "✅") == []
    # Live Activities still go to everyone
    assert [c for c in their_calls if c.data["data"].get("live_update")]

    # Nobody home -> everyone
    _set(hass, "device_tracker.my_phone", "not_home")
    _set(hass, "binary_sensor.laundry_room_washer_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    _set(hass, "binary_sensor.laundry_room_washer_door", "off", {"device_class": "door"})
    await _cycle(hass)
    assert len(_titled(mine_calls, "✅")) == 2
    assert len(_titled(their_calls, "✅")) == 1


async def test_home_only_off_by_default(hass: HomeAssistant, env, freezer):
    mobile, ge = env
    mine = _phone(hass, mobile, "a", "My Phone", "home")
    theirs = _phone(hass, mobile, "b", "Partner Phone", "not_home")
    async_mock_service(hass, "notify", "mobile_app_my_phone")
    their_calls = async_mock_service(hass, "notify", "mobile_app_partner_phone")
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    await _setup(hass, washer.id, {"devices": [mine.id, theirs.id]})
    await _cycle(hass)
    assert len(_titled(their_calls, "✅")) == 1


# ---------------------------------------------------------------- dishwasher
DW = {
    "sensor.kitchen_dishwasher_operating_mode": ("Off", {}),
    "sensor.kitchen_dishwasher_time_remaining": ("0.0", {"unit_of_measurement": "h"}),
    "binary_sensor.kitchen_dishwasher_door": ("off", {"device_class": "door"}),
    "binary_sensor.kitchen_dishwasher_dishwasher_is_clean": ("off", {}),
}


async def test_dishwasher_ready_to_unload(hass: HomeAssistant, env, freezer):
    mobile, ge = env
    me = _phone(hass, mobile, "a", "My Phone")
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    dw = await _ge_device(hass, ge, "dw", "Kitchen Dishwasher", DW)
    result = await _setup(hass, dw.id, {"devices": [me.id], "dismiss_minutes": 30})
    assert result["data"]["clean_entity"] == "binary_sensor.kitchen_dishwasher_dishwasher_is_clean"

    _set(hass, "sensor.kitchen_dishwasher_time_remaining", "2.0", {"unit_of_measurement": "h"})
    _set(hass, "sensor.kitchen_dishwasher_operating_mode", "Cycle Active")
    await hass.async_block_till_done()
    _set(hass, "binary_sensor.kitchen_dishwasher_dishwasher_is_clean", "on")
    _set(hass, "sensor.kitchen_dishwasher_time_remaining", "0.0", {"unit_of_measurement": "h"})
    _set(hass, "sensor.kitchen_dishwasher_operating_mode", "Cycle Complete")
    await hass.async_block_till_done()
    done = [c for c in calls if c.data["data"].get("critical_text") == "Done"][-1]
    assert "ready to unload" in done.data["message"]

    cleared = lambda: [c for c in calls if c.data.get("message") == "clear_notification"]  # noqa: E731
    await _tick(hass, freezer, timedelta(minutes=95))
    assert cleared() == []
    _set(hass, "binary_sensor.kitchen_dishwasher_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    assert [c.data["data"]["tag"] for c in cleared()] == ["kitchen_dishwasher"]


# ---------------------------------------------------------------- events + history
async def test_cycle_events_and_history(hass: HomeAssistant, env, freezer):
    mobile, ge = env
    me = _phone(hass, mobile, "a", "My Phone")
    async_mock_service(hass, "notify", "mobile_app_my_phone")
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    await _setup(hass, washer.id, {"devices": [me.id]})
    event_entity = "event.laundry_room_washer_cycle"
    state = hass.states.get(event_entity)
    assert state is not None
    assert "finished" in state.attributes["event_types"]

    events = []
    hass.bus.async_listen("state_changed", lambda e: e.data["entity_id"] == event_entity and events.append(
        e.data["new_state"].attributes.get("event_type")))

    _set(hass, "sensor.laundry_room_washer_time_remaining", "45", {"unit_of_measurement": "min"})
    _set(hass, "sensor.laundry_room_washer_state", "Run")
    await hass.async_block_till_done()
    assert hass.states.get(event_entity).attributes["event_type"] == "started"
    await _tick(hass, freezer, timedelta(minutes=45))
    _set(hass, "sensor.laundry_room_washer_time_remaining", "0", {"unit_of_measurement": "min"})
    _set(hass, "binary_sensor.laundry_room_washer_end_of_cycle", "on")
    _set(hass, "sensor.laundry_room_washer_state", "Finished")
    await hass.async_block_till_done()
    finished = hass.states.get(event_entity)
    assert finished.attributes["event_type"] == "finished"
    assert finished.attributes["minutes"] == 45
    assert finished.attributes["cycle"] == "Normal"

    await _cycle(hass, freezer, minutes=55)
    assert hass.states.get("sensor.laundry_room_washer_cycles_this_week").state == "2"
    assert hass.states.get("sensor.laundry_room_washer_average_cycle").state == "50"

    # Cancelled: stopped with lots of time left
    _set(hass, "binary_sensor.laundry_room_washer_end_of_cycle", "off")
    _set(hass, "sensor.laundry_room_washer_time_remaining", "40", {"unit_of_measurement": "min"})
    _set(hass, "sensor.laundry_room_washer_state", "Run")
    await hass.async_block_till_done()
    _set(hass, "sensor.laundry_room_washer_state", "Off")
    await hass.async_block_till_done()
    assert events[-2:] == ["started", "cancelled"]
    assert hass.states.get("sensor.laundry_room_washer_cycles_this_week").state == "2"

    # A week later the count drops
    await _tick(hass, freezer, timedelta(days=8))
    assert hass.states.get("sensor.laundry_room_washer_cycles_this_week").state == "0"
    assert hass.states.get("sensor.laundry_room_washer_average_cycle").state == "50"


async def test_door_events(hass: HomeAssistant, env, freezer):
    mobile, ge = env
    me = _phone(hass, mobile, "a", "My Phone")
    async_mock_service(hass, "notify", "mobile_app_my_phone")
    fridge = await _ge_device(hass, ge, "fridge", "Kitchen Refrigerator", {
        "binary_sensor.kitchen_refrigerator_freezer_door": ("off", {"device_class": "door"}),
        "sensor.kitchen_refrigerator_water_filter_status": ("Good", {}),
    })
    await _setup(hass, fridge.id, {"devices": [me.id]})
    entity = "event.kitchen_refrigerator_door"
    assert hass.states.get(entity).attributes["event_types"] == ["door_left_open", "door_closed"]
    _set(hass, "binary_sensor.kitchen_refrigerator_freezer_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(minutes=5, seconds=15))
    assert hass.states.get(entity).attributes["event_type"] == "door_left_open"
    _set(hass, "binary_sensor.kitchen_refrigerator_freezer_door", "off", {"device_class": "door"})
    await hass.async_block_till_done()
    state = hass.states.get(entity)
    assert state.attributes["event_type"] == "door_closed"
    assert state.attributes["minutes_open"] == 5


# ---------------------------------------------------------------- repairs + diagnostics
async def test_repairs(hass: HomeAssistant, env, freezer):
    mobile, ge = env
    me = _phone(hass, mobile, "a", "My Phone")
    gone = _phone(hass, mobile, "b", "Old Phone")  # no notify service
    async_mock_service(hass, "notify", "mobile_app_my_phone")
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    result = await _setup(hass, washer.id, {"devices": [me.id, gone.id]})
    entry_id = result["result"].entry_id
    registry = ir.async_get(hass)

    await _tick(hass, freezer, timedelta(minutes=6))
    issue = registry.async_get_issue(DOMAIN, f"phone_{entry_id}_{gone.id}")
    assert issue is not None and issue.translation_placeholders["phone"] == "Old Phone"
    assert registry.async_get_issue(DOMAIN, f"phone_{entry_id}_{me.id}") is None
    assert registry.async_get_issue(DOMAIN, f"missing_entities_{entry_id}") is None

    # A sensor disappears
    er.async_get(hass).async_remove("binary_sensor.laundry_room_washer_door")
    hass.states.async_remove("binary_sensor.laundry_room_washer_door")
    # The phone comes back
    async_mock_service(hass, "notify", "mobile_app_old_phone")
    await _tick(hass, freezer, timedelta(minutes=31))
    assert registry.async_get_issue(DOMAIN, f"phone_{entry_id}_{gone.id}") is None
    missing = registry.async_get_issue(DOMAIN, f"missing_entities_{entry_id}")
    assert missing is not None
    assert missing.translation_placeholders["entities"] == "binary_sensor.laundry_room_washer_door"

    # Removing the appliance removes its issues
    await hass.config_entries.async_remove(entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, f"missing_entities_{entry_id}") is None


async def test_diagnostics(hass: HomeAssistant, env, freezer):
    mobile, ge = env
    me = _phone(hass, mobile, "a", "My Phone", "home")
    async_mock_service(hass, "notify", "mobile_app_my_phone")
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    result = await _setup(hass, washer.id, {"devices": [me.id]})
    entry = hass.config_entries.async_get_entry(result["result"].entry_id)
    await _cycle(hass, freezer)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["appliance_type"] == "washer"
    assert diag["phones"][me.id] == {"name": "My Phone", "notify_services": ["mobile_app_my_phone"], "home": True}
    assert diag["entities"]["sensor.laundry_room_washer_state"]["state"] == "Finished"
    assert diag["internal"]["history"] and diag["data"]["status"] == "complete"
