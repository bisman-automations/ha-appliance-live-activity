"""Oven light on while the oven is on (Configure -> Cooking)."""
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.appliance_live_activity.const import DOMAIN

async def _setup(hass: HomeAssistant, light: str | None = "select.kitchen_oven_oven_light", light_state: str = "Off"):
    hass.states.async_set("sensor.oven_current_state", "Off")
    if light and light.startswith("select."):
        hass.states.async_set(light, light_state, {"options": ["Off", "High", "Dim"]})
    elif light:
        hass.states.async_set(light, light_state)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "manual", "appliance_type": "oven", "name": "Kitchen Oven",
            "state_entity": "sensor.oven_current_state", "notification_tag": "kitchen_oven",
            "devices": [],
        },
        options={"oven_light_entity": light} if light else {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _oven(hass: HomeAssistant, state: str) -> None:
    hass.states.async_set("sensor.oven_current_state", state)
    await hass.async_block_till_done()


async def test_light_follows_oven(hass: HomeAssistant, enable_custom_integrations):
    calls = async_mock_service(hass, "select", "select_option")
    await _setup(hass)
    assert calls == []
    await _oven(hass, "Bake")
    assert [c.data["option"] for c in calls] == ["High"]
    hass.states.async_set("select.kitchen_oven_oven_light", "High", {"options": ["Off", "High", "Dim"]})
    await _oven(hass, "Preheat")  # still on: nothing more
    assert len(calls) == 1
    await _oven(hass, "Off")
    assert [c.data["option"] for c in calls] == ["High", "Off"]
    assert calls[-1].data["entity_id"] == "select.kitchen_oven_oven_light"


async def test_light_already_on_left_alone(hass: HomeAssistant, enable_custom_integrations):
    calls = async_mock_service(hass, "select", "select_option")
    await _setup(hass, light_state="Dim")
    await _oven(hass, "Bake")
    await _oven(hass, "Off")
    assert calls == []


async def test_light_turned_off_while_cooking_stays_off(hass: HomeAssistant, enable_custom_integrations):
    calls = async_mock_service(hass, "select", "select_option")
    await _setup(hass)
    await _oven(hass, "Bake")
    hass.states.async_set("select.kitchen_oven_oven_light", "Off", {"options": ["Off", "High", "Dim"]})
    await _oven(hass, "Off")
    assert [c.data["option"] for c in calls] == ["High"]


async def test_no_light_picked_does_nothing(hass: HomeAssistant, enable_custom_integrations):
    calls = async_mock_service(hass, "select", "select_option")
    hass.states.async_set("select.kitchen_oven_oven_light", "Off", {"options": ["Off", "High", "Dim"]})
    await _setup(hass, light=None)
    await _oven(hass, "Bake")
    await _oven(hass, "Off")
    assert calls == []


async def test_unavailable_blip_ignored(hass: HomeAssistant, enable_custom_integrations):
    calls = async_mock_service(hass, "select", "select_option")
    await _setup(hass)
    await _oven(hass, "Bake")
    hass.states.async_set("select.kitchen_oven_oven_light", "High", {"options": ["Off", "High", "Dim"]})
    await _oven(hass, "unavailable")
    await _oven(hass, "Bake")
    assert [c.data["option"] for c in calls] == ["High"]


async def test_switch_light(hass: HomeAssistant, enable_custom_integrations):
    on = async_mock_service(hass, "switch", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")
    await _setup(hass, light="switch.oven_light", light_state="off")
    await _oven(hass, "Bake")
    assert len(on) == 1 and on[0].data["entity_id"] == "switch.oven_light"
    hass.states.async_set("switch.oven_light", "on")
    await _oven(hass, "Off")
    assert len(off) == 1


async def test_restart_mid_cook_still_turns_off(hass: HomeAssistant, enable_custom_integrations):
    calls = async_mock_service(hass, "select", "select_option")
    entry = await _setup(hass)
    await _oven(hass, "Bake")
    hass.states.async_set("select.kitchen_oven_oven_light", "High", {"options": ["Off", "High", "Dim"]})
    await hass.async_block_till_done()
    # Home Assistant restarts (reload) while the oven is on
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(calls) == 1
    await _oven(hass, "Off")
    assert [c.data["option"] for c in calls] == ["High", "Off"]


async def test_option_in_cooking_section(hass: HomeAssistant, enable_custom_integrations):
    async_mock_service(hass, "select", "select_option")
    entry = await _setup(hass, light=None)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    cooking = next(v for k, v in result["data_schema"].schema.items() if str(k) == "cooking")
    keys = {str(k) for k in cooking.schema.schema}
    assert "oven_light_entity" in keys and "oven_light" not in keys


async def test_select_already_dim_counts_as_on(hass: HomeAssistant, enable_custom_integrations):
    calls = async_mock_service(hass, "select", "select_option")
    await _setup(hass, light_state="Off")
    hass.states.async_set("select.kitchen_oven_oven_light", "Dim", {"options": ["Off", "High", "Dim"]})
    await _oven(hass, "Bake")  # Dim is on: left alone, not bumped to High
    assert calls == []
