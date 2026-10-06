# Changelog

## 1.6.1

### Changed
- **Dishwasher filter** has its own **Filter sensor** field instead of being
  picked with the refill supplies. GE dishwashers' "Reminders Clean Filter"
  is found automatically, and you get a "clean the filter" reminder when it
  turns on. If you'd added it to the refill supplies in 1.6.0, it's moved to
  the Filter field for you.
- Clearer labels for the refill reminder fields.

## 1.6.0

### Added
- **Oven kitchen timer Live Activity**: a timer set on the oven gets its own
  Live Activity counting down on the phone, then a time-sensitive "Timer
  done" alert. Cancelling the timer just ends it.
- **Meat probe Live Activity**: while the probe is plugged in, its
  temperature climbs on a Live Activity. Set a target with the new
  **Probe Target** number entity (GE ovens don't report the one set on the
  oven) to get "128°F → 145°F" with a progress bar and an alert when it's
  reached.
- **Double ovens**: GE double ovens are set up one oven at a time (upper /
  lower), each with its own Live Activity, timer and probe. The cooktop is
  alerted once, by the upper oven.
- **Dryer wrinkle tumble**: when a dryer finishes into extended tumble, the
  Live Activity shows "Dry Complete · tumbling to prevent wrinkles" and
  stays up until the door opens.
- **One Live Activity per laundry load**: the washer and dryer share a
  "Laundry" Live Activity — washing → "move to the dryer" → drying → done —
  instead of two. Opening the washer door keeps it up so the dryer can take
  it over. On by default for washers with a dryer; can be turned off in
  Configure.
- **Blocked dryer vent**: critical alert (a fire risk) while GE reports a
  blocked vent, repeated every 30 minutes, removed when it clears.
- **Refill reminders**: after a cycle, one notification listing what's
  low — washer detergent tank, dishwasher pods / rinse aid, dryer sheets.
  Each is mentioned once until it's refilled.
- **Fridge water filter**: a reminder when the filter needs replacing or has
  expired, and a critical alert if it reports a leak.
- GE appliances set up with an earlier version pick up the new sensors
  automatically.
- Status sensor attributes: `kitchen_timer_minutes`, `probe_temperature`,
  `probe_target`, `vent_blocked`.
- README: **Add to HACS** and **Add integration** buttons.

## 1.5.0

### Added
- **Delayed start Live Activity**: when a washer, dryer, dishwasher or oven
  is waiting on a delayed start, a Live Activity shows "Scheduled · Delayed
  start · starts at 3:45 PM" with a countdown to the start, then turns into
  the normal cycle countdown when it starts (or ends if the delay is
  cancelled). GE delay sensors are found automatically (also for appliances
  set up with an earlier version). Can be turned off in Configure.
- **Buttons on alerts** (on the notification, not the Live Activity — iOS
  doesn't allow buttons on Live Activities):
  - **Start dryer** on the washer's finished alert and move-the-laundry
    reminder: presses the dryer's start button. If the dryer's Remote Start
    isn't on, you get a notification saying so instead. The GE dryer's start
    button is found automatically.
  - **Laundry moved**: stops the reminders and removes the finished alert and
    Live Activity.
  - **Silence until dry** on leak alerts: stops the repeats and announcements
    until the sensor is dry; a new leak alerts again.
  - **Snooze 10 min** on fridge / door critical alerts: pauses the critical
    alerts while the door stays open (the Live Activity stays). The snooze
    length is in Configure; 0 removes the button.
- Status sensor: `delayed` state with a `starts_at` attribute, and a
  `snoozed_until` attribute for doors.

## 1.4.0

### Added
- **Oven preheated alert**: a time-sensitive "Kitchen Oven preheated — it's
  at 350°F, ready to cook" when the oven reaches its set temperature. While
  preheating, the Live Activity shows "Preheating · 275°F → 350°F" with the
  progress bar filling as it heats (updated in 10 % steps so iOS doesn't
  throttle it); once cooking it shows the set temperature. The alert is
  removed when the oven turns off. GE ovens' set-temperature entity is found
  automatically; can be turned off in Configure.
- **Water leak alerts** for any appliance: a critical alert the moment a leak
  sensor detects water, plus an optional speaker announcement, repeated every
  5 minutes until it's dry, then replaced with "leak cleared". Leak sensors
  named after the appliance (e.g. "Kitchen Dishwasher Leak Sensor") are
  picked automatically during GE setup; any moisture sensor can be added.
- **Move-the-laundry reminder** for washers: 15 minutes after a wash
  finishes, a time-sensitive reminder repeats every 15 minutes (up to 3
  times) until the washer door is opened or the dryer starts. The GE dryer is
  found automatically. Set the delay to 0 to turn it off.
- Speaker announcement settings are now available for every appliance.
- Status sensor attribute `leak_detected`.

### Fixed
- Oven "Delayed Start" is treated as idle.
- Clearing an optional picker (leak sensors, speakers, dryer…) in Configure
  now actually removes it instead of falling back to the value found at setup.

## 1.3.1

### Fixed
- **Finished Live Activity didn't clear** after the dismiss delay. After a
  cycle ended, an unrecognised appliance state (e.g. a GE dishwasher showing
  "Control Locked") was treated as a new cycle, which switched the activity
  back to "running" and cancelled the dismissal. Unrecognised states now only
  start a cycle when a timer is actually counting down; during a cycle they
  still count as running.
- **Icon color picker showed black** under Configure for appliances set up
  before 1.2.1 (stored as hex). It now shows the saved color.

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
