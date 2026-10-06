"""v1.7.0: sections, Reconfigure, quiet hours, dryer unload reminder, fridge alerts."""
from __future__ import annotations

from datetime import time, timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.appliance_live_activity.const import DOMAIN, EVENT_NOTIFICATION_ACTION
from custom_components.appliance_live_activity.helpers import in_quiet_hours


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
    form = result
    result = await hass.config_entries.flow.async_configure(result["flow_id"], notify_input)
    await hass.async_block_till_done()
    assert result["type"] == "create_entry", result
    return result, form


async def _tick(hass, freezer, delta):
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _titled(calls, start):
    return [c for c in calls if str(c.data.get("title", "")).startswith(start)]


def _cleared(calls):
    return [c.data["data"]["tag"] for c in calls if c.data.get("message") == "clear_notification"]


def _set(hass, entity, state, attrs=None):
    hass.states.async_set(entity, state, attrs or {})


# ---------------------------------------------------------------- pure
def test_quiet_hours_window():
    assert in_quiet_hours(time(23, 0), "22:00:00", "07:00:00")
    assert in_quiet_hours(time(6, 59), "22:00", "07:00")
    assert not in_quiet_hours(time(7, 0), "22:00", "07:00")
    assert not in_quiet_hours(time(12, 0), "22:00", "07:00")
    assert in_quiet_hours(time(13, 0), "12:00", "14:00")
    assert not in_quiet_hours(time(23, 0), None, "07:00")
    assert not in_quiet_hours(time(23, 0), "07:00", "07:00")


# ---------------------------------------------------------------- laundry
WASHER = {
    "sensor.laundry_room_washer_state": ("Off", {}),
    "sensor.laundry_room_washer_sub_cycle": ("---", {}),
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
}


async def _cycle(hass, prefix):
    _set(hass, f"sensor.{prefix}_time_remaining", "40", {"unit_of_measurement": "min"})
    _set(hass, f"sensor.{prefix}_state", "Run")
    await hass.async_block_till_done()
    _set(hass, f"sensor.{prefix}_time_remaining", "0", {"unit_of_measurement": "min"})
    _set(hass, f"binary_sensor.{prefix}_end_of_cycle", "on")
    _set(hass, f"sensor.{prefix}_state", "Finished")
    await hass.async_block_till_done()


async def test_form_sections(hass: HomeAssistant, phone):
    me, ge, calls = phone
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    result, form = await _setup(hass, washer.id, {"devices": [me.id], "quiet_start": "22:00:00"})
    schema = form["data_schema"].schema
    keys = [str(k) for k in schema]
    assert keys[:4] == ["devices", "finished_alert", "dismiss_minutes", "delay_start"]
    assert "laundry" in keys and "quiet_hours" in keys and "appearance" in keys
    assert "fridge" not in keys and "cooking" not in keys
    assert schema[next(k for k in schema if str(k) == "laundry")].options["collapsed"] is False
    assert schema[next(k for k in schema if str(k) == "quiet_hours")].options["collapsed"] is True
    # Stored flat
    assert result["data"]["quiet_start"] == "22:00:00"
    assert "quiet_hours" not in result["data"] and "laundry" not in result["data"]


