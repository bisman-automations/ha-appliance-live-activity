"""The Appliances dashboard: its websocket commands and the sidebar panel.

1.14.0 registered the sidebar panel from every config entry. Home Assistant
rejects a second registration (``ValueError: Overwriting panel appliances
owned by custom``), so only the first appliance loaded. 1.14.1 registered it
once at startup but removed it with the last appliance and never put it
back. These tests load several entries, then reload, unload and add them
again. Each entry is set up on its own: Home Assistant also sets up every
entry of a domain when the integration first loads, and a second setup
while one is still in progress raises OperationNotAllowed.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.appliance_live_activity import panel
from custom_components.appliance_live_activity.const import DOMAIN
from custom_components.appliance_live_activity.coordinator import ApplianceCoordinator
from homeassistant.config_entries import ConfigEntryState
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


# Six appliances, the report that only the first one loaded.
APPLIANCES = (
    "Kitchen Dishwasher",
    "Pantry Dishwasher",
    "Bar Dishwasher",
    "Guest Dishwasher",
    "Basement Dishwasher",
    "Cottage Dishwasher",
)


class _PanelCalls:
    """Stand-in for Home Assistant's panel registration.

    A second registration raises the same ValueError Home Assistant raises.
    A second static path raises too. The real frontend is not running in
    these tests; this is the behaviour that aborted setup.
    """

    def __init__(self, *, already_registered: bool = False) -> None:
        self.register_calls = 0
        self.static_calls = 0
        self.remove_calls = 0
        self.kwargs: dict = {}
        self.static_paths = None
        self.already_registered = already_registered

    async def register(self, hass, **kwargs):
        self.register_calls += 1
        self.kwargs = kwargs
        if self.already_registered or self.register_calls > 1:
            raise ValueError("Overwriting panel appliances owned by custom")

    async def static(self, paths):
        self.static_calls += 1
        self.static_paths = paths
        if self.static_calls > 1:
            raise RuntimeError("static path registered twice")

    def remove(self, hass, url_path, *, warn_if_unknown=False):
        self.remove_calls += 1


@contextmanager
def _patched_frontend(calls: _PanelCalls):
    with (
        patch(
            "homeassistant.components.http.HomeAssistantHTTP.async_register_static_paths",
            calls.static,
        ),
        patch(
            "homeassistant.components.panel_custom.async_register_panel",
            calls.register,
        ),
        patch(
            "homeassistant.components.frontend.async_remove_panel",
            calls.remove,
        ),
    ):
        yield calls


async def _enable_frontend(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "http", {})
    hass.config.components.add("frontend")


def _appliance(hass: HomeAssistant, name: str, index: int) -> MockConfigEntry:
    state = f"sensor.dishwasher_{index}_operating_mode"
    hass.states.async_set(state, "Off")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "manual",
            "appliance_type": "dishwasher",
            "name": name,
            "state_entity": state,
            "notification_tag": f"dishwasher_{index}",
            "devices": [],
        },
    )
    entry.add_to_hass(hass)
    return entry


async def _setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> bool:
    """Set up one entry, after any setup already running has finished.

    Loading the integration sets up every entry of this domain. Calling
    ``async_setup`` again while that entry is ``SETUP_IN_PROGRESS`` raises
    ``OperationNotAllowed``, so an entry Home Assistant already started is
    left to finish and its resulting state is what we report.
    """
    if entry.state is ConfigEntryState.SETUP_IN_PROGRESS:
        await hass.async_block_till_done()
    if entry.state is ConfigEntryState.NOT_LOADED:
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return result
    return entry.state is ConfigEntryState.LOADED


async def _setup_entries(
    hass: HomeAssistant, names: tuple[str, ...] = APPLIANCES
) -> list[MockConfigEntry]:
    """Add every appliance, then set each one up on its own."""
    entries = [_appliance(hass, name, index) for index, name in enumerate(names)]
    # One after another. Awaiting them together races Home Assistant, which
    # is already setting the same entries up while the integration loads.
    results = []
    for entry in entries:
        results.append(await _setup_entry(hass, entry))
    assert results == [True] * len(entries)
    assert [entry.state is ConfigEntryState.LOADED for entry in entries] == [
        True
    ] * len(entries)
    return entries


async def _listed_names(hass: HomeAssistant, hass_ws_client) -> list[str]:
    client = await hass_ws_client(hass)
    res = await _ws(client, type=f"{DOMAIN}/appliances")
    assert res["success"]
    return [item["name"] for item in res["result"]["appliances"]]


def _panel_is_up(hass: HomeAssistant, calls: _PanelCalls) -> None:
    """The page, its script and its commands were registered once and kept."""
    assert calls.register_calls == 1
    assert calls.static_calls == 1
    assert calls.remove_calls == 0
    assert hass.data[panel.DATA_PANEL] is True
    assert hass.data[panel.DATA_STATIC] is True
    assert hass.data[panel.DATA_API] is True


async def test_panel_registered_for_the_whole_run(
    hass: HomeAssistant, enable_custom_integrations
):
    """With a frontend, the panel is registered once and stays after unload."""
    await _enable_frontend(hass)
    calls = _PanelCalls()
    with _patched_frontend(calls):
        entry = await _setup(hass)
        assert calls.kwargs["frontend_url_path"] == "appliances"
        assert calls.kwargs["webcomponent_name"] == "appliance-live-activity-panel"
        assert calls.kwargs["require_admin"] is False
        assert calls.kwargs["module_url"].startswith(
            "/appliance_live_activity_static/appliance-live-activity-panel.js?v="
        )
        (config,) = calls.static_paths
        assert Path(config.path) == panel.FRONTEND_DIR
        _panel_is_up(hass, calls)

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        # Unloading the only appliance must not remove the page. Putting it
        # back would be a second registration, which Home Assistant rejects.
        _panel_is_up(hass, calls)


async def test_six_entries_set_up_together(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
):
    """Every appliance loads, and the dashboard lists all of them."""
    await _enable_frontend(hass)
    calls = _PanelCalls()
    with _patched_frontend(calls):
        await _setup_entries(hass)
        _panel_is_up(hass, calls)
        # Calling registration again (a retried setup) must not raise or
        # register the static path or the commands a second time.
        await panel.async_register_panel(hass, "1.14.2")
        await panel.async_setup_panel_backend(hass)
        _panel_is_up(hass, calls)
        assert sorted(await _listed_names(hass, hass_ws_client)) == sorted(APPLIANCES)


async def test_reload_one_entry_keeps_the_panel_and_every_appliance(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
):
    await _enable_frontend(hass)
    calls = _PanelCalls()
    with _patched_frontend(calls):
        entries = await _setup_entries(hass)
        assert await hass.config_entries.async_reload(entries[0].entry_id)
        await hass.async_block_till_done()
        _panel_is_up(hass, calls)
        assert sorted(await _listed_names(hass, hass_ws_client)) == sorted(APPLIANCES)


async def test_unload_all_but_one_lists_the_remaining_appliance(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
):
    await _enable_frontend(hass)
    calls = _PanelCalls()
    with _patched_frontend(calls):
        entries = await _setup_entries(hass)
        for entry in entries[1:]:
            assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        _panel_is_up(hass, calls)
        assert await _listed_names(hass, hass_ws_client) == ["Kitchen Dishwasher"]

        # 1.14.1 removed the page here: this was the last loaded appliance,
        # and the reload did not register it again.
        assert await hass.config_entries.async_reload(entries[0].entry_id)
        await hass.async_block_till_done()
        _panel_is_up(hass, calls)
        assert await _listed_names(hass, hass_ws_client) == ["Kitchen Dishwasher"]


async def test_unload_all_and_readd(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
):
    await _enable_frontend(hass)
    calls = _PanelCalls()
    with _patched_frontend(calls):
        entries = await _setup_entries(hass)
        for entry in entries:
            assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        _panel_is_up(hass, calls)
        assert await _listed_names(hass, hass_ws_client) == []

        again = []
        for entry in entries:
            again.append(await _setup_entry(hass, entry))
        assert again == [True] * len(entries)
        extra = _appliance(hass, "Laundry Dishwasher", len(entries))
        assert await hass.config_entries.async_setup(extra.entry_id)
        await hass.async_block_till_done()
        _panel_is_up(hass, calls)
        assert sorted(await _listed_names(hass, hass_ws_client)) == sorted(
            (*APPLIANCES, "Laundry Dishwasher")
        )


async def test_failed_setup_does_not_block_the_others(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client, monkeypatch
):
    """One appliance failing setup must not raise, drop the page, or hide the rest."""
    await _enable_frontend(hass)
    calls = _PanelCalls()
    entries = [_appliance(hass, name, index) for index, name in enumerate(APPLIANCES)]
    failed = entries[2]
    original = ApplianceCoordinator.async_setup

    async def _fail_one(self):
        if self.entry.entry_id == failed.entry_id:
            raise RuntimeError("setup failed")
        await original(self)

    monkeypatch.setattr(ApplianceCoordinator, "async_setup", _fail_one)
    with _patched_frontend(calls):
        results = []
        for entry in entries:
            results.append(await _setup_entry(hass, entry))
        assert results == [True, True, False, True, True, True]
        assert failed.state.value == "setup_error"
        assert not hasattr(failed, "runtime_data")
        _panel_is_up(hass, calls)
        assert sorted(await _listed_names(hass, hass_ws_client)) == sorted(
            name for name in APPLIANCES if name != "Bar Dishwasher"
        )


async def test_panel_already_registered_does_not_fail_setup(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client
):
    """Home Assistant already owning the panel is not a setup failure."""
    await _enable_frontend(hass)
    calls = _PanelCalls(already_registered=True)
    with _patched_frontend(calls):
        await _setup_entries(hass)
        assert calls.register_calls == 1
        assert calls.static_calls == 1
        assert hass.data[panel.DATA_PANEL] is True
        assert sorted(await _listed_names(hass, hass_ws_client)) == sorted(APPLIANCES)


async def test_one_bad_summary_does_not_hide_the_others(
    hass: HomeAssistant, enable_custom_integrations, hass_ws_client, monkeypatch
):
    entries = await _setup_entries(hass, APPLIANCES[:2])
    real = panel.appliance_summary

    def _boom(hass, entry):
        if entry.entry_id == entries[0].entry_id:
            raise RuntimeError("summary failed")
        return real(hass, entry)

    monkeypatch.setattr(panel, "appliance_summary", _boom)
    assert await _listed_names(hass, hass_ws_client) == ["Pantry Dishwasher"]


async def test_no_panel_without_frontend(
    hass: HomeAssistant, enable_custom_integrations
):
    with patch(
        "homeassistant.components.panel_custom.async_register_panel", AsyncMock()
    ) as register:
        await _setup(hass)
    register.assert_not_awaited()
