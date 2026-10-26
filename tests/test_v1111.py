"""1.11.1: entity IDs, device lookups and timers on current Home Assistant."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.appliance_live_activity.const import DOMAIN
from custom_components.appliance_live_activity.device import own_device
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


def _ge_dishwasher(hass: HomeAssistant) -> MockConfigEntry:
    """A dishwasher set up from its GE Home device (so our device is linked)."""
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    dishwasher = dr.async_get(hass).async_get_or_create(
        config_entry_id=ge.entry_id,
        identifiers={("ge_home", "DW123")},
        name="Kitchen Dishwasher",
    )
    hass.states.async_set("sensor.kitchen_dishwasher_operating_mode", "Off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "ge_home",
            "source_device": dishwasher.id,
            "appliance_type": "dishwasher",
            "name": "Kitchen Dishwasher",
            "state_entity": "sensor.kitchen_dishwasher_operating_mode",
            "notification_tag": "kitchen_dishwasher",
            "devices": [],
            "ge_discovery": 99,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_linked_entity_ids_are_not_doubled(
    hass: HomeAssistant, enable_custom_integrations
):
    """Our device is "Kitchen Dishwasher Live Activity" when linked. Since
    Home Assistant 2026.7 that name was put in front of every new entity ID
    (sensor.kitchen_dishwasher_live_activity_kitchen_dishwasher_status)."""
    entry = _ge_dishwasher(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert own_device(hass, entry).name == "Kitchen Dishwasher Live Activity"
    ids = {
        e.entity_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    assert {
        "sensor.kitchen_dishwasher_status",
        "sensor.kitchen_dishwasher_progress",
        "sensor.kitchen_dishwasher_time_left",
        "event.kitchen_dishwasher_cycle",
        "button.kitchen_dishwasher_update_live_activity",
    } <= ids
    assert not any("live_activity_kitchen" in entity_id for entity_id in ids)


async def test_existing_entity_ids_are_kept(
    hass: HomeAssistant, enable_custom_integrations
):
    """The suggested ID is only for new entities: one the user renamed stays."""
    entry = _ge_dishwasher(hass)
    er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_status",
        suggested_object_id="dishwasher_now",
        config_entry=entry,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.dishwasher_now") is not None
    assert hass.states.get("sensor.kitchen_dishwasher_status") is None


async def test_unload_cancels_pending_notification_clears(
    hass: HomeAssistant, enable_custom_integrations
):
    """A "resolved" notification is removed two minutes later; unloading the
    entry first cancels that, rather than leaving a timer behind."""
    from custom_components.appliance_live_activity.notify import async_resolve  # noqa: PLC0415

    entry = _ge_dishwasher(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]

    await async_resolve(
        hass, coordinator, tag="kitchen_dishwasher_door", title="t", message="m"
    )
    assert len(coordinator.pending_clears) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert coordinator.pending_clears == set()
