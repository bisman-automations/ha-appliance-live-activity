"""v1.9.2: the appliance's device is connected via the GE appliance."""
from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.appliance_live_activity.const import DOMAIN


async def test_own_device_linked_to_ge_appliance(hass: HomeAssistant, enable_custom_integrations, monkeypatch):
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    dishwasher = dev_reg.async_get_or_create(
        config_entry_id=ge.entry_id, identifiers={("ge_home", "DW123")},
        connections={("mac", "aa:bb:cc:dd:ee:ff")}, name="Kitchen Dishwasher",
    )
    hass.states.async_set("sensor.kitchen_dishwasher_operating_mode", "Off")
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "ge_home", "source_device": dishwasher.id, "appliance_type": "dishwasher",
        "name": "Kitchen Dishwasher", "state_entity": "sensor.kitchen_dishwasher_operating_mode",
        "notification_tag": "kitchen_dishwasher", "devices": [], "ge_discovery": 99,
    })
    entry.add_to_hass(hass)

    # 1.9.4 put our entities on the GE device
    from homeassistant.helpers import entity_registry as er  # noqa: PLC0415

    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_status", suggested_object_id="kitchen_dishwasher_status",
        device_id=dishwasher.id, config_entry=entry,
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # Our own device again, holding all our entities; GE's device untouched
    own = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert own is not None and own.id != dishwasher.id
    assert own.name == "Kitchen Dishwasher Live Activity"
    ours = er.async_entries_for_config_entry(ent_reg, entry.entry_id)
    assert ours and {e.device_id for e in ours} == {own.id}
    assert ent_reg.async_get("sensor.kitchen_dishwasher_status").device_id == own.id
    assert dev_reg.async_get(dishwasher.id).config_entries == {ge.entry_id}
    assert dev_reg.async_get(dishwasher.id).name == "Kitchen Dishwasher"
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.tap_path() == f"/config/devices/device/{dishwasher.id}"

    # Home Assistant 2026.8+: our device shares the GE device's identifiers and
    # connections, which lists each under the other's "Linked devices"
    from custom_components.appliance_live_activity import device as device_mod  # noqa: PLC0415

    monkeypatch.setattr(device_mod, "LINKED_DEVICES_SUPPORTED", True)
    info = device_mod.own_device_info(coordinator, entry)
    assert info["identifiers"] == {(DOMAIN, entry.entry_id), ("ge_home", "DW123")}
    assert info["connections"] == {("mac", "aa:bb:cc:dd:ee:ff")}


async def test_renamed_device_titles_activity(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("binary_sensor.garage_door", "off")
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "manual", "appliance_type": "door", "name": "Garage Door",
        "state_entity": "binary_sensor.garage_door", "notification_tag": "garage_door", "devices": [],
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    dev_reg = dr.async_get(hass)
    own = dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    dev_reg.async_update_device(own.id, name_by_user="Big Door")
    assert hass.data[DOMAIN][entry.entry_id].display_title == "Big Door"


async def test_manual_appliance_not_linked(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("binary_sensor.garage_door", "off")
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "manual", "appliance_type": "door", "name": "Garage Door",
        "state_entity": "binary_sensor.garage_door", "notification_tag": "garage_door", "devices": [],
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    # No device behind the sensor: just our device, named after the appliance
    own = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert own is not None and own.name == "Garage Door"
    assert own.identifiers == {(DOMAIN, entry.entry_id)}


async def test_other_brand_linked(hass: HomeAssistant, enable_custom_integrations):
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
    assert own is not None and own.name == "LG Washer Live Activity"
    status = er.async_get(hass).async_get("sensor.lg_washer_status")
    assert status is not None and status.device_id == own.id
    assert dev_reg.async_get(washer.id).config_entries == {lg.entry_id}
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
