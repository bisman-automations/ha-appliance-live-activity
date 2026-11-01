"""The Appliances dashboard: its websocket commands and the sidebar panel."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.appliance_live_activity import panel
from custom_components.appliance_live_activity.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

STATE = "sensor.kitchen_dishwasher_operating_mode"


async def _setup(hass: HomeAssistant, state: str = "Off") -> MockConfigEntry:
    hass.states.async_set(STATE, state)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "manual",
            "appliance_type": "dishwasher",
            "name": "Kitchen Dishwasher",
            "state_entity": STATE,
            "notification_tag": "kitchen_dishwasher",
            "devices": [],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _ws(client, **msg):
    await client.send_json_auto_id(msg)
    return await client.receive_json()


async def test_appliances_websocket(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
):
    entry = await _setup(hass)
    entry.runtime_data._history = [[1_790_000_000, 92.0], [1_790_100_000, 88.5]]
    client = await hass_ws_client(hass)
    res = await _ws(client, type=f"{DOMAIN}/appliances")
    assert res["success"]
    (appliance,) = res["result"]["appliances"]
    assert res["result"]["is_admin"] is True
    assert appliance["entry_id"] == entry.entry_id
    assert appliance["name"] == "Kitchen Dishwasher"
    assert appliance["type"] == "dishwasher"
    assert appliance["type_name"] == "Dishwasher"
    assert appliance["door"] is False
    assert appliance["image"] is None
    entities = appliance["entities"]
    assert entities["status"] == "sensor.kitchen_dishwasher_status"
    assert entities["time_left"] == "sensor.kitchen_dishwasher_time_left"
    assert entities["power"] == "switch.kitchen_dishwasher_power"
    assert entities["update_live_activity"].startswith("button.")
    # Newest cycle first.
    assert [c["minutes"] for c in appliance["recent_cycles"]] == [88.5, 92.0]
    assert appliance["alerts"] == []


async def test_set_and_clear_picture(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
):
    entry = await _setup(hass)
    client = await hass_ws_client(hass)
    res = await _ws(
        client, type=f"{DOMAIN}/image", entry_id=entry.entry_id, image_id="abc123"
    )
    assert res["success"]
    assert res["result"] == {
        "image": "/api/image/serve/abc123/512x512",
        "previous_image_id": None,
    }
    res = await _ws(client, type=f"{DOMAIN}/appliances")
    assert res["result"]["appliances"][0]["image"] == "/api/image/serve/abc123/512x512"

    # Replacing it tells the dashboard which picture to delete.
    res = await _ws(
        client, type=f"{DOMAIN}/image", entry_id=entry.entry_id, image_id="def456"
    )
    assert res["result"]["previous_image_id"] == "abc123"
    res = await _ws(client, type=f"{DOMAIN}/image", entry_id=entry.entry_id)
    assert res["result"]["image"] is None
    res = await _ws(client, type=f"{DOMAIN}/appliances")
    assert res["result"]["appliances"][0]["image"] is None

    res = await _ws(client, type=f"{DOMAIN}/image", entry_id="nope", image_id="x")
    assert res["error"]["code"] == "not_found"


async def test_pictures_are_kept_across_restarts(
    hass: HomeAssistant, enable_custom_integrations, hass_storage
):
    hass_storage[panel.IMAGES_STORE] = {
        "version": 1,
        "key": panel.IMAGES_STORE,
        "data": {"images": {"placeholder": "img1"}},
    }
    await _setup(hass)
    assert hass.data[panel.DATA_IMAGES].images == {"placeholder": "img1"}


async def test_only_admins_change_pictures(
    hass: HomeAssistant,
    enable_custom_integrations,
    hass_ws_client,
    hass_read_only_access_token,
):
    entry = await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    res = await _ws(client, type=f"{DOMAIN}/appliances")
    assert res["success"] and res["result"]["is_admin"] is False
    res = await _ws(
        client, type=f"{DOMAIN}/image", entry_id=entry.entry_id, image_id="abc"
    )
    assert res["error"]["code"] == "unauthorized"


async def test_maintenance_alerts(hass: HomeAssistant, enable_custom_integrations):
    entry = await _setup(hass)
    coordinator = entry.runtime_data

    class Supplies:
        def low_supplies(self):
            return [("sensor.rinse_aid", "Rinse aid: low")]

    class Filter:
        status = "dirty"

    coordinator.supplies = Supplies()
    coordinator.filter = Filter()
    summary = panel.appliance_summary(hass, entry)
    assert summary["alerts"] == ["Rinse aid: low", "Filter needs cleaning"]


async def test_panel_registered_and_removed(
    hass: HomeAssistant, enable_custom_integrations
):
    """With a frontend, the panel appears with the first appliance and goes with the last."""
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")
    static = AsyncMock()
    with (
        patch(
            "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths",
            static,
        ),
        patch(
            "homeassistant.components.panel_custom.async_register_panel", AsyncMock()
        ) as register,
        patch("homeassistant.components.frontend.async_remove_panel") as remove,
    ):
        entry = await _setup(hass)
        register.assert_awaited_once()
        kwargs = register.await_args.kwargs
        assert kwargs["frontend_url_path"] == "appliances"
        assert kwargs["webcomponent_name"] == "appliance-live-activity-panel"
        assert kwargs["require_admin"] is False
        assert kwargs["module_url"].startswith(
            "/appliance_live_activity_static/appliance-live-activity-panel.js?v="
        )
        (config,) = static.await_args.args[0]
        assert Path(config.path) == panel.FRONTEND_DIR

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        remove.assert_called_once()
        assert remove.call_args.args[1] == "appliances"


async def test_no_panel_without_frontend(
    hass: HomeAssistant, enable_custom_integrations
):
    with patch(
        "homeassistant.components.panel_custom.async_register_panel", AsyncMock()
    ) as register:
        await _setup(hass)
    register.assert_not_awaited()
