"""Run the blueprints inside Home Assistant's automation engine."""
from __future__ import annotations

import asyncio
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

async def _settle(hass):
    """Let automation runs progress without waiting for their long waits to end."""
    for _ in range(20):
        await asyncio.sleep(0)


ROOT = Path(__file__).parent.parent / "blueprints" / "automation"


def _install(hass, name):
    target = Path(hass.config.path("blueprints", "automation", "test"))
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / name, target / name)
    return f"test/{name}"


@pytest.fixture
async def phone(hass: HomeAssistant):
    entry = MockConfigEntry(domain="mobile_app")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("mobile_app", "p")}, name="My Phone"
    )
    return device, async_mock_service(hass, "notify", "mobile_app_my_phone")


async def test_door_left_open_blueprint(hass: HomeAssistant, phone, freezer):
    device, calls = phone
    hass.states.async_set("binary_sensor.freezer_door", "off", {"friendly_name": "Freezer Door"})
    path = await hass.async_add_executor_job(_install, hass, "door_left_open.yaml")
    assert await async_setup_component(
        hass,
        "automation",
        {"automation": {"use_blueprint": {"path": path, "input": {
            "door_sensors": ["binary_sensor.freezer_door"],
            "notify_devices": [device.id],
            "escalate_after": 0,
        }}}},
    )
    await _settle(hass)

    hass.states.async_set("binary_sensor.freezer_door", "on", {"friendly_name": "Freezer Door"})
    await _settle(hass)
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await _settle(hass)
    live = [c for c in calls if c.data["data"].get("live_update")]
    assert len(live) == 1 and live[0].data["data"]["critical_text"] == "Open"
    assert live[0].data["data"]["chronometer"] is True

    # Critical after 5 minutes (from opening)
    freezer.tick(timedelta(minutes=4, seconds=30))
    async_fire_time_changed(hass)
    await _settle(hass)
    crit = [c for c in calls if isinstance(c.data["data"].get("push"), dict)
            and c.data["data"]["push"].get("interruption-level") == "critical"]
    assert len(crit) == 1
    assert [c for c in calls if c.data["data"].get("live_update")][-1].data["data"]["critical_text"] == "Still open"

    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await _settle(hass)
    crit = [c for c in calls if isinstance(c.data["data"].get("push"), dict)
            and c.data["data"]["push"].get("interruption-level") == "critical"]
    assert len(crit) == 2

    hass.states.async_set("binary_sensor.freezer_door", "off", {"friendly_name": "Freezer Door"})
    await _settle(hass)
    assert [c for c in calls if c.data["data"].get("live_update")][-1].data["data"]["critical_text"] == "Closed"
    assert any(c.data.get("message") == "clear_notification" and c.data["data"]["tag"].startswith("door_open_")
               for c in calls)

    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await _settle(hass)
    assert calls[-1].data["message"] == "clear_notification"
    assert calls[-1].data["data"]["tag"].startswith("door_live_")


async def test_ge_blueprint_cycle(hass: HomeAssistant, phone, freezer):
    device, calls = phone
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    washer = dr.async_get(hass).async_get_or_create(
        config_entry_id=ge.entry_id, identifiers={("ge_home", "w")}, name="Laundry Room Washer"
    )
    ent_reg = er.async_get(hass)
    states = {
        "sensor.laundry_room_washer_state": "Off",
        "sensor.laundry_room_washer_sub_cycle": "---",
        "sensor.laundry_room_washer_cycle": "Towels Or Sheets",
        "sensor.laundry_room_washer_time_remaining": "0",
        "binary_sensor.laundry_room_washer_end_of_cycle": "off",
        "binary_sensor.laundry_room_washer_door": "off",
    }
    for eid, st in states.items():
        domain, obj = eid.split(".")
        ent_reg.async_get_or_create(domain, "ge_home", obj, suggested_object_id=obj,
                                    device_id=washer.id, config_entry=ge)
        hass.states.async_set(eid, st, {"unit_of_measurement": "min"} if "time_remaining" in eid else {})

    path = await hass.async_add_executor_job(_install, hass, "ge_appliance_live_activity.yaml")
    assert await async_setup_component(
        hass, "automation",
        {"automation": {"use_blueprint": {"path": path, "input": {"appliance": washer.id, "phones": [device.id]}}}},
    )
    await _settle(hass)

    hass.states.async_set("sensor.laundry_room_washer_time_remaining", "60", {"unit_of_measurement": "min"})
    hass.states.async_set("sensor.laundry_room_washer_sub_cycle", "Wash")
    hass.states.async_set("sensor.laundry_room_washer_state", "Run")
    await _settle(hass)
    live = [c for c in calls if c.data["data"].get("live_update")]
    assert live, "blueprint should start a Live Activity"
    assert live[-1].data["data"]["chronometer"] is True
    n = len(calls)

    hass.states.async_set("sensor.laundry_room_washer_sub_cycle", "Rinse")
    await _settle(hass)
    assert len(calls) == n + 1

    hass.states.async_set("sensor.laundry_room_washer_time_remaining", "0", {"unit_of_measurement": "min"})
    hass.states.async_set("binary_sensor.laundry_room_washer_end_of_cycle", "on")
    await _settle(hass)
    assert any(c.data["data"].get("critical_text") == "Done" for c in calls)

    hass.states.async_set("binary_sensor.laundry_room_washer_door", "on")
    await _settle(hass)
    assert calls[-1].data["message"] == "clear_notification"
