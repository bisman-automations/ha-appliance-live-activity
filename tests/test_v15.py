"""v1.5.0: delayed-start Live Activity + notification action buttons."""
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

from tests.conftest import suggested_values
from custom_components.appliance_live_activity.const import DOMAIN, EVENT_NOTIFICATION_ACTION
from custom_components.appliance_live_activity.ge import discover_from_entity_ids


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
    suggested = suggested_values(result)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], notify_input)
    await hass.async_block_till_done()
    return result, suggested


async def _tick(hass, freezer, delta):
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _live(calls):
    return [c for c in calls if c.data.get("data", {}).get("live_update")]


def _titled(calls, start):
    return [c for c in calls if str(c.data.get("title", "")).startswith(start)]


def _cleared(calls):
    return [c.data["data"]["tag"] for c in calls if c.data.get("message") == "clear_notification"]


async def _action(hass, action):
    hass.bus.async_fire(EVENT_NOTIFICATION_ACTION, {"action": action})
    await hass.async_block_till_done()


def _status(hass, name):
    return hass.states.get(f"sensor.{name}_status")


# ---------------------------------------------------------------- discovery
def test_discovers_delay_and_start_button():
    found = discover_from_entity_ids([
        "sensor.laundry_room_dryer_state",
        "sensor.laundry_room_dryer_sub_cycle",
        "sensor.laundry_room_dryer_dryness_new_level",
        "sensor.laundry_room_dryer_time_remaining",
        "sensor.laundry_room_dryer_delay_time_remaining",
        "button.laundry_room_dryer_start_cycle",
    ])
    assert found.appliance_type == "dryer"
    assert found.remaining_entity == "sensor.laundry_room_dryer_time_remaining"
    assert found.delay_entity == "sensor.laundry_room_dryer_delay_time_remaining"
    assert found.start_button == "button.laundry_room_dryer_start_cycle"

    dishwasher = discover_from_entity_ids([
        "sensor.kitchen_dishwasher_operating_mode",
        "sensor.kitchen_dishwasher_time_remaining",
        "sensor.kitchen_dishwasher_user_setting_delay_hours",
    ])
    assert dishwasher.delay_entity == "sensor.kitchen_dishwasher_user_setting_delay_hours"


# ---------------------------------------------------------------- laundry
WASHER = {
    "sensor.laundry_room_washer_state": ("Off", {}),
    "sensor.laundry_room_washer_sub_cycle": ("---", {}),
    "sensor.laundry_room_washer_cycle": ("Normal", {}),
    "sensor.laundry_room_washer_time_remaining": ("0", {"unit_of_measurement": "min"}),
    "sensor.laundry_room_washer_delay_time_remaining": ("0", {"unit_of_measurement": "h"}),
    "binary_sensor.laundry_room_washer_end_of_cycle": ("off", {}),
    "binary_sensor.laundry_room_washer_door": ("off", {"device_class": "door"}),
}
DRYER = {
    "sensor.laundry_room_dryer_state": ("Off", {}),
    "sensor.laundry_room_dryer_sub_cycle": ("---", {}),
    "sensor.laundry_room_dryer_dryness_new_level": ("More Dry", {}),
    "sensor.laundry_room_dryer_time_remaining": ("0", {"unit_of_measurement": "min"}),
    "button.laundry_room_dryer_start_cycle": ("unknown", {}),
    "binary_sensor.laundry_room_dryer_remote_status": ("on", {}),
}


async def _washer(hass, phone, **extra):
    me, ge, calls = phone
    await _ge_device(hass, ge, "dryer", "Laundry Room Dryer", DRYER)
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    result, suggested = await _setup(
        hass, washer.id,
        {"devices": [me.id], "move_reminder_minutes": 15,
         "dryer_entity": "sensor.laundry_room_dryer_state",
         "dryer_start_entity": "button.laundry_room_dryer_start_cycle", **extra},
    )
    assert result["data"]["delay_entity"] == "sensor.laundry_room_washer_delay_time_remaining"
    assert suggested["dryer_start_entity"] == "button.laundry_room_dryer_start_cycle"
    return calls


async def _run_and_finish(hass):
    hass.states.async_set("sensor.laundry_room_washer_time_remaining", "40", {"unit_of_measurement": "min"})
    hass.states.async_set("sensor.laundry_room_washer_state", "Run")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.laundry_room_washer_time_remaining", "0", {"unit_of_measurement": "min"})
    hass.states.async_set("binary_sensor.laundry_room_washer_end_of_cycle", "on")
    hass.states.async_set("sensor.laundry_room_washer_state", "Finished")
    await hass.async_block_till_done()


