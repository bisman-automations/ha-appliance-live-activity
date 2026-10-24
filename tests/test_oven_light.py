"""Oven light on while the oven is on (Configure -> Cooking)."""
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.appliance_live_activity.const import DOMAIN
from custom_components.appliance_live_activity.ge import discover_from_entity_ids

GE_OVEN = [
    "sensor.kitchen_oven_current_state",
    "sensor.kitchen_oven_cook_mode",
    "sensor.kitchen_oven_cook_time_remaining",
    "select.kitchen_oven_oven_light",
]


def test_ge_discovers_oven_light():
    assert discover_from_entity_ids(GE_OVEN).oven_light_entity == "select.kitchen_oven_oven_light"


def test_ge_double_oven_light_per_cavity():
    ids = [
        "sensor.range_upper_oven_current_state",
        "sensor.range_lower_oven_current_state",
        "select.range_upper_oven_light",
        "select.range_lower_oven_light",
    ]
    assert discover_from_entity_ids(ids, "upper").oven_light_entity == "select.range_upper_oven_light"
    assert discover_from_entity_ids(ids, "lower").oven_light_entity == "select.range_lower_oven_light"


def test_ge_washer_has_no_oven_light():
    ids = ["sensor.washer_sub_cycle", "sensor.washer_machine_state", "select.washer_oven_light"]
    assert discover_from_entity_ids(ids).oven_light_entity is None


async def _setup(hass: HomeAssistant, light: str = "select.kitchen_oven_oven_light", enabled: bool = True, light_state: str = "Off"):
    hass.states.async_set("sensor.oven_current_state", "Off")
    if light.startswith("select."):
        hass.states.async_set(light, light_state, {"options": ["Off", "High", "Dim"]})
    else:
        hass.states.async_set(light, light_state)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "manual", "appliance_type": "oven", "name": "Kitchen Oven",
            "state_entity": "sensor.oven_current_state", "notification_tag": "kitchen_oven",
            "devices": [], "oven_light_entity": light,
        },
        options={"oven_light": enabled},
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


async def test_disabled_does_nothing(hass: HomeAssistant, enable_custom_integrations):
    calls = async_mock_service(hass, "select", "select_option")
    await _setup(hass, enabled=False)
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
    entry = await _setup(hass, enabled=False)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    cooking = next(v for k, v in result["data_schema"].schema.items() if str(k) == "cooking")
    keys = {str(k) for k in cooking.schema.schema}
    assert {"oven_light", "oven_light_entity"} <= keys
    # The discovered / stored light is pre-filled
    cooking_key = next(k for k in result["data_schema"].schema if str(k) == "cooking")
    light_key = next(k for k in cooking.schema.schema if str(k) == "oven_light_entity")
    assert (cooking_key.description or {}).get("suggested_value", {}).get("oven_light_entity") == "select.kitchen_oven_oven_light" or (
        (light_key.description or {}).get("suggested_value") == "select.kitchen_oven_oven_light"
    )
