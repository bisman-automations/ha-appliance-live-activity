# Changelog

## 1.2.0

Everything since 1.0.0 (1.1.0 was never released as a tagged version).

### Added
- **GE Home Appliances (SmartHQ) automatic setup**: pick the GE device and
  its state, sub-cycle, cycle, time-remaining, end-of-cycle, door, oven
  temperature, cooktop and fridge/freezer door entities are discovered.
- **Door monitoring** (refrigerator / freezer, and a new generic **Door**
  type for garage, patio…): Live Activity counting up while open (after a
  30 s start delay), critical alerts every minute after 5 minutes until
  closed, then "Closed" for a minute before the activity ends. Optional
  escalation: extra phones, speaker announcements, red lights (restored on
  close).
- **Cooktop left-on alerts** for ovens (from the "Critical Gas Cooktop Left
  On Alert" blueprint): critical alert after 30 min with an Acknowledge
  button, repeating every 15 min, optional speaker announcement, cleared
  when the cooktop turns off.
- Native countdown on the phone (`chronometer` / `when` / `when_relative`).
- "Finished" handling: *Done* state, optional time-sensitive alert, and the
  Live Activity is ended when the door opens or after a configurable delay.
- Optional end-of-cycle and door entities for manually configured appliances.
- Options for all alert timings, escalation and announcements.
- Tests and a CI workflow (hassfest, HACS validation, pytest).

### Fixed
- **Notifications were never sent**: phones were looked up by notify
  *entities*, but the Companion app registers `notify.mobile_app_<name>`
  services. Phones are now resolved by device name.
- The *Done* notification was re-sent every minute while an appliance sat
  in its completed state.
- Running updates were sent every minute. Updates are now sent only when
  something changes or the time estimate drifts more than 3 minutes, so iOS
  no longer throttles them.
- Remaining time in hours (GE dishwashers / ovens) is converted to minutes.
- State matching is case-insensitive; "Pause" also matches "Paused", and
  unrecognised running states (e.g. GE's "Cycle Active") count as running.
- Ovens: turning the oven off is no longer reported as "complete" unless a
  cook timer had run out.
- Options flow compatibility with current Home Assistant (no longer sets
  `config_entry` itself).

### Changed
- Requires Home Assistant 2026.7+ (Live Activities support).
- Everything lives in the integration; the repo no longer ships blueprints.

## 1.0.0

Initial release.

- Config-flow based setup: pick an appliance type, its entities, and which
  phones get notified -- no YAML editing required.
- Five appliance plugins: washer, dryer, dishwasher, oven, refrigerator.
- Generic coordinator ported from the original `applianceminder.yaml`
  blueprint.
- Persists total cycle length across HA restarts (no `input_number` helper
  needed).
- Status and Progress sensors per appliance for dashboards.
- `appliance_live_activity.update` service for forcing a manual refresh.
