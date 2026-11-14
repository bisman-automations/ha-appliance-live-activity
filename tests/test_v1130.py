"""v1.13.0: a Power switch and an enum Status, for Home Assistant Matter Hub."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.appliance_mgmt.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er


async def _setup(hass: HomeAssistant, appliance_type: str, state: str):
    hass.states.async_set("sensor.kitchen_dishwasher_operating_mode", state)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "manual",
            "appliance_type": appliance_type,
            "name": "Kitchen Dishwasher",
            "state_entity": "sensor.kitchen_dishwasher_operating_mode",
            "notification_tag": "kitchen_dishwasher",
            "devices": [],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_power_switch_and_enum_status_for_matter_hub(
    hass: HomeAssistant, enable_custom_integrations
):
    await _setup(hass, "dishwasher", "Off")
    status = hass.states.get("sensor.kitchen_dishwasher_status")
    # Matter Hub finds the appliance's state sensor: an enum sensor on the
    # same device whose options include "running" and "paused".
    assert status.attributes["device_class"] == "enum"
    assert {"running", "paused"} <= set(status.attributes["options"])
    assert status.state == "idle"
    power = hass.states.get("switch.kitchen_dishwasher_power")
    assert power.state == "off"
    ent_reg = er.async_get(hass)
    assert (
        ent_reg.async_get("switch.kitchen_dishwasher_power").device_id
        == ent_reg.async_get("sensor.kitchen_dishwasher_status").device_id
    )

    hass.states.async_set("sensor.kitchen_dishwasher_operating_mode", "Cycle Active")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kitchen_dishwasher_status").state == "running"
    assert hass.states.get("switch.kitchen_dishwasher_power").state == "on"

    hass.states.async_set("sensor.kitchen_dishwasher_operating_mode", "Pause")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.kitchen_dishwasher_status").state == "paused"
    assert hass.states.get("switch.kitchen_dishwasher_power").state == "on"

    # GE appliances can't be started or stopped remotely.
    for service in ("turn_on", "turn_off"):
        with pytest.raises(HomeAssistantError, match="can't be started or stopped"):
            await hass.services.async_call(
                "switch",
                service,
                {"entity_id": "switch.kitchen_dishwasher_power"},
                blocking=True,
            )


async def test_no_power_switch_for_doors_and_ovens(
    hass: HomeAssistant, enable_custom_integrations
):
    await _setup(hass, "oven", "Off")
    assert hass.states.async_entity_ids("switch") == []
    # Ovens still get the enum Status.
    status = hass.states.get("sensor.kitchen_dishwasher_status")
    assert status.attributes["device_class"] == "enum"


async def test_door_status_is_not_an_enum(
    hass: HomeAssistant, enable_custom_integrations
):
    hass.states.async_set("binary_sensor.garage_door", "off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "manual",
            "appliance_type": "door",
            "name": "Garage Door",
            "state_entity": "binary_sensor.garage_door",
            "notification_tag": "garage_door",
            "devices": [],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert "device_class" not in hass.states.get("sensor.garage_door_status").attributes
    assert hass.states.async_entity_ids("switch") == []
