"""Config flow (GE path) + Live Activity lifecycle."""
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
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.appliance_live_activity.const import DOMAIN

PREFIX = "laundry_room_washer"
WASHER_ENTITIES = {
    ("sensor", "state"): "Off",
    ("sensor", "sub_cycle"): "---",
    ("sensor", "cycle"): "Towels Or Sheets",
    ("sensor", "time_remaining"): "0",
    ("sensor", "delay_time_remaining"): "0",
    ("binary_sensor", "end_of_cycle"): "off",
    ("binary_sensor", "door"): "off",
}


@pytest.fixture
async def setup_devices(hass: HomeAssistant, enable_custom_integrations):
    """A GE washer device with entities, and a phone with a notify service."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    ge_entry = MockConfigEntry(domain="ge_home")
    ge_entry.add_to_hass(hass)
    washer = dev_reg.async_get_or_create(
        config_entry_id=ge_entry.entry_id, identifiers={("ge_home", "washer1")}, name="Laundry Room Washer"
    )
    for (domain, suffix), state in WASHER_ENTITIES.items():
        ent_reg.async_get_or_create(
            domain, "ge_home", f"washer1_{suffix}",
            suggested_object_id=f"{PREFIX}_{suffix}", device_id=washer.id, config_entry=ge_entry,
        )
        attrs = {"unit_of_measurement": "min"} if suffix == "time_remaining" else {}
        hass.states.async_set(f"{domain}.{PREFIX}_{suffix}", state, attrs)

    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    phone = dev_reg.async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "phone1")}, name="My Phone"
    )
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    return washer, phone, calls


async def _create_entry(hass, washer, phone):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "ge_home"})
    assert result["step_id"] == "ge_home"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"source_device": washer.id, "appliance_type": "auto"}
    )
    assert result["step_id"] == "notify"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"devices": [phone.id], "finished_alert": True, "dismiss_minutes": 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["appliance_type"] == "washer"
    assert data["name"] == "Laundry Room Washer"
    assert data["remaining_entity"] == f"sensor.{PREFIX}_time_remaining"
    await hass.async_block_till_done()
    return result["result"]


def _set(hass, suffix, state, domain="sensor"):
    attrs = {"unit_of_measurement": "min"} if suffix == "time_remaining" else {}
    hass.states.async_set(f"{domain}.{PREFIX}_{suffix}", state, attrs)


async def test_ge_flow_and_lifecycle(hass: HomeAssistant, setup_devices):
    washer, phone, calls = setup_devices
    await _create_entry(hass, washer, phone)
    assert calls == []  # idle: nothing sent

    # Cycle starts
    _set(hass, "time_remaining", "60")
    _set(hass, "state", "Run")
    _set(hass, "sub_cycle", "Wash")
    await hass.async_block_till_done()
    assert calls, "running update expected"
    data = calls[-1].data["data"]
    assert data["live_update"] is True
    assert data["chronometer"] is True and data["when_relative"] is True
    assert calls[-1].data["title"] == "Laundry Room Washer"
    sent = len(calls)

    # Countdown ticks along as expected -> no new push
    _set(hass, "time_remaining", "59")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=1))
    await hass.async_block_till_done()
    assert len(calls) == sent

    # Phase change -> push
    _set(hass, "sub_cycle", "Rinse")
    await hass.async_block_till_done()
    assert len(calls) == sent + 1
    assert calls[-1].data["data"]["critical_text"] == "Rinse"
    sent = len(calls)

    # Estimate jumps 15 min -> push
    _set(hass, "time_remaining", "44")
    await hass.async_block_till_done()
    assert len(calls) == sent + 1
    sent = len(calls)

    # Pause -> push without countdown
    _set(hass, "state", "Paused")
    await hass.async_block_till_done()
    assert calls[-1].data["data"]["critical_text"] == "Paused"
    assert "chronometer" not in calls[-1].data["data"]
    _set(hass, "state", "Run")
    await hass.async_block_till_done()
    sent = len(calls)

    # Finish: end-of-cycle on -> Done + finished alert, once
    _set(hass, "time_remaining", "0")
    _set(hass, "end_of_cycle", "on", domain="binary_sensor")
    await hass.async_block_till_done()
    new = calls[sent:]
    assert [c.data["data"].get("critical_text") for c in new if c.data["data"].get("live_update")] == ["Done"]
    assert any("finished" in c.data.get("title", "") for c in new)
    sent = len(calls)

    # Staying finished does not re-send every minute
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=3))
    await hass.async_block_till_done()
    assert len(calls) == sent

    # Door opens -> Live Activity cleared
    _set(hass, "door", "on", domain="binary_sensor")
    await hass.async_block_till_done()
    assert calls[-1].data["message"] == "clear_notification"


async def test_cancelled_cycle_clears(hass: HomeAssistant, setup_devices):
    washer, phone, calls = setup_devices
    await _create_entry(hass, washer, phone)
    _set(hass, "time_remaining", "50")
    _set(hass, "state", "Run")
    await hass.async_block_till_done()
    _set(hass, "state", "Off")
    await hass.async_block_till_done()
    assert calls[-1].data["message"] == "clear_notification"
    assert not any("finished" in c.data.get("title", "") for c in calls)


async def test_bundled_blueprint_installed(hass: HomeAssistant, setup_devices):
    import os

    washer, phone, _ = setup_devices
    await _create_entry(hass, washer, phone)
    path = hass.config.path("blueprints", "automation", DOMAIN, "ge_appliance_live_activity.yaml")
    assert os.path.exists(path)


async def test_options_flow(hass: HomeAssistant, setup_devices):
    washer, phone, _ = setup_devices
    entry = await _create_entry(hass, washer, phone)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"devices": [phone.id], "finished_alert": False, "dismiss_minutes": 10}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["finished_alert"] is False


async def test_manual_flow(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("sensor.lg_washer_state", "Off")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["step_id"] == "manual"  # no GE devices -> straight to manual
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"appliance_type": "washer", "name": "LG Washer"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"state_entity": "sensor.lg_washer_state"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"devices": []})
    assert result["type"] is FlowResultType.CREATE_ENTRY
