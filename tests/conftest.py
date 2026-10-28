"""Shared fixtures."""

from __future__ import annotations

import pytest

from custom_components.appliance_live_activity.config_flow import SECTION_OF, SECTIONS
from homeassistant import data_entry_flow


def sectioned(user_input):
    """Tests write settings flat; the forms group them into sections."""
    if not isinstance(user_input, dict) or not any(k in SECTION_OF for k in user_input):
        return user_input
    nested: dict = {}
    for key, value in user_input.items():
        name = SECTION_OF.get(key)
        if name:
            nested.setdefault(name, {})[key] = value
        else:
            nested[key] = value
    return nested


def suggested_values(result) -> dict:
    """Suggested (pre-filled) values of a form, flattened across sections."""
    values: dict = {}
    for key, value in result["data_schema"].schema.items():
        if str(key) in SECTIONS:
            for inner in value.schema.schema:
                if getattr(inner, "description", None):
                    values[str(inner)] = inner.description.get("suggested_value")
        elif getattr(key, "description", None):
            values[str(key)] = key.description.get("suggested_value")
    return values


@pytest.fixture(autouse=True)
def _wait_for_background_tasks(request, monkeypatch):
    """Wait for config-entry background tasks inside ``async_block_till_done``.

    State changes schedule ``entry.async_create_background_task``. Home
    Assistant's ``async_block_till_done`` does not wait for those by default
    (they are cancelled on unload instead of blocking startup). These tests
    assert on that work, so the wait includes it. Long-lived background tasks
    are not started by this integration.
    """
    if "hass" not in request.fixturenames:
        yield
        return
    hass = request.getfixturevalue("hass")
    original = hass.async_block_till_done

    async def _wait(wait_background_tasks: bool = True):
        await original(wait_background_tasks=wait_background_tasks)

    monkeypatch.setattr(hass, "async_block_till_done", _wait)
    yield


@pytest.fixture(autouse=True)
def _sectioned_forms(monkeypatch):
    original = data_entry_flow.FlowManager.async_configure

    async def async_configure(self, flow_id, user_input=None):
        user_input = sectioned(user_input)
        # Like the frontend: every section of the form is submitted
        flow = self._progress.get(flow_id)
        step = getattr(flow, "cur_step", None) or {}
        schema = step.get("data_schema")
        if isinstance(user_input, dict) and schema is not None:
            for key, value in schema.schema.items():
                if isinstance(value, data_entry_flow.section):
                    user_input.setdefault(str(key), {})
        return await original(self, flow_id, user_input)

    monkeypatch.setattr(data_entry_flow.FlowManager, "async_configure", async_configure)
