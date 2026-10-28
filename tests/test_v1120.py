"""1.12.0: entity names, device lookup, diagnostics, runtime data, migrations."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.appliance_live_activity import GE_DISCOVERY_VERSION
from custom_components.appliance_live_activity.const import CONFIG_MINOR_VERSION, DOMAIN
from custom_components.appliance_live_activity.device import (
    SUGGESTED_ENTITY_NAMES,
    devices_sharing_identifier,
    own_device,
)
from custom_components.appliance_live_activity.diagnostics import (
    TO_REDACT,
    async_get_config_entry_diagnostics,
)
from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er


def test_suggested_entity_names_match_translations():
    """The slug source and strings.json name the entity the same way."""
    import json
    from pathlib import Path

    strings = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "custom_components"
            / "appliance_live_activity"
            / "strings.json"
        ).read_text()
    )
    for (platform, key), name in SUGGESTED_ENTITY_NAMES.items():
        assert strings["entity"][platform][key]["name"] == name, (platform, key)


def _phone(hass: HomeAssistant):
    """A Companion-app phone named with a placeholder, reported as home."""
    phone_entry = MockConfigEntry(domain="mobile_app")
    phone_entry.add_to_hass(hass)
    phone = dr.async_get(hass).async_get_or_create(
        config_entry_id=phone_entry.entry_id,
        identifiers={("mobile_app", "phone-1")},
        name="My Phone",
    )
    er.async_get(hass).async_get_or_create(
        "device_tracker",
        "mobile_app",
        "phone-1",
        suggested_object_id="my_phone",
        device_id=phone.id,
        config_entry=phone_entry,
    )
    hass.states.async_set("device_tracker.my_phone", "home")
    return phone


def _washer(hass: HomeAssistant, phone_id: str, *, minor_version: int = 1):
    hass.states.async_set(
        "sensor.washer_state",
        "Off",
        {
            "entity_picture": "/api/media/local/photo.jpg?token=secret",
            "entity_picture_local": "/local/photo.jpg",
            "device_class": "enum",
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        minor_version=minor_version,
        data={
            "source": "manual",
            "appliance_type": "washer",
            "name": "Laundry Room Washer",
            "state_entity": "sensor.washer_state",
            "notification_tag": "laundry_room_washer",
            "devices": [phone_id],
            "leak_entities": ["binary_sensor.washer_leak"],
            "activity_title": "Washer at home",
        },
        options={"devices": [phone_id], "leak_entities": None},
    )
    entry.add_to_hass(hass)
    return entry


async def test_existing_entity_ids_survive_has_entity_name(
    hass: HomeAssistant, enable_custom_integrations
):
    """Unique ids are unchanged, so entity ids already in the registry stay.

    A new entity on a linked appliance uses the short id
    (``sensor.kitchen_dishwasher_progress``). A doubled id stored by an
    earlier install is not renamed.
    """
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
    registry = er.async_get(hass)
    # What 1.11.0 and earlier stored. The user may also have renamed one.
    preexisting = {
        ("sensor", f"{entry.entry_id}_status", "sensor.dishwasher_now"),
        ("event", f"{entry.entry_id}_event", "event.dishwasher_events"),
        (
            "button",
            f"{entry.entry_id}_update_live_activity",
            "button.dishwasher_refresh",
        ),
        # The doubled id Home Assistant 2026.7–2026.10 created. Left as stored.
        (
            "sensor",
            f"{entry.entry_id}_time_left",
            "sensor.kitchen_dishwasher_live_activity_kitchen_dishwasher_time_left",
        ),
    }
    for domain, unique_id, entity_id in preexisting:
        registry.async_get_or_create(
            domain,
            DOMAIN,
            unique_id,
            suggested_object_id=entity_id.split(".", 1)[1],
            config_entry=entry,
        )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for domain, unique_id, entity_id in preexisting:
        assert registry.async_get_entity_id(domain, DOMAIN, unique_id) == entity_id
        assert hass.states.get(entity_id) is not None

    # Progress was not in the registry. The suggestion is the short id.
    progress = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_progress"
    )
    assert progress == "sensor.kitchen_dishwasher_progress"
    assert hass.states.get("sensor.kitchen_dishwasher_time_left") is None
    assert hass.states.get(
        "sensor.kitchen_dishwasher_live_activity_kitchen_dishwasher_time_left"
    )

    status = registry.async_get("sensor.dishwasher_now")
    assert status is not None
    assert status.unique_id == f"{entry.entry_id}_status"
    assert status.has_entity_name is True
    assert status.translation_key == "status"


async def test_device_lookup_does_not_call_async_get_device(
    hass: HomeAssistant, enable_custom_integrations, monkeypatch
):
    """Shared identifiers must be resolved with the entry, not async_get_device.

    Home Assistant 2026.10 raises RuntimeError from that call when it cannot
    tell which integration made it. Setup and our lookups must not use it.
    """
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    dev_reg = dr.async_get(hass)
    dishwasher = dev_reg.async_get_or_create(
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
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("async_get_device")

    monkeypatch.setattr(type(dev_reg), "async_get_device", _boom)
    own = own_device(hass, entry)
    assert own is not None
    assert own.config_entry_id == entry.entry_id
    shared = devices_sharing_identifier(hass, ("ge_home", "DW123"))
    assert {device.id for device in shared} == {dishwasher.id, own.id}


async def test_diagnostics_redact_personal_data(
    hass: HomeAssistant, enable_custom_integrations
):
    """Entry data, pictures, phone names and home presence are redacted."""
    phone = _phone(hass)
    from pytest_homeassistant_custom_component.common import async_mock_service  # noqa: PLC0415

    async_mock_service(hass, "notify", "mobile_app_my_phone")
    entry = _washer(hass, phone.id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert "entity_picture" in TO_REDACT
    assert "entity_picture_local" in TO_REDACT
    assert result["entry"]["title"] == REDACTED
    assert result["entry"]["data"]["name"] == REDACTED
    assert result["entry"]["data"]["devices"] == REDACTED
    assert result["entry"]["data"]["activity_title"] == REDACTED
    # The sensor the bug report is about is still named.
    assert result["entry"]["data"]["state_entity"] == "sensor.washer_state"
    phone_info = result["phones"][phone.id]
    assert phone_info["name"] == REDACTED
    assert phone_info["home"] == REDACTED
    assert phone_info["notify_services"] == REDACTED
    attributes = result["entities"]["sensor.washer_state"]["attributes"]
    assert attributes["entity_picture"] == REDACTED
    assert attributes["entity_picture_local"] == REDACTED
    assert attributes["device_class"] == "enum"
    assert result["appliance_type"] == "washer"
    assert result["data"]["status"] == "idle"


async def test_services_registered_once_and_forward_failure_cleans_up(
    hass: HomeAssistant, enable_custom_integrations, monkeypatch
):
    """Services exist for the whole process. A failed platform forward leaves
    no coordinator and no timer."""
    phone = _phone(hass)
    entry = _washer(hass, phone.id, minor_version=CONFIG_MINOR_VERSION)
    # Drop the wiped-option shape; this entry is already at the current minor.
    hass.config_entries.async_update_entry(entry, options={"devices": [phone.id]})

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("platform failed")

    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", _boom)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not hasattr(entry, "runtime_data")
    # async_setup registered the service before the entry failed. A failed
    # entry stays in SETUP_ERROR; the service is what a later appliance uses.
    assert hass.services.has_service(DOMAIN, "update")

    monkeypatch.undo()
    second = _washer(hass, phone.id, minor_version=CONFIG_MINOR_VERSION)
    hass.config_entries.async_update_entry(second, options={"devices": [phone.id]})
    # The helper always uses the same entity ids. Give this entry its own.
    hass.config_entries.async_update_entry(
        second,
        data={
            **second.data,
            "state_entity": "sensor.washer_two_state",
            "notification_tag": "washer_two",
            "name": "Washer Two",
        },
    )
    hass.states.async_set("sensor.washer_two_state", "Off")
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    assert second.runtime_data is not None
    await hass.services.async_call(
        DOMAIN, "update", {"entry_id": second.entry_id}, blocking=True
    )
    await hass.services.async_call(
        DOMAIN, "update", {"entry_id": "not-an-appliance"}, blocking=True
    )

    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
    # Registered in async_setup, not removed when the last appliance unloads.
    assert hass.services.has_service(DOMAIN, "update")


async def test_migrations_run_once(hass: HomeAssistant, enable_custom_integrations):
    """Minor version 1 is repaired once. A later clear survives a reload."""
    phone = _phone(hass)
    ge = MockConfigEntry(domain="ge_home")
    ge.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=ge.entry_id,
        identifiers={("ge_home", "DW123")},
        name="Kitchen Dishwasher",
    )
    hass.states.async_set("sensor.kitchen_dishwasher_operating_mode", "Off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        data={
            "source": "ge_home",
            "source_device": device.id,
            "appliance_type": "dishwasher",
            "name": "Kitchen Dishwasher",
            "state_entity": "sensor.kitchen_dishwasher_operating_mode",
            "notification_tag": "kitchen_dishwasher",
            "devices": [phone.id],
            "ge_discovery": 1,
            "leak_entities": ["binary_sensor.washer_leak"],
        },
        options={"devices": [phone.id], "leak_entities": None},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == CONFIG_MINOR_VERSION
    assert entry.data["ge_discovery"] == GE_DISCOVERY_VERSION
    assert entry.data["options_restored"] == 1
    assert "leak_entities" not in entry.options
    assert entry.runtime_data is not None

    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "leak_entities": None}
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.minor_version == CONFIG_MINOR_VERSION
    assert entry.options["leak_entities"] is None


async def test_resolved_notification_timer_is_unloaded_with_the_entry(
    hass: HomeAssistant, enable_custom_integrations
):
    """The two-minute clear is an entry unload callback, not a bare timer."""
    from custom_components.appliance_live_activity.notify import async_resolve  # noqa: PLC0415

    phone = _phone(hass)
    entry = _washer(hass, phone.id, minor_version=CONFIG_MINOR_VERSION)
    hass.config_entries.async_update_entry(entry, options={"devices": [phone.id]})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    before = len(entry._on_unload or [])

    await async_resolve(
        hass,
        entry.runtime_data,
        tag="laundry_room_washer_door",
        title="t",
        message="m",
    )
    assert len(entry.runtime_data.pending_clears) == 1
    assert len(entry._on_unload or []) == before + 1

    coordinator = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert coordinator.pending_clears == set()
    # runtime_data is removed by Home Assistant after a successful unload.
    assert not hasattr(entry, "runtime_data")
