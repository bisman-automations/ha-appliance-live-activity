"""v1.8.1: sections must be Required (the frontend ignores Optional ones);
settings wiped by 1.7.0 / 1.8.0 are restored where setup had found them."""
from __future__ import annotations

import voluptuous as vol
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section

from custom_components.appliance_live_activity import config_flow
from custom_components.appliance_live_activity.const import DOMAIN


def test_sections_are_required():
    for appliance_type in ("washer", "dryer", "dishwasher", "oven", "refrigerator", "door"):
        schema = config_flow._sectioned(config_flow._behaviour_fields(appliance_type, {}, True))
        sections = [k for k, v in schema.schema.items() if isinstance(v, section)]
        assert sections
        for key in sections:
            assert isinstance(key, vol.Required), (appliance_type, key)
        # A frontend that sends every section (as it does for Required ones)
        # with the defaults filled in validates
        payload = {str(k): {} for k in sections}
        assert schema(payload)


async def test_wiped_settings_restored(hass: HomeAssistant, enable_custom_integrations):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "source": "manual", "appliance_type": "washer", "name": "Washer",
            "state_entity": "sensor.washer_state", "notification_tag": "washer", "devices": [],
            "leak_entities": ["binary_sensor.washer_leak"],
            "dryer_entity": "sensor.dryer_state",
        },
        options={"devices": [], "leak_entities": None, "dryer_entity": None, "tts_entity": None},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    cfg = {**entry.data, **entry.options}
    assert cfg["leak_entities"] == ["binary_sensor.washer_leak"]
    assert cfg["dryer_entity"] == "sensor.dryer_state"
    assert entry.options["tts_entity"] is None  # nothing found at setup to restore

    # Only once: a later deliberate clear sticks
    hass.config_entries.async_update_entry(entry, options={**entry.options, "leak_entities": None})
    await hass.async_block_till_done()
    assert {**entry.data, **entry.options}["leak_entities"] is None
