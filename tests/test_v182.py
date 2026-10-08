"""v1.8.2: settings and sensors only for the appliance types they apply to."""
from __future__ import annotations

from datetime import timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations

from custom_components.appliance_live_activity import config_flow as cf
from custom_components.appliance_live_activity.const import DOMAIN


def _names(appliance_type, current=None, cooktop=False):
    return {cf._key_name(k) for k in cf._behaviour_fields(appliance_type, current or {}, cooktop)}


def test_fields_by_type():
    for t in ("washer", "dishwasher", "refrigerator"):
        assert "leak_entities" in _names(t), t
    for t in ("dryer", "oven", "door"):
        assert "leak_entities" not in _names(t), t
    # ...unless already set up
    assert "leak_entities" in _names("oven", {"leak_entities": ["binary_sensor.x"]})

    assert "speakers" not in _names("oven")
    assert "speakers" in _names("oven", cooktop=True)
    assert "speakers" in _names("dryer") and "speakers" in _names("door")

    assert "quiet_start" not in _names("door")
    assert "quiet_start" in _names("door", {"quiet_start": "22:00:00"})
    assert "quiet_start" in _names("refrigerator")

    laundry = {"move_reminder_minutes", "combine_laundry", "dryer_entity"}
    for t in ("dishwasher", "oven", "refrigerator", "door"):
        assert not laundry & _names(t), t
        assert "supply_entities" not in _names(t) or t == "dishwasher"
    for t in ("washer", "dryer", "dishwasher", "oven"):
        assert not {"fridge_max_temp", "open_delay_seconds", "snooze_minutes"} & _names(t), t
    for t in ("refrigerator", "door"):
        assert not {"finished_alert", "dismiss_minutes", "delay_start", "only_home"} & _names(t), t


async def test_door_sensors(hass: HomeAssistant, enable_custom_integrations):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "manual", "appliance_type": "door", "name": "Garage Door",
        "state_entity": "binary_sensor.garage_door", "notification_tag": "garage_door", "devices": [],
    })
    entry.add_to_hass(hass)
    hass.states.async_set("binary_sensor.garage_door", "off")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.garage_door_status") is not None
    assert hass.states.get("sensor.garage_door_progress") is None
    assert hass.states.get("sensor.garage_door_cycles_this_week") is None


async def test_manual_fridge_asks_for_temperatures(hass: HomeAssistant, enable_custom_integrations):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"appliance_type": "refrigerator", "name": "Garage Fridge"}
    )
    assert result["step_id"] == "entities"
    keys = [str(k) for k in result["data_schema"].schema]
    assert {"fridge_temp_entity", "freezer_temp_entity", "ice_entity"} <= set(keys)
    config = await async_get_translations(hass, "en", "config", [DOMAIN])
    for key in keys:
        assert f"component.{DOMAIN}.config.step.entities.data.{key}" in config, key


# ---------------------------------------------------------------- titles
from homeassistant.helpers import device_registry as dr  # noqa: E402
from pytest_homeassistant_custom_component.common import async_mock_service  # noqa: E402


async def _washer_dryer(hass, washer_options=None, dryer_options=None):
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    me = dr.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "p")}, name="My Phone"
    )
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    for name in ("washer", "dryer"):
        hass.states.async_set(f"sensor.{name}_state", "Off")
        hass.states.async_set(f"sensor.{name}_time_remaining", "0", {"unit_of_measurement": "min"})
    dryer = MockConfigEntry(domain=DOMAIN, data={
        "source": "manual", "appliance_type": "dryer", "name": "Laundry Room Dryer",
        "state_entity": "sensor.dryer_state", "remaining_entity": "sensor.dryer_time_remaining",
        "notification_tag": "laundry_room_dryer", "devices": [me.id],
    }, options=dryer_options or {})
    washer = MockConfigEntry(domain=DOMAIN, data={
        "source": "manual", "appliance_type": "washer", "name": "Laundry Room Washer",
        "state_entity": "sensor.washer_state", "remaining_entity": "sensor.washer_time_remaining",
        "notification_tag": "laundry_room_washer", "devices": [me.id],
        "dryer_entity": "sensor.dryer_state",
    }, options=washer_options or {})
    for entry in (dryer, washer):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return calls, washer, dryer


async def _run(hass, name):
    hass.states.async_set(f"sensor.{name}_time_remaining", "40", {"unit_of_measurement": "min"})
    hass.states.async_set(f"sensor.{name}_state", "Run")
    await hass.async_block_till_done()


def _live_titles(calls):
    return [c.data["title"] for c in calls if c.data.get("data", {}).get("live_update")]


async def test_shared_title_follows_the_appliance(hass: HomeAssistant, enable_custom_integrations):
    calls, washer, dryer = await _washer_dryer(hass)
    await _run(hass, "washer")
    await _run(hass, "dryer")
    assert _live_titles(calls) == ["Laundry Room Washer", "Laundry Room Dryer"]


