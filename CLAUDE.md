# Appliance Live Activity: notes for Claude and other coding agents

Instructions for AI coding agents (Claude, Codex, Copilot, etc.) and humans.
`AGENTS.md` points here, so keep the rules in this file.

## What this is

**Appliance Live Activity** (`appliance_live_activity`): a HACS custom integration
that sends iOS Live Activities and alerts (via the Home Assistant Companion app,
`mobile_app` notify) for appliances: GE Home / SmartHQ (`ge_home`) appliances
first, plus any other brand or a plain door/contact sensor set up manually.

- Repo: `bisman-automations/ha-appliance-live-activity` (owner `@donavanbecker`).
- Minimum Home Assistant: `hacs.json` → `homeassistant` (currently 2026.8.0).
  Code must keep working from that version through the current dev release.
  Do not add a `homeassistant` key to `manifest.json`; hassfest rejects it.

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
  migrate it once in `async_migrate_entry` and bump `CONFIG_MINOR_VERSION`
  (and the flow's `MINOR_VERSION`). `GE_DISCOVERY_VERSION` is defined in both
  `__init__.py` and `config_flow.py`; a new discovery version needs a new
  minor step that calls `_async_backfill_ge`, or existing entries will not
  pick the new entities up.

## Release notes for this repo

- Each release's `CHANGELOG.md` entries are user-facing: what changed and why,
  with **bold lead-ins** like the existing entries.

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
| `door.py`, `cooktop.py`, `leak.py`, `maintenance.py`, `oven_extras.py`, `oven_light.py` | Feature monitors |
| `sensor.py`, `number.py`, `event.py`, `button.py` | Entities |
| `health.py` | Repairs issues; `diagnostics.py` (redact personal data) |
| `strings.json` + `translations/en.json` | Must stay **identical**; edit both |
| `brand/` | Icons shown by HACS / HA |

## Home Assistant conventions to follow

- **Devices (registry v3, required since the 2026.8 minimum)**: a device
  belongs to exactly one config entry (`config_entry_id`). Each appliance
  gets its own device (`own_device_info`) that repeats the appliance
  device's identifiers and connections, so both pages show each other under
  **Linked devices**. Don't co-own another integration's device, don't put
  our entities on it (`entity.device_entry`), and don't use `via_device`.
  Don't read `DeviceEntry.config_entries` or `primary_config_entry`, and
  don't pass `remove_config_entry_id`; remove a device with
  `async_remove_device`.
- **Finding our device**: use `own_device(hass, entry)` (`device.py`). It
  calls `async_get_device_by_identifier` with our config entry. Identifiers
  are shared with the appliance, so `async_get_device` is ambiguous; 2026.10
  reports that call and raises `RuntimeError` when the caller isn't tied to
  an integration, and 2027.8 removes it. Devices that share one identifier
  are listed with `async_get_devices`.
- **Entity IDs**: platforms set `_attr_has_entity_name = True` and a
  `translation_key` (strings in `strings.json`, `translations/en.json` and
  `icons.json`). Do not set `_attr_name`: a name that already includes the
  appliance name is prefixed with the device name ("… Live Activity") and
  the entity id doubles. `attach_to_appliance` suggests
  `<platform>.<slug of appliance name + entity name>`
  (`sensor.kitchen_dishwasher_status`). That suggestion applies only when
  the unique id is new. The unique id stays `<entry_id>_<key>` (the event
  entity's unique id is `<entry_id>_event`), so an entity id already in the
  registry is kept. The English names used for the slug are
  `SUGGESTED_ENTITY_NAMES` and must match the translations.
- **Timers**: every `async_call_later` goes through `async_track_later`,
  which registers the cancel callback with `entry.async_on_unload`.
  Background work uses `entry.async_create_background_task` (`async_run` on
  the coordinator), not `hass.async_create_task`. The test harness fails a
  test that leaves a timer behind.
- **Coordinators** live on `entry.runtime_data`. Don't put them in
  `hass.data[DOMAIN]`. Services are registered once in `async_setup`.
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

Run the shared checks at the end of this file.

- `appliances/__init__.py` imports each appliance module only to register
  it; those imports carry `# noqa: F401` so ruff doesn't remove them. Do the
  same for a new appliance type.
- Add or update tests for every behavior change, ideally reproducing the
  real-world bug first. Use `MockConfigEntry`, `async_mock_service(hass,
  "notify", ...)`, and `freezer` + `async_fire_time_changed` for timers.
- The PyPI test harness lags behind HA releases. When a change depends on
  newer HA behavior, read that version's source and cover it with a test.
  The oldest supported release is the `requirements_test_min.txt` venv.

<!-- BEGIN bisman-automations shared rules -->
<!-- This block is the same in every bisman-automations repo. Edit it in
     bisman-automations/.github (templates/CLAUDE.shared.md) and copy it to
     every repo; the Validate workflow's "standards" job checks it matches. -->

## Shared rules (every bisman-automations repo)

### Releases

- The version lives in `custom_components/<domain>/manifest.json`. Anything
  else that repeats it is called out in the repo-specific notes below and is
  bumped in the same commit.
- Versions follow [Semantic Versioning](https://semver.org): patch for fixes,
  translations, docs and CI; minor for new features, options or entities;
  major when something users rely on is removed or renamed (entities,
  services, events, options) or setup has to be redone.
- Check what is released before choosing a version:
  `git ls-remote --tags origin | awk -F/ '{print $3}' | sort -V | tail -1`
  (`sort -V`: plain sorting puts `v1.10.0` before `v1.9.0`). Never add
  changes to a released version. If the manifest version has no tag yet,
  add to its CHANGELOG section instead of bumping again.
- Every push to `main` ships as a release. In that same commit, named
  `Release X.Y.Z`, bump the manifest version and write the notes directly
  under a new `## [X.Y.Z] - YYYY-MM-DD` heading in `CHANGELOG.md` (Keep a
  Changelog: Added, Changed, Deprecated, Removed, Fixed, Security), with
  that version's compare link at the bottom. There is no `## [Unreleased]`
  section and no `[Unreleased]:` compare link. New work is not collected
  under a holding heading and moved later; the release commit is where the
  heading and the entries are written. The standards check fails if a
  `## [Unreleased]` heading is present.
- Ask Donavan before every push. Push fast-forward only: never force-push,
  rebase or amend anything already pushed, or rewrite history in any other
  way. Rewriting history orphans the release tags (it broke drafting in
  ha-button-actions).
- Pushing to `main` runs **Draft release**, which creates or refreshes a
  draft `vX.Y.Z` with that version's CHANGELOG section as the notes, the
  commits since the last release and `<domain>.zip`. **Donavan publishes
  the draft himself**, and publishing creates the tag. Never create or push
  tags, publish releases, or edit published releases.
- Publishing runs **Release check**: the tag must match the manifest version
  and the CHANGELOG, and be on `main`. If it fails, fix it with a new patch
  release, not by moving the tag.

### Commits

- Author commits as `Donavan Becker <donavan.becker@icloud.com>` (set
  `git config user.name` / `user.email` in the clone). HACS's
  default-repository check needs the submitter to have a fair share of the
  commits. Credit an AI assistant with a `Co-Authored-By:` trailer if you
  like, never as the author.
- Subject lines are plain, imperative and say what changed for the user
  ("Show Pico remotes as unavailable when Lutron isn't running"). No
  `fix:`/`feat:` prefixes. Release commits are "Release X.Y.Z".
- Commit and push only when asked.

### CI (shared workflows)

- `.github/workflows/` holds four thin callers of the reusable workflows in
  [bisman-automations/.github](https://github.com/bisman-automations/.github):
  `test.yml` (lint, frontend, pytest on the oldest supported and the newest
  Home Assistant, plus the upcoming one as information only), `validate.yml`
  (hassfest, HACS, standards), `draft-release.yml` and `release-check.yml`.
  Don't add jobs to the callers. Use the shared workflow's inputs, or change
  the shared workflow so every repo gets the improvement.
- `requirements_test.txt` leaves `pytest-homeassistant-custom-component`
  unpinned (newest Home Assistant) and pins ruff (and mypy where used).
  `requirements_test_min.txt` pins the harness release for the minimum in
  `hacs.json`: the newest harness release of that month. CI fails if they
  drift apart.
- Raising the minimum Home Assistant means changing, together: `hacs.json`,
  `requirements_test_min.txt`, `python-min` in `test.yml` (3.13 up to
  2026.2, 3.14 from 2026.3), the README's Home Assistant badge, and a
  CHANGELOG entry.
- Home Assistant 2026.3 and newer need Python 3.14 (3.14.2+).
- The published hassfest rejects `categories` in `manifest.json` and Pillow
  in `requirements`. Leave both out.
- Dependabot (`.github/dependabot.yml`) proposes action and pinned-tool
  updates weekly. It ignores the test harness on purpose.
- Test and Validate also run every Thursday, the day after Home Assistant's
  betas come out. The **next** test job (newest pre-release harness) is
  information only: when it fails, fix the cause before that release ships.

### Before saying work is done

Run from the repo root, in a Python 3.14 venv with `requirements_test.txt`
installed:

```
ruff check .
ruff format --check .
pytest
```

Also run `node --test tests/*.mjs` when the repo has Node tests, mypy when
the repo-specific notes list it, and the tests in a second venv with
`requirements_test_min.txt` when a change could behave differently on the
oldest supported Home Assistant. The standards check (also in CI) is
`python <path to bisman-automations/.github>/scripts/check_repo.py .`.

### Code and docs

- Support every Home Assistant from the `hacs.json` minimum to the newest
  release. Check for deprecations in the newest release and the beta.
- Keep entity IDs, unique IDs, service names and event names stable. When
  one has to change, migrate it and say so under Changed in the CHANGELOG.
- `strings.json` and `translations/en.json` hold the same keys. Home
  Assistant reads only `translations/`, so change both in the same commit.
- Never put personal details in the repo (README, CHANGELOG, code, tests,
  screenshots): no names, addresses, account or device identifiers, or real
  entity IDs. Use placeholders such as `light.living_room`.
- `README.md` is user documentation with the standard header (badges, HACS
  and "add integration" My buttons) and sections Installation, Setup, ...,
  Troubleshooting, Development, License. Use plain language and show names,
  not entity IDs, wherever the UI does.
<!-- END bisman-automations shared rules -->