async def test_delayed_start_live_activity(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone)
    hass.states.async_set("sensor.laundry_room_washer_delay_time_remaining", "2.0", {"unit_of_measurement": "h"})
    hass.states.async_set("sensor.laundry_room_washer_state", "Delay Run")
    await hass.async_block_till_done()

    live = _live(calls)
    assert len(live) == 1
    data = live[0].data["data"]
    assert data["critical_text"] == "Scheduled"
    assert data["when"] == 7200 and data["when_relative"] is True
    assert "Delayed start" in live[0].data["message"] and "starts at" in live[0].data["message"]
    assert _status(hass, "laundry_room_washer").state == "delayed"
    assert _status(hass, "laundry_room_washer").attributes["starts_at"] is not None

    # The delay sensor counting down with the clock does not push again
    for minutes_left in (114, 108, 102):
        await _tick(hass, freezer, timedelta(minutes=6))
        hass.states.async_set("sensor.laundry_room_washer_delay_time_remaining",
                              str(minutes_left / 60), {"unit_of_measurement": "h"})
        await hass.async_block_till_done()
    assert len(_live(calls)) == 1

    # Starts: the same activity switches to the normal countdown
    hass.states.async_set("sensor.laundry_room_washer_delay_time_remaining", "0", {"unit_of_measurement": "h"})
    hass.states.async_set("sensor.laundry_room_washer_time_remaining", "50", {"unit_of_measurement": "min"})
    hass.states.async_set("sensor.laundry_room_washer_state", "Run")
    await hass.async_block_till_done()
    live = _live(calls)
    assert len(live) == 2
    assert live[-1].data["data"]["critical_text"] != "Scheduled"
    assert live[-1].data["data"]["when"] == 50 * 60
    assert live[-1].data["data"]["tag"] == live[0].data["data"]["tag"]
    assert _cleared(calls) == []


async def test_delay_cancelled_clears(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone)
    hass.states.async_set("sensor.laundry_room_washer_delay_time_remaining", "1.0", {"unit_of_measurement": "h"})
    hass.states.async_set("sensor.laundry_room_washer_state", "Delay Run")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.laundry_room_washer_state", "Off")
    await hass.async_block_till_done()
    assert _cleared(calls) == ["laundry_room_washer"]
    assert _status(hass, "laundry_room_washer").state == "idle"


async def test_delay_can_be_turned_off(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone, delay_start=False)
    hass.states.async_set("sensor.laundry_room_washer_delay_time_remaining", "1.0", {"unit_of_measurement": "h"})
    hass.states.async_set("sensor.laundry_room_washer_state", "Delay Run")
    await hass.async_block_till_done()
    assert _live(calls) == []


DW = {
    "sensor.kitchen_dishwasher_operating_mode": ("Off", {}),
    "sensor.kitchen_dishwasher_time_remaining": ("0.0", {"unit_of_measurement": "h"}),
    "sensor.kitchen_dishwasher_user_setting_delay_hours": ("4", {"unit_of_measurement": "h"}),
}


