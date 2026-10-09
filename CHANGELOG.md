# Changelog

## 1.9.1

### Added
- **Linked to the appliance**: this integration's device now shows as
  *Connected via* the appliance, so the two device pages link to each other —
  the GE appliance for GE setups, or for any other brand the device the
  state sensor belongs to (e.g. an LG or Samsung washer, or a door's contact
  sensor). It also starts out in the appliance's area (an area you've already
  chosen is kept), and tapping a notification opens the appliance's page.
  Existing appliances are linked on the next start.

### Fixed
- **Critical alerts could stay on screen after the problem was fixed**
  (cooktop turned off, door closed, dryer vent cleared). They were removed
  with a silent "clear" push, which iOS may handle late, not at all, or before
  an alert sent seconds earlier. They're now replaced with a quiet "✅ Cooktop
  off" / "✅ closed" / "✅ vent clear" notification, which is removed two
  minutes later.
- **Fridge / door Live Activity stuck**: closing and reopening the door
  within the minute "Closed" shows left the Live Activity up for good. A
  reopen now updates the same Live Activity right away, and the next close
  ends it as usual.
- GE fridges: alerts name the door that's open ("Fridge Right Door") instead
  of also listing the overall "Door" sensor.
- Snoozing a door alert replaces it with "🔕 alert snoozed" instead of a
  silent clear.

## 1.9.0

### Added
- **One notification per laundry load**, named after the wash cycle, that
  stays in Notification Center after the Live Activity is gone:
  - Washer done: "✅ Towels: washed — Laundry Room Washer finished the
    Towels cycle. Load it into the dryer."
  - When that load finishes drying, the same notification becomes
    "✅ Towels: load complete — Your Towels load has been washed and dried.
    Please take care of it."
  - Each load has its own notification, so two loads (towels drying while
    darks wash) never replace each other. Loads go into the dryer in the
    order they were washed.
  - Something dried on its own: "✅ Delicates: dry".
  - *Unloaded* on the dryer's notification removes it.

## 1.8.2

### Changed
- Settings only show for the appliances they apply to:
  - **Leak sensors** for washers, dishwashers and fridges (not ovens, dryers
    or doors).
  - **Speaker announcements** only when there's something to announce —
    leaks, a cooktop, the dryer vent or a door left open.
  - **Quiet hours** not for plain doors (their alerts are all critical or
    Live Activities, which never wait).
  - A setting you already use stays visible.
- **Live Activity titles**: the shared washer + dryer Live Activity now shows
  the name of whichever is running ("Laundry Room Washer", then "Laundry Room
  Dryer") instead of "Laundry". Set one title for it under the washer's
  Configure → Laundry, or a title for any appliance under Configure → Live
  Activity title & icon. Titles also follow the appliance if you rename its
  device in Home Assistant.

### Fixed
- **Two loads at once**: a new wash while the last load is drying no longer
  fights the dryer over one Live Activity. Each load keeps its own: the
  second appliance to start gets a Live Activity of its own, and the dryer
  takes over the right load's activity when it's moved in.
- Fridges and doors no longer get a Progress sensor (it was disabled anyway).
- Setting up a fridge by hand now also asks for the fridge / freezer
  temperature and ice bucket sensors.

## 1.8.1

### Fixed
- **Configure didn't save** (1.7.0, 1.8.0): settings inside the grouped
  sections (Laundry, Cooking, Leak sensors, Quiet hours…) weren't shown or
  saved by the Home Assistant frontend, and saving could wipe pickers in
  those sections. Sections now show your saved values and save normally.
- Sensors that setup had found and that were wiped this way (leak sensors,
  dryer, dryer start button, supplies, filter, blocked vent) are restored
  automatically. Settings you picked yourself (speakers, text-to-speech,
  quiet hours, escalation phones and lights) can't be recovered — please
  set them again in Configure.

## 1.8.0

### Added
- **Only alert people who are home** (Configure, off by default): Done
  alerts and reminders go only to phones whose owner is home, by the
  Companion app's location; if nobody is home, everyone gets them. Live
  Activities and critical alerts always go to everyone.
- **Dishwasher "ready to unload"**: when the dishwasher reports clean dishes,
  the Live Activity shows "Dishes Clean · ready to unload" and stays up until
  the door opens. GE's clean sensor is found automatically.
- **Cycle events** for automations: an event entity per appliance —
  `started`, `scheduled`, `finished` (with how long it ran) and `cancelled`
  for appliances, `door_left_open` and `door_closed` for fridges and doors.
- **Cycle history**: *Cycles This Week* (with today and last 30 days) and
  *Average Cycle* (last 10 cycles) sensors.
- **Repairs**: Settings → Repairs shows when a phone can no longer receive
  alerts (e.g. renamed in the Companion app) or a sensor an appliance uses
  no longer exists. Issues clear themselves once fixed.
- **Download diagnostics** on each appliance for bug reports.

## 1.7.0

### Added
- **Grouped settings**: setup and Configure are split into sections —
  Laundry, Cooking, Fridge & freezer, Escalation, Appliance health, Leak
  sensors, Speaker announcements, Quiet hours and Icon — with the less-used
  ones collapsed.
- **Reconfigure** (⋮ on the appliance → Reconfigure): change the sensors an
  appliance uses after setup, or have the GE sensors found again, without
  deleting it.
- **Quiet hours**: set a start and end time and regular alerts — Done,
  laundry reminders, refills, filters — wait until quiet hours end (only the
  latest of each is delivered, and anything dealt with overnight is
  dropped). Live Activities, critical alerts and cooking alerts (preheated,
  kitchen timer, probe) still come through.
- **Dryer unload reminder**: 30 minutes after the dryer finishes, "Unload the
  dryer" — repeated once — until the dryer door opens or you tap
  **Unloaded** (also on the dryer's finished alert). On by default; set the
  time to 0 in Configure → Laundry to turn it off.
- **Fridge / freezer too warm**: a critical alert when the fridge or freezer
  stays above its limit (45 °F / 7 °C and 15 °F / -9 °C by default) for 30
  minutes — a door left ajar or a power cut — repeated hourly, then "back to
  normal". GE fridges' temperature sensors are found automatically.
- **Ice bucket full** notification (off by default — a full bucket is the
  ice maker's normal resting state).

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
