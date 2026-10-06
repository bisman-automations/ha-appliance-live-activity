"""v1.6.1: dishwasher filter reminder in its own field; labels."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.translation import async_get_translations

from custom_components.appliance_live_activity.const import DOMAIN
from custom_components.appliance_live_activity.ge import discover_from_entity_ids

DW = {
    "sensor.kitchen_dishwasher_operating_mode": ("Off", {}),
    "sensor.kitchen_dishwasher_time_remaining": ("0.0", {"unit_of_measurement": "h"}),
    "number.kitchen_dishwasher_pods_remaining_value": ("12", {"unit_of_measurement": "pods"}),
    "sensor.kitchen_dishwasher_reminders_add_rinse_aid": ("False", {}),
    "sensor.kitchen_dishwasher_reminders_clean_filter": ("False", {}),
}


def test_dishwasher_filter_is_not_a_supply():
    found = discover_from_entity_ids(list(DW))
    assert found.filter_entity == "sensor.kitchen_dishwasher_reminders_clean_filter"
    assert found.supply_entities == [
        "number.kitchen_dishwasher_pods_remaining_value",
        "sensor.kitchen_dishwasher_reminders_add_rinse_aid",
    ]


@pytest.fixture
async def dishwasher(hass: HomeAssistant, enable_custom_integrations):
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    me = dr.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id, identifiers={("mobile_app", "p")}, name="My Phone"
    )
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=ge.entry_id, identifiers={("ge_home", "dw")}, name="Kitchen Dishwasher"
    )
    for eid, (state, attrs) in DW.items():
        domain, obj = eid.split(".")
        er.async_get(hass).async_get_or_create(
            domain, "ge_home", obj, suggested_object_id=obj, device_id=device.id, config_entry=ge
        )
        hass.states.async_set(eid, state, attrs)
    return me, device, async_mock_service(hass, "notify", "mobile_app_my_phone")


async def test_filter_moved_out_of_supplies_and_alerts(hass: HomeAssistant, dishwasher):
    me, device, calls = dishwasher
    # As saved by 1.6.0 when the clean-filter sensor was picked as a supply
    entry = MockConfigEntry(domain=DOMAIN, data={
        "source": "ge_home", "source_device": device.id, "appliance_type": "dishwasher",
        "name": "Kitchen Dishwasher", "state_entity": "sensor.kitchen_dishwasher_operating_mode",
        "notification_tag": "kitchen_dishwasher", "devices": [me.id], "ge_discovery": 2,
    }, options={
        "devices": [me.id], "filter_entity": None,
        "supply_entities": [
            "number.kitchen_dishwasher_pods_remaining_value",
            "sensor.kitchen_dishwasher_reminders_add_rinse_aid",
            "sensor.kitchen_dishwasher_reminders_clean_filter",
        ],
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.options["filter_entity"] == "sensor.kitchen_dishwasher_reminders_clean_filter"
    assert entry.options["supply_entities"] == [
        "number.kitchen_dishwasher_pods_remaining_value",
        "sensor.kitchen_dishwasher_reminders_add_rinse_aid",
    ]

    hass.states.async_set("sensor.kitchen_dishwasher_reminders_clean_filter", "True")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.kitchen_dishwasher_reminders_clean_filter", "True", {"x": 1})
    await hass.async_block_till_done()
    alerts = [c for c in calls if str(c.data.get("title", "")).startswith("🧽 Kitchen Dishwasher: clean the filter")]
    assert len(alerts) == 1
    hass.states.async_set("sensor.kitchen_dishwasher_reminders_clean_filter", "False")
    await hass.async_block_till_done()
    assert any(
        c.data.get("message") == "clear_notification" and c.data["data"]["tag"] == "kitchen_dishwasher_filter"
        for c in calls
    )


async def test_every_form_field_has_a_label(hass: HomeAssistant, enable_custom_integrations):
    """Every option field name must have a translated label (no raw keys)."""
    import voluptuous as vol  # noqa: PLC0415

    from custom_components.appliance_live_activity import config_flow  # noqa: PLC0415
    from custom_components.appliance_live_activity.appliance import APPLIANCE_REGISTRY  # noqa: PLC0415

    options = await async_get_translations(hass, "en", "options", [DOMAIN])
    config = await async_get_translations(hass, "en", "config", [DOMAIN])
    for appliance_type in APPLIANCE_REGISTRY:
        for key in config_flow._behaviour_fields(appliance_type, {}, True):
            name = str(key.schema if isinstance(key, vol.Marker) else key)
            where = config_flow.SECTION_OF.get(name)
            path = f"sections.{where}.data.{name}" if where else f"data.{name}"
            assert f"component.{DOMAIN}.options.step.init.{path}" in options, name
            assert f"component.{DOMAIN}.config.step.notify.{path}" in config, name
    for name in config_flow.SECTIONS:
        assert f"component.{DOMAIN}.options.step.init.sections.{name}.name" in options, name
        assert f"component.{DOMAIN}.config.step.notify.sections.{name}.name" in config, name
    for appliance_type in APPLIANCE_REGISTRY:
        for key in config_flow._entity_fields(appliance_type):
            name = str(key.schema if isinstance(key, vol.Marker) else key)
            assert f"component.{DOMAIN}.config.step.reconfigure.data.{name}" in config, name
