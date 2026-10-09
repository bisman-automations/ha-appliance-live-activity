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
