"""2.0.0: Appliance Live Activity (``appliance_live_activity``) moves to Appliance Mgmt."""

from __future__ import annotations

from pathlib import Path

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.appliance_mgmt.const import DOMAIN
from custom_components.appliance_mgmt.migrate import (
    ISSUE_OLD_FOLDER,
    MIGRATED_FROM,
    OLD_DOMAIN,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.setup import async_setup_component

DATA = {
    "source": "manual",
    "appliance_type": "oven",
    "name": "Kitchen Oven",
    "state_entity": "sensor.oven_current_state",
    "notification_tag": "kitchen_oven",
    "devices": [],
}


def _old_entry(hass: HomeAssistant, hass_storage) -> MockConfigEntry:
    hass.states.async_set("sensor.oven_current_state", "Off")
    old = MockConfigEntry(
        domain=OLD_DOMAIN,
        title="Kitchen Oven",
        unique_id="kitchen_oven",
        data=DATA,
        options={"dismiss_minutes": 7},
        minor_version=2,
    )
    old.add_to_hass(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    device = dev_reg.async_get_or_create(
        config_entry_id=old.entry_id,
        identifiers={(OLD_DOMAIN, old.entry_id)},
        name="Kitchen Oven",
    )
    dev_reg.async_update_device(device.id, name_by_user="Big Oven")
    ent_reg.async_get_or_create(
        "sensor",
        OLD_DOMAIN,
        f"{old.entry_id}_status",
        suggested_object_id="kitchen_oven_status",
        config_entry=old,
        device_id=device.id,
    )
    hass_storage[f"{OLD_DOMAIN}_{old.entry_id}"] = {
        "version": 1,
        "key": f"{OLD_DOMAIN}_{old.entry_id}",
        "data": {"total_minutes": 42, "history": []},
    }
    hass_storage[f"{OLD_DOMAIN}.images"] = {
        "version": 1,
        "key": f"{OLD_DOMAIN}.images",
        "data": {"images": {old.entry_id: "img123"}},
    }
    return old


async def test_moves_everything(
    hass: HomeAssistant, enable_custom_integrations, hass_storage
):
    old = _old_entry(hass, hass_storage)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(old.entry_id) is None
    (entry,) = hass.config_entries.async_entries(DOMAIN)
    assert entry.title == "Kitchen Oven"
    assert entry.unique_id == "kitchen_oven"
    assert entry.options["dismiss_minutes"] == 7
    assert MIGRATED_FROM not in entry.data
    assert entry.data["state_entity"] == "sensor.oven_current_state"

    ent_reg = er.async_get(hass)
    status = ent_reg.async_get("sensor.kitchen_oven_status")
    assert status.platform == DOMAIN
    assert status.config_entry_id == entry.entry_id
    assert status.unique_id == f"{entry.entry_id}_status"
    assert hass.states.get("sensor.kitchen_oven_status") is not None
    # No second status sensor was registered
    assert not [
        e
        for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id)
        if e.entity_id.startswith("sensor.kitchen_oven_status_")
    ]

    device = dr.async_get(hass).async_get(status.device_id)
    assert (DOMAIN, entry.entry_id) in device.identifiers
    assert device.name_by_user == "Big Oven"

    assert hass.data[f"{DOMAIN}_images"].images[entry.entry_id] == "img123"
    assert entry.runtime_data._total_minutes == 42


async def test_waits_for_old_folder(
    hass: HomeAssistant, enable_custom_integrations, hass_storage, tmp_path: Path
):
    hass.config.config_dir = str(tmp_path)
    folder = tmp_path / "custom_components" / OLD_DOMAIN
    folder.mkdir(parents=True)
    old = _old_entry(hass, hass_storage)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    # Nothing moved while the old code is installed
    assert hass.config_entries.async_get_entry(old.entry_id) is not None
    assert hass.config_entries.async_entries(DOMAIN) == []
    assert ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_OLD_FOLDER)

    from custom_components.appliance_mgmt.repairs import async_create_fix_flow

    flow = await async_create_fix_flow(hass, ISSUE_OLD_FOLDER, None)
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["step_id"] == "confirm"
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"
    assert not folder.exists()
