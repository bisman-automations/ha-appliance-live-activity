# Changelog

## 1.3.0

### Added
- **Tap to open**: tapping a Live Activity or any alert opens the appliance's
  device page in the Home Assistant app — the GE appliance itself (with its
  controls) for GE setups, otherwise the appliance's device in this
  integration. Works on iOS Live Activities and on Android notifications.
- **Time Left** sensor (minutes, duration) and **Finishes At** sensor
  (timestamp) for washers, dryers, dishwashers and ovens — for dashboards and
  automations. Time Left is 0 and Finishes At is unknown when nothing is
  running; Finishes At is unknown while paused.

## 1.2.2

### Added
- Integration icon (light and dark) in `custom_components/appliance_live_activity/brand/`,
  shown by Home Assistant 2026.3+ in Settings → Devices & services and on the
  integration's devices.

## 1.2.1

### Changed
- **Icon color** is now a color picker in setup and **Configure** instead of
  a hex text field. Existing hex values keep working and show up in the
  picker.
- The **Notification tag** field was removed from setup; it's generated
  automatically and no longer repeats the appliance type
  (`kitchen_refrigerator` instead of `refrigerator_kitchen_refrigerator`).

## 1.2.0

### Added
- **Door monitoring** for refrigerators / freezers: after a door has been
  open 30 s, a Live Activity counts up how long it's been open. After 5
  minutes it turns red and **critical alerts** repeat every minute until the
  door is closed. On close the alerts are removed and the Live Activity shows
  "Closed · was open N min" for a minute, then ends. GE fridges get every door
  (fridge left/right, freezer) automatically.
- **Door** appliance type for garage, patio, gate and other doors, using the
  same flow.
- **Escalation** for doors: after N critical alerts, extra phones get the
  alerts, speakers announce it, and chosen lights turn red (restored on close).
- **Cooktop left-on alerts** for ovens (from the "Critical Gas Cooktop Left
  On Alert" blueprint): critical alert after 30 min with an **Acknowledge**
  button, repeating every 15 min, optional speaker announcement, removed when
  the cooktop turns off. GE ovens' cooktop sensor is found automatically.
- Options for all door and cooktop timings, escalation and announcements.

### Changed
- Everything lives in the integration: the repo no longer ships blueprints,
  and the blueprint installer was removed.

## 1.1.0

### Added
- **GE Home Appliances (SmartHQ) automatic setup**: pick the GE device and
  its state, sub-cycle, cycle, time-remaining, end-of-cycle, door and oven
  temperature entities are discovered automatically.
- Native countdown on the phone (`chronometer` / `when` / `when_relative`).
- "Finished" handling: *Done* state, optional time-sensitive alert, and the
  Live Activity is ended when the door opens or after a configurable delay.
- Optional end-of-cycle and door entities for manually configured appliances.
- Options: finished alert and dismiss delay.
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
