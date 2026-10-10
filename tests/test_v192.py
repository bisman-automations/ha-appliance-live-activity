"""v1.9.2: the appliance's device is connected via the GE appliance."""
from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr

from custom_components.appliance_live_activity.const import DOMAIN


async def test_connected_via_ge_appliance(hass: HomeAssistant, enable_custom_integrations):
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    kitchen = ar.async_get(hass).async_create("Kitchen")
    dishwasher = dev_reg.async_get_or_create(
        config_entry_id=ge.entry_id, identifiers={("ge_home", "DW123")}, name="Kitchen Dishwasher"
    )
    dev_reg.async_update_device(dishwasher.id, area_id=kitchen.id)
    hass.states.async_set("sensor.kitchen_dishwasher_operating_mode", "Off")

    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "ge_home", "source_device": dishwasher.id, "appliance_type": "dishwasher",
        "name": "Kitchen Dishwasher", "state_entity": "sensor.kitchen_dishwasher_operating_mode",
        "notification_tag": "kitchen_dishwasher", "devices": [], "ge_discovery": 99,
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    own = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert own.via_device_id == dishwasher.id
    assert own.area_id == kitchen.id

    # A device created by an older version (not linked) is linked on start-up,
    # and an area the user picked is kept
    living = ar.async_get(hass).async_create("Utility")
    dev_reg.async_update_device(own.id, via_device_id=None, area_id=living.id)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    own = dev_reg.async_get(own.id)
    assert own.via_device_id == dishwasher.id
    assert own.area_id == living.id


async def test_manual_appliance_not_linked(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("binary_sensor.garage_door", "off")
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "manual", "appliance_type": "door", "name": "Garage Door",
        "state_entity": "binary_sensor.garage_door", "notification_tag": "garage_door", "devices": [],
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    own = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert own is not None and own.via_device_id is None


async def test_other_brand_linked_via_state_sensor(hass: HomeAssistant, enable_custom_integrations):
    lg = MockConfigEntry(domain="lg_thinq")
    lg.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    washer = dev_reg.async_get_or_create(
        config_entry_id=lg.entry_id, identifiers={("lg_thinq", "WM1")}, name="LG Washer"
    )
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    er.async_get(hass).async_get_or_create(
        "sensor", "lg_thinq", "wm1_state", suggested_object_id="lg_washer_state",
        device_id=washer.id, config_entry=lg,
    )
    hass.states.async_set("sensor.lg_washer_state", "Off")
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "manual", "appliance_type": "washer", "name": "LG Washer",
        "state_entity": "sensor.lg_washer_state", "notification_tag": "lg_washer", "devices": [],
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    own = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert own.via_device_id == washer.id
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.tap_path() == f"/config/devices/device/{washer.id}"


# ---------------------------------------------------------------- oven off
from datetime import timedelta  # noqa: E402

from pytest_homeassistant_custom_component.common import (  # noqa: E402
    async_fire_time_changed,
    async_mock_service,
)


async def test_oven_off_shows_off_then_ends(hass: HomeAssistant, enable_custom_integrations, freezer):
    """Oven used without a cook timer: turning it off updates the Live Activity
    to "Off" (real-world bug: it stayed on the last cooking state)."""
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    me = dr.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "p")}, name="My Phone"
    )
    calls = async_mock_service(hass, "notify", "mobile_app_my_phone")
    for entity, state in (
        ("sensor.oven_current_state", "Off"),
        ("sensor.oven_cook_mode", "Off"),
        ("sensor.oven_cook_time_remaining", "0.0"),
    ):
        hass.states.async_set(entity, state, {"unit_of_measurement": "h"} if "remaining" in entity else {})
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "manual", "appliance_type": "oven", "name": "Kitchen Oven",
        "state_entity": "sensor.oven_current_state", "phase_entity": "sensor.oven_cook_mode",
        "remaining_entity": "sensor.oven_cook_time_remaining",
        "notification_tag": "kitchen_oven", "devices": [me.id],
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("sensor.oven_cook_mode", "Bake")
    hass.states.async_set("sensor.oven_current_state", "Bake")
    await hass.async_block_till_done()
    live = lambda: [c for c in calls if c.data.get("data", {}).get("live_update")]  # noqa: E731
    assert live()[-1].data["data"]["critical_text"] == "Bake"

    freezer.tick(timedelta(minutes=45))
    async_fire_time_changed(hass)
    hass.states.async_set("sensor.oven_cook_mode", "Off")
    hass.states.async_set("sensor.oven_current_state", "Off")
    await hass.async_block_till_done()
    off = live()[-1]
    assert off.data["data"]["critical_text"] == "Off"
    assert off.data["message"] == "Oven off · cooked 45 min"
    assert off.data["data"]["tag"] == "kitchen_oven"
    assert not [c for c in calls if c.data.get("message") == "clear_notification"]

    # Back on within the minute: the same activity carries on (not ended)
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    hass.states.async_set("sensor.oven_cook_mode", "Bake")
    hass.states.async_set("sensor.oven_current_state", "Bake")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=45))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not [c for c in calls if c.data.get("message") == "clear_notification"]
    assert live()[-1].data["data"]["critical_text"] == "Bake"

    # Off again -> "Off", ended a minute later
    hass.states.async_set("sensor.oven_cook_mode", "Off")
    hass.states.async_set("sensor.oven_current_state", "Off")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=61))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert calls[-1].data["message"] == "clear_notification"
    assert calls[-1].data["data"]["tag"] == "kitchen_oven"