async def test_quiet_hours_hold_regular_alerts(hass: HomeAssistant, phone, freezer):
    freezer.move_to("2026-10-06 23:00:00-07:00")
    me, ge, calls = phone
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    leak = "binary_sensor.laundry_room_washer_leak_sensor_water_leak"
    _set(hass, leak, "off", {"device_class": "moisture"})
    await _setup(hass, washer.id, {
        "devices": [me.id], "quiet_start": "22:00:00", "quiet_end": "07:00:00",
        "supply_entities": ["sensor.laundry_room_washer_smart_dispense_loads_left"],
        "leak_entities": [leak],
    })
    await _cycle(hass, "laundry_room_washer")
    # The Live Activity still updates; the regular alerts wait
    assert [c for c in calls if c.data["data"].get("critical_text") == "Done"]
    assert _titled(calls, "✅ Laundry Room Washer finished") == []
    assert _titled(calls, "🧴") == []

    # Critical alerts never wait
    _set(hass, leak, "on", {"device_class": "moisture"})
    await hass.async_block_till_done()
    assert len(_titled(calls, "💧")) == 1
    _set(hass, leak, "off", {"device_class": "moisture"})
    await hass.async_block_till_done()

    # Move reminders pile up overnight: only the latest is kept
    for _ in range(6):
        await _tick(hass, freezer, timedelta(minutes=15))
    assert _titled(calls, "🧺") == []

    # 07:00 -> delivered once each
    freezer.move_to("2026-10-07 07:00:30-07:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(_titled(calls, "✅ Laundry Room Washer finished")) == 1
    assert len(_titled(calls, "🧴")) == 1
    assert len(_titled(calls, "🧺 Move the laundry")) == 1


async def test_quiet_hours_cleared_alert_is_dropped(hass: HomeAssistant, phone, freezer):
    freezer.move_to("2026-10-06 23:00:00-07:00")
    me, ge, calls = phone
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    await _setup(hass, washer.id, {"devices": [me.id], "quiet_start": "22:00:00", "quiet_end": "07:00:00"})
    await _cycle(hass, "laundry_room_washer")
    # Laundry moved overnight: the held reminders are no longer relevant
    hass.bus.async_fire(EVENT_NOTIFICATION_ACTION, {"action": "LAUNDRY_ROOM_WASHER_LAUNDRY_MOVED"})
    await hass.async_block_till_done()
    freezer.move_to("2026-10-07 07:01:00-07:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _titled(calls, "✅ Laundry Room Washer finished") == []
    assert _titled(calls, "🧺") == []


async def test_dryer_unload_reminder(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    dryer = await _ge_device(hass, ge, "dryer", "Laundry Room Dryer", DRYER)
    result, form = await _setup(hass, dryer.id, {"devices": [me.id]})
    await _cycle(hass, "laundry_room_dryer")
    done = _titled(calls, "✅ Laundry Room Dryer finished")[0]
    assert done.data["data"]["actions"] == [
        {"action": "LAUNDRY_ROOM_DRYER_LAUNDRY_MOVED", "title": "Unloaded"}
    ]
    await _tick(hass, freezer, timedelta(minutes=29))
    assert _titled(calls, "🧺") == []
    await _tick(hass, freezer, timedelta(minutes=2))
    reminders = _titled(calls, "🧺 Unload the dryer")
    assert len(reminders) == 1 and "min ago" in reminders[0].data["message"]
    await _tick(hass, freezer, timedelta(minutes=30))
    assert len(_titled(calls, "🧺 Unload the dryer")) == 2
    await _tick(hass, freezer, timedelta(minutes=60))
    assert len(_titled(calls, "🧺 Unload the dryer")) == 2  # max 2

    # Next load: the Unloaded button stops it
    _set(hass, "binary_sensor.laundry_room_dryer_end_of_cycle", "off")
    await _cycle(hass, "laundry_room_dryer")
    await _tick(hass, freezer, timedelta(minutes=31))
    assert len(_titled(calls, "🧺 Unload the dryer")) == 3
    hass.bus.async_fire(EVENT_NOTIFICATION_ACTION, {"action": "LAUNDRY_ROOM_DRYER_LAUNDRY_MOVED"})
    await hass.async_block_till_done()
    assert "laundry_room_dryer_move" in _cleared(calls)
    await _tick(hass, freezer, timedelta(minutes=60))
    assert len(_titled(calls, "🧺 Unload the dryer")) == 3


async def test_dryer_reminder_stops_when_door_opens(hass: HomeAssistant, phone, freezer):
    me, ge, calls = phone
    dryer = await _ge_device(hass, ge, "dryer", "Laundry Room Dryer", DRYER)
    await _setup(hass, dryer.id, {"devices": [me.id]})
    await _cycle(hass, "laundry_room_dryer")
    await _tick(hass, freezer, timedelta(minutes=10))
    _set(hass, "binary_sensor.laundry_room_dryer_door", "on", {"device_class": "door"})
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(minutes=90))
    assert _titled(calls, "🧺") == []


# ---------------------------------------------------------------- fridge
FRIDGE = {
    "binary_sensor.kitchen_refrigerator_freezer_door": ("off", {"device_class": "door"}),
    "sensor.kitchen_refrigerator_current_temperature_fridge": ("37", {"unit_of_measurement": "°F"}),
    "sensor.kitchen_refrigerator_current_temperature_freezer": ("0", {"unit_of_measurement": "°F"}),
    "sensor.kitchen_refrigerator_ice_maker_bucket_status": ("Not Full", {}),
}


async def _fridge(hass, phone, **extra):
    me, ge, calls = phone
    hass.config.units = US_CUSTOMARY_SYSTEM
    fridge = await _ge_device(hass, ge, "fridge", "Kitchen Refrigerator", FRIDGE)
    result, form = await _setup(hass, fridge.id, {"devices": [me.id], **extra})
    data = result["data"]
    assert data["fridge_temp_entity"] == "sensor.kitchen_refrigerator_current_temperature_fridge"
    assert data["freezer_temp_entity"] == "sensor.kitchen_refrigerator_current_temperature_freezer"
    assert data["ice_entity"] == "sensor.kitchen_refrigerator_ice_maker_bucket_status"
    return calls


async def _freezer(hass, temp):
    _set(hass, "sensor.kitchen_refrigerator_current_temperature_freezer", str(temp), {"unit_of_measurement": "°F"})
    await hass.async_block_till_done()


async def test_freezer_too_warm(hass: HomeAssistant, phone, freezer):
    calls = await _fridge(hass, phone)
    await _freezer(hass, 25)
    await _tick(hass, freezer, timedelta(minutes=20))
    assert _titled(calls, "🌡️") == []
    await _tick(hass, freezer, timedelta(minutes=11))
    alerts = _titled(calls, "🌡️ Kitchen Refrigerator: freezer too warm")
    assert len(alerts) == 1
    assert alerts[0].data["data"]["push"]["interruption-level"] == "critical"
    assert "25°F" in alerts[0].data["message"] and "limit 15°F" in alerts[0].data["message"]
    await _tick(hass, freezer, timedelta(minutes=30))
    assert len(_titled(calls, "🌡️")) == 1
    await _tick(hass, freezer, timedelta(minutes=31))
    assert len(_titled(calls, "🌡️")) == 2
    await _freezer(hass, 5)
    assert len(_titled(calls, "✅ Kitchen Refrigerator: freezer back to 5°F")) == 1


async def test_brief_warm_spell_is_ignored(hass: HomeAssistant, phone, freezer):
    calls = await _fridge(hass, phone)
    await _freezer(hass, 25)  # door open for a bit
    await _tick(hass, freezer, timedelta(minutes=10))
    await _freezer(hass, 2)
    await _tick(hass, freezer, timedelta(minutes=10))
    await _freezer(hass, 20)
    await _tick(hass, freezer, timedelta(minutes=25))
    assert _titled(calls, "🌡️") == []
    assert _titled(calls, "✅") == []


async def test_ice_bucket_off_by_default(hass: HomeAssistant, phone, freezer):
    calls = await _fridge(hass, phone)
    _set(hass, "sensor.kitchen_refrigerator_ice_maker_bucket_status", "Full")
    await _tick(hass, freezer, timedelta(minutes=2))
    assert _titled(calls, "🧊") == []


async def test_ice_bucket_full(hass: HomeAssistant, phone, freezer):
    calls = await _fridge(hass, phone, ice_full_alert=True)
    _set(hass, "sensor.kitchen_refrigerator_ice_maker_bucket_status", "Full")
    await _tick(hass, freezer, timedelta(minutes=2))
    await _tick(hass, freezer, timedelta(minutes=2))
    assert len(_titled(calls, "🧊 Kitchen Refrigerator: ice bucket full")) == 1
    _set(hass, "sensor.kitchen_refrigerator_ice_maker_bucket_status", "Not Full")
    await _tick(hass, freezer, timedelta(minutes=2))
    assert "kitchen_refrigerator_ice" in _cleared(calls)


# ---------------------------------------------------------------- reconfigure
async def _reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def test_reconfigure(hass: HomeAssistant, phone):
    me, ge, calls = phone
    washer = await _ge_device(hass, ge, "washer", "Laundry Room Washer", WASHER)
    result, _ = await _setup(hass, washer.id, {"devices": [me.id]})
    entry = hass.config_entries.async_get_entry(result["result"].entry_id)
    assert entry.data["remaining_entity"] == "sensor.laundry_room_washer_time_remaining"

    hass.states.async_set("sensor.my_other_timer", "0", {"unit_of_measurement": "min"})
    result = await _reconfigure(hass, entry)
    assert result["step_id"] == "reconfigure"
    keys = [str(k) for k in result["data_schema"].schema]
    assert keys[0] == "rediscover" and "remaining_entity" in keys
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "state_entity": "sensor.laundry_room_washer_state",
        "remaining_entity": "sensor.my_other_timer",
    })
    await hass.async_block_till_done()
    assert result["type"] == "abort" and result["reason"] == "reconfigure_successful"
    assert entry.data["remaining_entity"] == "sensor.my_other_timer"
    assert entry.data["door_entity"] is None  # cleared
    assert entry.data["devices"] == [me.id]  # untouched

    # Find the GE sensors again
    result = await _reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {
        "rediscover": True, "state_entity": "sensor.laundry_room_washer_state",
    })
    await hass.async_block_till_done()
    assert entry.data["remaining_entity"] == "sensor.laundry_room_washer_time_remaining"
    assert entry.data["door_entity"] == "binary_sensor.laundry_room_washer_door"
