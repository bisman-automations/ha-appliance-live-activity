<img src="custom_components/appliance_live_activity/brand/icon.png" alt="Appliance Live Activity" width="96" align="right">

# Appliance Live Activity

Live Activities (iOS) and Live Updates (Android) for your appliances in Home
Assistant — plus critical alerts when something is left open or left on.

| Appliance | What you get |
|---|---|
| **Washer, dryer, dishwasher** | Live Activity with the current phase, cycle, a live countdown and progress bar → **Done** → dismissed when the door opens. **Delayed starts** count down to the start. Washers also remind you to **move the laundry**, with **Start dryer** / **Laundry moved** buttons |
| **Oven** | Live Activity while **preheating** (temperature climbing) and cooking + **preheated** alert + **cooktop left-on** critical alerts |
| **Any appliance** | **Water leak** critical alerts from leak sensors |
| **Refrigerator / freezer** | Live Activity while a door is open → **critical alerts** if it stays open → **Closed** |
| **Any door** (garage, patio, gate…) | Same as the fridge, for any door sensor |

**GE Home Appliances (SmartHQ)** appliances are set up automatically — pick
the appliance and every sensor is found for you. Other brands (LG, Samsung,
Bosch, Whirlpool, Miele…) work too: pick their sensors.

Everything is in the integration — no blueprints, helpers or YAML needed.

## Requirements

- Home Assistant **2026.7** or newer
- Companion app: iOS **17.2+** (Live Activities) or Android **16+** (Live Updates)
- iOS: allow **Critical Alerts** for the Companion app (Settings → Notifications → Home Assistant)

## Install via HACS

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/donavanbecker/ha-appliance-live-activity`, category
   **Integration**.
2. Install **Appliance Live Activity** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → *Appliance Live Activity*.

## Setup

Add one entry per appliance.

- **GE appliance (SmartHQ) — automatic:** choose the GE device. State,
  sub-cycle, cycle, time remaining, end-of-cycle, door, oven temperature,
  cooktop and every fridge/freezer door are found automatically. Then
  choose your phones and alert settings.
- **Any appliance or door:** choose the type (washer, dryer, dishwasher,
  oven, refrigerator, door), then its sensors, then your phones.

Everything after the sensors can be changed later with **Configure**.

## How it behaves

### Washer, dryer, dishwasher, oven

- **Starts** a Live Activity when the appliance starts.
- **Updates only when something changes** — state, phase, cycle, or the
  appliance's estimate drifting more than 3 minutes from the countdown. The
  phone runs the countdown itself, so there's no update every minute for iOS
  to throttle.
- Reads the time-remaining unit from the sensor (GE reports **hours** for
  dishwashers and ovens, **minutes** for laundry).
- **Finishes once:** *Done* with a full progress bar, an optional
  time-sensitive "finished" alert, and the Live Activity ends when the door
  opens (or after 30 minutes).
- **Cancelled** cycles (stopped with time left) just end the activity.
- **Delayed start:** while the appliance waits to start, the Live Activity
  shows *Scheduled · starts at 3:45 PM* and counts down to the start, then
  switches to the cycle countdown. Cancelling the delay ends it.

### Oven preheat

When the oven is preheating, the Live Activity shows the temperature climbing
toward the set temperature (with a progress bar). When it gets there you get a
time-sensitive **"Oven preheated — it's at 350°F"** alert, which is removed
when the oven turns off.

### Water leaks (any appliance)

Add leak sensors to any appliance. The moment one detects water you get a
**critical alert** (and a speaker announcement if configured), repeated every
5 minutes until it's dry, then "leak cleared". **Silence until dry** on the
alert stops the repeats; a new leak alerts again. Sensors named after the
appliance, like a "Kitchen Dishwasher Leak Sensor", are picked automatically
in GE setup.

### Move the laundry (washers)

15 minutes after the washer finishes, a reminder to move the laundry repeats
every 15 minutes (up to 3 times) until the washer door opens or the dryer
starts. The GE dryer is found automatically.

The finished alert and the reminders have two buttons:

- **Start dryer** — starts the dryer (its **Remote Start** must be on; if it
  isn't, you're told so instead).
- **Laundry moved** — stops the reminders and clears the washer's alerts.

### Cooktop left on (ovens / ranges)

- Cooktop on for **30 minutes** → **critical alert** with an
  **Acknowledge** button, plus an optional speaker announcement.
- Repeats every **15 minutes** until the cooktop is off or you tap
  Acknowledge (which silences it until the next time the cooktop is on).
- Turning the cooktop off removes the alert. The integration never turns the
  cooktop off.

### Doors (refrigerator, freezer, garage…)

1. Open for **30 seconds** (so quick grabs don't count — iOS limits how many
   Live Activities can start) → Live Activity counting up how long it's been
   open, naming the door ("Freezer Door is open").
2. Still open after **5 minutes** → it turns red and **critical alerts**
   repeat **every minute** until it's closed.
   **Snooze 10 min** on the alert pauses them (the Live Activity stays).
   Optional **escalation** after a number of alerts: extra phones get the
   alerts, speakers announce it, and chosen lights turn red.
3. Closed → alerts removed, lights restored, the Live Activity shows
   **Closed · was open N min** for a minute, then goes away.

### Buttons

iOS doesn't allow buttons on Live Activities, so buttons are on the regular
alerts (long-press or swipe down on the notification to see them).

### Tapping a notification

Tapping a Live Activity or alert opens the appliance's device page in the
Home Assistant app (the GE appliance's own page for GE setups).

### Dashboards and services

- **Status** and **Progress** sensors per appliance, plus **Time Left** and
  **Finishes At** for washers, dryers, dishwashers and ovens (status attributes include
  phase, cycle, remaining minutes, door open minutes and cooktop on-time).
- `appliance_live_activity.update` re-sends an appliance's Live Activity.

## Adding an appliance type

Appliance types are plugins in
`custom_components/appliance_live_activity/appliances/`. Add a file with an
`ApplianceDefinition` (see `washer.py`) and one import line in
`appliances/__init__.py`.

## Development

```bash
pip install pytest-homeassistant-custom-component
pytest
```

CI runs hassfest, HACS validation and the tests.

## License

MIT — see [LICENSE](LICENSE).
