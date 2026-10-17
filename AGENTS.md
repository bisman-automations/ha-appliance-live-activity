# Working on this repo

Instructions for AI coding agents (Claude, Copilot, etc.) and humans. `CLAUDE.md`
imports this file, so keep the rules here.

## What this is

**Appliance Live Activity** (`appliance_live_activity`): a HACS custom integration
that sends iOS Live Activities and alerts (via the Home Assistant Companion app,
`mobile_app` notify) for appliances: GE Home / SmartHQ (`ge_home`) appliances
first, plus any other brand or a plain door/contact sensor set up manually.

- Repo: `bisman-automations/ha-appliance-live-activity` (owner `@donavanbecker`).
- Minimum Home Assistant: `hacs.json` → `homeassistant` (currently 2026.7.0).
  Code must keep working from that version through the current dev release.

## Ground rules

- **Everything lives in the integration.** No blueprints, helpers or YAML for
  users to install. Add a blueprint only if something truly can't be done in
  the integration.
- **No personal details in the repo**: no account numbers, serial numbers,
  service IDs, addresses, device IDs or phone names in code, tests, README or
  CHANGELOG. Use placeholders ("Kitchen Oven", "My Phone", `DW123`).
- Don't change entity unique IDs or entity IDs; dashboards and automations
  depend on them. Moving entities between devices must keep IDs.
- Existing config entries must keep working: when stored data changes shape,
  migrate or backfill it in `async_setup_entry` (see `_async_backfill_ge`,
  `_async_restore_wiped`, and `GE_DISCOVERY_VERSION`, which is defined in both
  `__init__.py` and `config_flow.py`).

## Releases

- The version is `custom_components/appliance_live_activity/manifest.json` →
  `version`. Each release bumps it and adds a `## x.y.z` section at the top of
  `CHANGELOG.md` (user-facing: what changed and why, with **bold lead-ins**
  like the existing entries).
- If the manifest version hasn't been published yet (no `vX.Y.Z` tag), add to
  that version's changelog section instead of bumping again.
- Every push to `main` refreshes a **draft** GitHub release for the manifest
  version (`.github/workflows/draft-release.yml`). The maintainer publishes it;
  agents never create tags or publish releases.
- Keep history to roughly one commit per release; group related work into one
  commit. Never force-push or rewrite published history without asking.
- `.github/workflows/validate.yml` runs hassfest, the HACS action and pytest
  on every push. Keep it green.

## Layout (`custom_components/appliance_live_activity/`)

| File | Role |
| --- | --- |
| `__init__.py` | Setup, migrations/backfills, device linking, platforms, services |
| `config_flow.py` | Setup (GE discovery or manual), Reconfigure, Configure (options) |
| `coordinator.py` | `ApplianceCoordinator`: cycle state, Live Activity, loads, quiet hours, history |
| `notify.py` | Sending/clearing notifications, "resolved" alerts, home filter |
| `device.py` | Our device per appliance and its link to the appliance's device |
| `ge.py` | GE Home entity discovery by entity-ID suffix |
| `appliances/` | Per-type definitions (washer, dryer, dishwasher, oven, refrigerator, door) |
| `door.py`, `cooktop.py`, `leak.py`, `maintenance.py`, `oven_extras.py` | Feature monitors |
| `sensor.py`, `number.py`, `event.py`, `button.py` | Entities |
| `health.py` | Repairs issues; `diagnostics.py` (redact personal data) |
| `strings.json` + `translations/en.json` | Must stay **identical**; edit both |
| `brand/` | Icons shown by HACS / HA |

## Home Assistant conventions to follow

- **Devices (HA 2026.8+ registry v3)**: a device belongs to exactly one config
  entry. Each appliance gets its own device (`own_device_info`) that repeats
  the appliance device's identifiers and connections, so both pages show each
  other under **Linked devices**. Don't co-own another integration's device,
  don't put our entities on it (`entity.device_entry`), and don't use
  `via_device` for this. Gate behavior that differs on older HA with
  `LINKED_DEVICES_SUPPORTED`. Avoid `DeviceEntry.config_entries` and
  `primary_config_entry` on new HA; use `config_entry_id`.
- **Config entry reloads**: Configure uses `OptionsFlowWithReload`;
  Reconfigure uses `async_update_reload_and_abort`. Don't add an
  `add_update_listener` reload: HA warns about combining an update
  listener with these, and that behavior changes in 2026.12.
- **Config-flow sections**: section keys must be `vol.Required`. Values are
  flattened on save (`_flatten`) and re-nested for suggested values (`_nest`,
  `SECTIONS`, `SECTION_OF`).
- `DataUpdateCoordinator` gets `config_entry=` explicitly.
- Before relying on an HA API, check the current dev branch of
  `home-assistant/core` for `report_usage` / `breaks_in_ha_version`
  deprecations, not just the version installed for tests.

## Live Activity / notification behavior (keep these working)

- Live Activity payload: `live_update`, `tag`, `chronometer`, `when`,
  `when_relative`, `progress`, `progress_max`, `critical_text`,
  `notification_icon`, `notification_icon_color`, `url`/`clickAction`.
  `message: clear_notification` ends it.
- iOS doesn't reliably remove a notification on a silent clear. So an update
  is always sent first: on stop, show "Off"/"Stopped" and end 60 s later
  (`STOPPED_DISPLAY_SECONDS`). Critical alerts are replaced by a passive
  "resolved" notification and cleared after 120 s (`RESOLVED_CLEAR_SECONDS`).
- Tapping opens the appliance's device page (`tap_path`), else our device,
  else the integration page.
- Laundry tracks loads separately (washer → dryer), each with its own final
  notification.

## Tests

```bash
python3.13 -m venv .venv && .venv/bin/pip install pytest-homeassistant-custom-component pyflakes
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m pyflakes custom_components tests   # "imported but unused" in appliances/ is expected (registration imports)
```

- Add or update tests for every behavior change, ideally reproducing the
  real-world bug first. Use `MockConfigEntry`, `async_mock_service(hass,
  "notify", ...)`, and `freezer` + `async_fire_time_changed` for timers.
- The PyPI test harness lags behind HA releases. When a change depends on
  newer HA behavior, read that version's source, cover the old-HA path in
  tests, and test new-HA-only logic directly (e.g. monkeypatch
  `LINKED_DEVICES_SUPPORTED`).
