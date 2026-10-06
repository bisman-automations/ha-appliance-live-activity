"""Refrigerator door flow: Live Activity -> critical alerts -> Closed -> cleared."""
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

PREFIX = "kitchen_refrigerator"
DOORS = ["door", "freezer_door", "fridge_left_door", "fridge_right_door"]
NAMES = {
    "door": "Door",
    "freezer_door": "Freezer Door",
    "fridge_left_door": "Fridge Left Door",
    "fridge_right_door": "Fridge Right Door",
}


@pytest.fixture
async def fridge(hass: HomeAssistant, enable_custom_integrations):
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    ge_entry = MockConfigEntry(domain="ge_home")
    ge_entry.add_to_hass(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=ge_entry.entry_id, identifiers={("ge_home", "fridge1")}, name="Kitchen Refrigerator"
    )
    for suffix in DOORS:
        ent_reg.async_get_or_create(
            "binary_sensor", "ge_home", f"fridge1_{suffix}",
            suggested_object_id=f"{PREFIX}_{suffix}", device_id=device.id, config_entry=ge_entry,
        )
        _door(hass, suffix, "off")
    for extra in ("water_filter_status", "doors"):
        ent_reg.async_get_or_create(
            "sensor", "ge_home", f"fridge1_{extra}",
            suggested_object_id=f"{PREFIX}_{extra}", device_id=device.id, config_entry=ge_entry,
        )
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    phone = dev_reg.async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "p")}, name="My Phone"
    )
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "ge_home"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source_device": device.id})
    assert result["step_id"] == "notify"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"devices": [phone.id], "open_delay_seconds": 30, "critical_after_minutes": 5, "critical_repeat_minutes": 1},
    )
    assert result["data"]["appliance_type"] == "refrigerator"
    assert len(result["data"]["door_entities"]) == 4
    assert result["data"]["notification_tag"] == "kitchen_refrigerator"
    await hass.async_block_till_done()
    return calls


def _door(hass, suffix, state):
    hass.states.async_set(
        f"binary_sensor.{PREFIX}_{suffix}", state,
        {"friendly_name": f"Kitchen Refrigerator {NAMES[suffix]}", "device_class": "door"},
    )


def _live(calls):
    return [c for c in calls if c.data.get("data", {}).get("live_update")]


def _critical(calls):
    return [c for c in calls if c.data.get("data", {}).get("push", {}).get("interruption-level") == "critical"]


async def test_door_flow(hass: HomeAssistant, fridge, freezer):
    calls = fridge

    # Quick grab: opened and closed within the delay -> nothing sent
    _door(hass, "fridge_left_door", "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=10))
    _door(hass, "fridge_left_door", "off")
    await hass.async_block_till_done()
    assert calls == []

    # Freezer left open
    _door(hass, "freezer_door", "on")
    await hass.async_block_till_done()
    assert calls == []
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    live = _live(calls)
    assert len(live) == 1
    assert live[0].data["message"] == "Freezer Door is open"
    assert live[0].data["data"]["chronometer"] is True
    assert "when_relative" not in live[0].data["data"]  # absolute -> counts up
    assert _critical(calls) == []

    # Minutes 1-4: no repeat pushes
    for _ in range(4):
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert len(_live(calls)) == 1 and _critical(calls) == []

    # 5 minutes -> activity turns critical + first critical alert
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert _live(calls)[-1].data["data"]["critical_text"] == "Still open"
    assert len(_critical(calls)) == 1

    # Repeats every minute while open
    freezer.tick(timedelta(minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(_critical(calls)) == 2

    # Closed -> critical cleared, activity shows Closed
    _door(hass, "freezer_door", "off")
    await hass.async_block_till_done()
    tags_cleared = [c.data["data"]["tag"] for c in calls if c.data.get("message") == "clear_notification"]
    assert any(t.endswith("_critical") for t in tags_cleared)
    assert _live(calls)[-1].data["data"]["critical_text"] == "Closed"

    # ...and is ended a minute later
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls[-1].data["message"] == "clear_notification"
    assert not calls[-1].data["data"]["tag"].endswith("_critical")


async def test_generic_door_escalation(hass: HomeAssistant, enable_custom_integrations, freezer):
    dev_reg = dr.async_get(hass)
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    me = dev_reg.async_get_or_create(config_entry_id=phone_entry.entry_id,
                                     identifiers={("mobile_app", "a")}, name="My Phone")
    partner = dev_reg.async_get_or_create(config_entry_id=phone_entry.entry_id,
                                          identifiers={("mobile_app", "b")}, name="Partner Phone")
    mine = async_mock_service(hass, "notify", "mobile_app_my_phone")
    theirs = async_mock_service(hass, "notify", "mobile_app_partner_phone")
    scene_create = async_mock_service(hass, "scene", "create")
    light_on = async_mock_service(hass, "light", "turn_on")
    scene_on = async_mock_service(hass, "scene", "turn_on")
    async_mock_service(hass, "scene", "delete")
    tts = async_mock_service(hass, "tts", "speak")
    hass.states.async_set("binary_sensor.garage_door", "off", {"friendly_name": "Garage Door"})

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"appliance_type": "door", "name": "Garage"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"state_entity": "binary_sensor.garage_door"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"devices": [me.id], "open_delay_seconds": 0, "critical_after_minutes": 10,
         "critical_repeat_minutes": 2, "escalate_after": 1, "escalation_devices": [partner.id],
         "tts_entity": "tts.home", "speakers": ["media_player.kitchen"], "alert_lights": ["light.hall"]},
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()

    hass.states.async_set("binary_sensor.garage_door", "on", {"friendly_name": "Garage Door"})
    await hass.async_block_till_done()
    assert len(_live(mine)) == 1  # no start delay

    for _ in range(10):
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert len(_critical(mine)) == 1 and _critical(theirs) == []  # not escalated yet
    assert tts == [] and light_on == []

    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(_critical(mine)) == 2 and len(_critical(theirs)) == 1
    assert len(tts) == 1 and len(scene_create) == 1 and len(light_on) == 1

    hass.states.async_set("binary_sensor.garage_door", "off", {"friendly_name": "Garage Door"})
    await hass.async_block_till_done()
    assert len(scene_on) == 1  # lights restored
    assert any(c.data.get("message") == "clear_notification" for c in theirs)