async def test_dishwasher_delay_setting_does_not_move(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    dw = await _ge_device(hass, ge, "dw", "Kitchen Dishwasher", DW)
    await _setup(hass, dw.id, {"devices": [me.id]})
    # The setting stays at 4 h, so the start time must stay fixed
    hass.states.async_set("sensor.kitchen_dishwasher_operating_mode", "Delay")
    await hass.async_block_till_done()
    for _ in range(30):
        await _tick(hass, freezer, timedelta(minutes=1))
    live = _live(calls)
    assert len(live) == 1 and live[0].data["data"]["when"] == 4 * 3600


async def test_finished_alert_buttons_and_start_dryer(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone)
    presses = async_mock_service(hass, "button", "press")
    await _run_and_finish(hass)

    alert = _titled(calls, "✅ Normal: washed")[0]
    assert alert.data["message"] == "Laundry Room Washer finished the Normal cycle. Load it into the dryer."
    assert alert.data["data"]["tag"] == "laundry_room_washer_load_1"
    actions = alert.data["data"]["actions"]
    assert [a["title"] for a in actions] == ["Start dryer", "Laundry moved"]
    assert actions[0]["action"] == "LAUNDRY_ROOM_WASHER_START_DRYER"

    # Another appliance's button does nothing
    await _action(hass, "SOMETHING_ELSE_START_DRYER")
    assert presses == []

    await _action(hass, actions[0]["action"])
    assert len(presses) == 1
    assert presses[0].data["entity_id"] in ("button.laundry_room_dryer_start_cycle",
                                            ["button.laundry_room_dryer_start_cycle"])
    # Finished Live Activity removed; the load's notification stays for the
    # dryer to complete; no reminders afterwards
    assert "laundry_room_washer_load_1" not in _cleared(calls)
    assert "laundry_room_washer" in _cleared(calls)
    await _tick(hass, freezer, timedelta(minutes=60))
    assert _titled(calls, "🧺") == []


async def test_start_dryer_remote_off(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone)
    presses = async_mock_service(hass, "button", "press")
    hass.states.async_set("binary_sensor.laundry_room_dryer_remote_status", "off")
    await _run_and_finish(hass)
    await _action(hass, "LAUNDRY_ROOM_WASHER_START_DRYER")
    assert presses == []
    assert len(_titled(calls, "🧺 Couldn't start the dryer")) == 1


async def test_laundry_moved_stops_reminders(hass: HomeAssistant, phone, freezer):
    calls = await _washer(hass, phone)
    await _run_and_finish(hass)
    await _tick(hass, freezer, timedelta(minutes=16))
    reminders = _titled(calls, "🧺 Move the laundry")
    assert len(reminders) == 1
    assert [a["title"] for a in reminders[0].data["data"]["actions"]] == ["Start dryer", "Laundry moved"]

    await _action(hass, "LAUNDRY_ROOM_WASHER_LAUNDRY_MOVED")
    assert "laundry_room_washer_move" in _cleared(calls)
    await _tick(hass, freezer, timedelta(minutes=60))
    assert len(_titled(calls, "🧺 Move the laundry")) == 1


# ---------------------------------------------------------------- leak
async def test_silence_leak(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    leak = "binary_sensor.kitchen_dishwasher_leak_sensor_water_leak"
    hass.states.async_set(leak, "off", {"device_class": "moisture"})
    dw = await _ge_device(hass, ge, "dw", "Kitchen Dishwasher", DW)
    await _setup(hass, dw.id, {"devices": [me.id], "leak_entities": [leak]})

    hass.states.async_set(leak, "on", {"device_class": "moisture"})
    await hass.async_block_till_done()
    alert = _titled(calls, "💧")[0]
    action = alert.data["data"]["actions"][0]
    assert action == {"action": "KITCHEN_DISHWASHER_SILENCE_LEAK", "title": "Silence until dry"}

    await _action(hass, action["action"])
    assert "kitchen_dishwasher_leak" in _cleared(calls)
    await _tick(hass, freezer, timedelta(minutes=20))
    assert len(_titled(calls, "💧")) == 1

    # Dry, then a new leak alerts again
    hass.states.async_set(leak, "off", {"device_class": "moisture"})
    await hass.async_block_till_done()
    hass.states.async_set(leak, "on", {"device_class": "moisture"})
    await hass.async_block_till_done()
    assert len(_titled(calls, "💧")) == 2


# ---------------------------------------------------------------- doors
async def test_snooze_door_alert(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    fridge = await _ge_device(hass, ge, "fridge", "Kitchen Refrigerator", {
        "binary_sensor.kitchen_refrigerator_freezer_door": ("off", {"device_class": "door"}),
        "sensor.kitchen_refrigerator_water_filter_status": ("Good", {}),
    })
    result, suggested = await _setup(hass, fridge.id, {"devices": [me.id], "snooze_minutes": 10})
    assert suggested.get("snooze_minutes") in (None, 10)

    hass.states.async_set("binary_sensor.kitchen_refrigerator_freezer_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(minutes=5, seconds=15))
    critical = _titled(calls, "🚨")
    assert len(critical) == 1
    action = critical[0].data["data"]["actions"][0]
    assert action == {"action": "KITCHEN_REFRIGERATOR_SNOOZE_DOOR", "title": "Snooze 10 min"}

    await _action(hass, action["action"])
    assert "kitchen_refrigerator_critical" in _cleared(calls)
    assert _status(hass, "kitchen_refrigerator").attributes["snoozed_until"] is not None
    for _ in range(9):
        await _tick(hass, freezer, timedelta(minutes=1))
    assert len(_titled(calls, "🚨")) == 1

    # Snooze over: alerts resume while it's still open
    await _tick(hass, freezer, timedelta(minutes=1, seconds=15))
    assert len(_titled(calls, "🚨")) == 2
    await _tick(hass, freezer, timedelta(minutes=1))
    assert len(_titled(calls, "🚨")) == 3


async def test_existing_ge_entry_backfilled(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    await _ge_device(hass, ge, "dryer", "Laundry Room Dryer", DRYER)
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    # Entry as created by 1.4.0: no delay sensor / dryer start button
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "ge_home",
            "source_device": washer.id,
            "appliance_type": "washer",
            "name": "Laundry Room Washer",
            "state_entity": "sensor.laundry_room_washer_state",
            "remaining_entity": "sensor.laundry_room_washer_time_remaining",
            "notification_tag": "laundry_room_washer",
            "devices": [me.id],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.data["delay_entity"] == "sensor.laundry_room_washer_delay_time_remaining"
    assert entry.data["dryer_start_entity"] == "button.laundry_room_dryer_start_cycle"
