"""Finished Live Activity must be dismissed after the configured delay."""
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

# GE dishwasher, strings exactly as gehomesdk renders them
DW = {
    "sensor.kitchen_dishwasher_operating_mode": "Off",
    "sensor.kitchen_dishwasher_cycle_state": "N/A",
    "sensor.kitchen_dishwasher_dishwasher_cycle_name": "AutoSense",
    "sensor.kitchen_dishwasher_time_remaining": "0.0",
    "binary_sensor.kitchen_dishwasher_door": "off",
}


@pytest.fixture
async def dishwasher(hass: HomeAssistant, enable_custom_integrations):
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=ge.entry_id, identifiers={("ge_home", "dw")}, name="Kitchen Dishwasher"
    )
    for eid, st in DW.items():
        domain, obj = eid.split(".")
        ent_reg.async_get_or_create(domain, "ge_home", obj, suggested_object_id=obj,
                                    device_id=device.id, config_entry=ge)
        _set(hass, eid, st)
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    phone = dev_reg.async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "p")}, name="My Phone"
    )
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "ge_home"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"source_device": device.id})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"devices": [phone.id], "finished_alert": True, "dismiss_minutes": 30}
    )
    await hass.async_block_till_done()
    return result["result"], calls


def _set(hass, eid, state):
    attrs = {"unit_of_measurement": "h"} if eid.endswith("time_remaining") else {}
    hass.states.async_set(eid, state, attrs)


async def _tick(hass, freezer, delta):
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _cleared(calls):
    return [c for c in calls if c.data.get("message") == "clear_notification"
            and not c.data["data"]["tag"].endswith("_done")]


async def _run_cycle(hass, freezer):
    _set(hass, "sensor.kitchen_dishwasher_time_remaining", "1.5")
    _set(hass, "sensor.kitchen_dishwasher_operating_mode", "Cycle Active")
    await hass.async_block_till_done()
    for remaining in ("1.0", "0.5", "0.1", "0.0"):
        _set(hass, "sensor.kitchen_dishwasher_time_remaining", remaining)
        await _tick(hass, freezer, timedelta(minutes=20))
    _set(hass, "sensor.kitchen_dishwasher_operating_mode", "Cycle Complete")
    await hass.async_block_till_done()


async def test_dismiss_after_delay(hass: HomeAssistant, dishwasher, freezer):
    _, calls = dishwasher
    await _run_cycle(hass, freezer)
    assert any(c.data["data"].get("critical_text") == "Done" for c in calls)
    assert _cleared(calls) == []
    await _tick(hass, freezer, timedelta(minutes=31))
    assert len(_cleared(calls)) == 1


async def test_dismiss_survives_idle_states_after_finish(hass: HomeAssistant, dishwasher, freezer):
    """GE goes Cycle Complete -> Control Locked / Off after finishing."""
    _, calls = dishwasher
    await _run_cycle(hass, freezer)
    await _tick(hass, freezer, timedelta(minutes=5))
    _set(hass, "sensor.kitchen_dishwasher_operating_mode", "Control Locked")
    await _tick(hass, freezer, timedelta(minutes=5))
    _set(hass, "sensor.kitchen_dishwasher_operating_mode", "Off")
    await _tick(hass, freezer, timedelta(minutes=25))
    assert len(_cleared(calls)) == 1
    # No phantom "running" activity was started after the cycle ended
    done_at = max(i for i, c in enumerate(calls) if c.data["data"].get("critical_text") == "Done")
    assert not any(c.data["data"].get("live_update") for c in calls[done_at + 1:])


async def test_dismiss_survives_reload(hass: HomeAssistant, dishwasher, freezer):
    entry, calls = dishwasher
    await _run_cycle(hass, freezer)
    await _tick(hass, freezer, timedelta(minutes=10))
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await _tick(hass, freezer, timedelta(minutes=21))
    assert len(_cleared(calls)) == 1
