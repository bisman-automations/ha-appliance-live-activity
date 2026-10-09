"""Oven: cooktop left-on critical alerts (GE auto-setup)."""
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

OVEN = {
    "sensor.kitchen_oven_current_state": "Off",
    "sensor.kitchen_oven_cook_mode": "Off",
    "sensor.kitchen_oven_cook_time_remaining": "0.0",
    "sensor.kitchen_oven_display_temperature": "0",
    "binary_sensor.kitchen_oven_cooktop_status": "off",
}


@pytest.fixture
async def oven(hass: HomeAssistant, enable_custom_integrations):
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=ge.entry_id, identifiers={("ge_home", "oven")}, name="Kitchen Oven"
    )
    for eid, st in OVEN.items():
        domain, obj = eid.split(".")
        ent_reg.async_get_or_create(domain, "ge_home", obj, suggested_object_id=obj,
                                    device_id=device.id, config_entry=ge)
        hass.states.async_set(eid, st, {"unit_of_measurement": "h"} if "remaining" in eid else {})
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    phone = dev_reg.async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "p")}, name="My Phone"
    )
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    tts = async_mock_service(hass, "tts", "speak")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "ge_home"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source_device": device.id})
    assert result["step_id"] == "notify"
    cooking = result["data_schema"].schema["cooking"].schema.schema
    assert "cooktop_alert_minutes" in [str(k) for k in cooking]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "devices": [phone.id],
            "cooktop_alert_minutes": 30,
            "cooktop_repeat_minutes": 15,
            "tts_entity": "tts.home",
            "speakers": ["media_player.kitchen"],
        },
    )
    assert result["data"]["appliance_type"] == "oven"
    assert result["data"]["notification_tag"] == "kitchen_oven"
    assert result["data"]["cooktop_entities"] == ["binary_sensor.kitchen_oven_cooktop_status"]
    await hass.async_block_till_done()
    return calls, tts


def _crit(calls):
    return [c for c in calls if c.data.get("title", "").startswith("🔥")]


async def _advance(hass, freezer, delta):
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_cooktop_alerts_repeat_and_clear(hass: HomeAssistant, oven, freezer):
    calls, tts = oven
    hass.states.async_set("binary_sensor.kitchen_oven_cooktop_status", "on")
    await hass.async_block_till_done()
    await _advance(hass, freezer, timedelta(minutes=29))
    assert _crit(calls) == []

    await _advance(hass, freezer, timedelta(minutes=1, seconds=30))
    crit = _crit(calls)
    assert len(crit) == 1
    data = crit[0].data["data"]
    assert data["push"]["interruption-level"] == "critical"
    assert data["actions"][0]["title"] == "Acknowledge"
    assert len(tts) == 1

    await _advance(hass, freezer, timedelta(minutes=10))
    assert len(_crit(calls)) == 1
    await _advance(hass, freezer, timedelta(minutes=6))
    assert len(_crit(calls)) == 2

    hass.states.async_set("binary_sensor.kitchen_oven_cooktop_status", "off")
    await hass.async_block_till_done()
    # Replaced with a quiet "off" notification (reliable on iOS)...
    assert calls[-1].data["title"] == "✅ Cooktop off"
    assert calls[-1].data["data"]["tag"].endswith("_cooktop")
    assert calls[-1].data["data"]["push"]["interruption-level"] == "passive"
    # ...which is removed two minutes later
    await _advance(hass, freezer, timedelta(minutes=2, seconds=5))
    assert calls[-1].data["message"] == "clear_notification"
    assert calls[-1].data["data"]["tag"].endswith("_cooktop")


async def test_cooktop_acknowledge_stops_repeats(hass: HomeAssistant, oven, freezer):
    calls, _ = oven
    hass.states.async_set("binary_sensor.kitchen_oven_cooktop_status", "on")
    await hass.async_block_till_done()
    await _advance(hass, freezer, timedelta(minutes=31))
    action = _crit(calls)[0].data["data"]["actions"][0]["action"]

    hass.bus.async_fire("mobile_app_notification_action", {"action": action})
    await hass.async_block_till_done()
    await _advance(hass, freezer, timedelta(minutes=40))
    assert len(_crit(calls)) == 1

    # Next time it's turned on, alerts work again
    hass.states.async_set("binary_sensor.kitchen_oven_cooktop_status", "off")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.kitchen_oven_cooktop_status", "on")
    await hass.async_block_till_done()
    await _advance(hass, freezer, timedelta(minutes=31))
    assert len(_crit(calls)) == 2