async def test_shared_title_custom(hass: HomeAssistant, enable_custom_integrations):
    calls, washer, dryer = await _washer_dryer(hass, washer_options={"laundry_title": "Laundry"})
    await _run(hass, "washer")
    await _run(hass, "dryer")
    assert _live_titles(calls) == ["Laundry", "Laundry"]


async def test_custom_and_renamed_titles(hass: HomeAssistant, enable_custom_integrations):
    calls, washer, dryer = await _washer_dryer(
        hass, washer_options={"combine_laundry": False}, dryer_options={"activity_title": "Dryer"}
    )
    # Renaming the integration's washer device in Home Assistant is followed
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, washer.entry_id)})
    dev_reg.async_update_device(device.id, name_by_user="Washer")
    await _run(hass, "washer")
    await _run(hass, "dryer")
    assert _live_titles(calls) == ["Washer", "Dryer"]


def _live_tags(calls, title):
    return [
        c.data["data"]["tag"]
        for c in calls
        if c.data.get("data", {}).get("live_update") and c.data["title"] == title
    ]


async def _finish(hass, name):
    hass.states.async_set(f"sensor.{name}_time_remaining", "0", {"unit_of_measurement": "min"})
    hass.states.async_set(f"sensor.{name}_state", "Finished")
    await hass.async_block_till_done()


async def test_new_wash_while_last_load_dries(hass: HomeAssistant, enable_custom_integrations, freezer):
    calls, washer, dryer = await _washer_dryer(hass)
    cleared = lambda: [c.data["data"]["tag"] for c in calls if c.data.get("message") == "clear_notification"]  # noqa: E731

    # Load 1: washed, then moved to the dryer (same Live Activity)
    await _run(hass, "washer")
    await _finish(hass, "washer")
    await _run(hass, "dryer")
    assert set(_live_tags(calls, "Laundry Room Dryer")) == {"laundry_room_washer"}

    # Load 2 starts washing while load 1 dries: its own Live Activity
    await _run(hass, "washer")
    hass.states.async_set("sensor.washer_time_remaining", "35", {"unit_of_measurement": "min"})
    hass.states.async_set("sensor.dryer_time_remaining", "30", {"unit_of_measurement": "min"})
    await hass.async_block_till_done()
    washer_tags = _live_tags(calls, "Laundry Room Washer")
    assert washer_tags[-1] == "laundry_room_washer_2"
    assert set(_live_tags(calls, "Laundry Room Dryer")) == {"laundry_room_washer"}

    # Load 1 is dry and unloaded; load 2 finishes washing
    await _finish(hass, "dryer")
    await _finish(hass, "washer")
    dryer_coordinator = hass.data[DOMAIN][dryer.entry_id]
    await dryer_coordinator._async_dismiss()  # dryer door opened
    assert cleared() == ["laundry_room_washer"]

    # Load 2 goes into the dryer: it takes over load 2's Live Activity
    calls.clear()
    await _run(hass, "dryer")
    assert _live_tags(calls, "Laundry Room Dryer") == ["laundry_room_washer_2"]
    # ...and the washer's dismiss timer no longer ends it
    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert cleared() == []


async def _finish_cycle(hass, name, cycle):
    hass.states.async_set(f"sensor.{name}_cycle", cycle)
    await _run(hass, name)
    await _finish(hass, name)


def _alerts(calls):
    return [
        (c.data["data"]["tag"], c.data["title"], c.data["message"])
        for c in calls
        if str(c.data.get("title", "")).startswith("✅")
    ]


async def test_one_notification_per_load(hass: HomeAssistant, enable_custom_integrations):
    calls, washer, dryer = await _washer_dryer(hass)
    for entry in (washer, dryer):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "cycle_entity": f"sensor.{entry.data['appliance_type']}_cycle"}
        )
    hass.states.async_set("sensor.washer_cycle", "---")
    hass.states.async_set("sensor.dryer_cycle", "---")
    for entry in (washer, dryer):
        await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    # Towels: washed, then a second load (Darks) washed while towels wait
    await _finish_cycle(hass, "washer", "Towels")
    await _finish_cycle(hass, "washer", "Darks")
    # Towels go into the dryer first, then Darks
    await _finish_cycle(hass, "dryer", "Mixed Load")
    await _finish_cycle(hass, "dryer", "Mixed Load")

    assert _alerts(calls) == [
        ("laundry_room_washer_load_1", "✅ Towels: washed",
         "Laundry Room Washer finished the Towels cycle. Load it into the dryer."),
        ("laundry_room_washer_load_2", "✅ Darks: washed",
         "Laundry Room Washer finished the Darks cycle. Load it into the dryer."),
        ("laundry_room_washer_load_1", "✅ Towels: load complete",
         "Your Towels load has been washed and dried. Please take care of it."),
        ("laundry_room_washer_load_2", "✅ Darks: load complete",
         "Your Darks load has been washed and dried. Please take care of it."),
    ]

    # Something dried on its own (nothing washed waiting)
    await _finish_cycle(hass, "dryer", "Delicates")
    assert _alerts(calls)[-1] == (
        "laundry_room_dryer_load_1", "✅ Delicates: dry",
        "Laundry Room Dryer finished the Delicates cycle. Please take care of it.",
    )
