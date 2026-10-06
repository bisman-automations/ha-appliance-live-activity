<img src="custom_components/appliance_live_activity/brand/icon.png" alt="Appliance Live Activity" width="96" align="right">

# Appliance Live Activity

Live Activities (iOS) and Live Updates (Android) for your appliances in Home
Assistant — plus critical alerts when something is left open or left on.

| Appliance | What you get |
|---|---|
| **Washer, dryer, dishwasher** | Live Activity with the current phase, cycle, a live countdown and progress bar → **Done** → dismissed when the door opens |
| **Oven** | Live Activity while cooking (mode, temperature, cook-timer countdown) + **cooktop left-on** critical alerts |
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
   Optional **escalation** after a number of alerts: extra phones get the
   alerts, speakers announce it, and chosen lights turn red.
3. Closed → alerts removed, lights restored, the Live Activity shows
   **Closed · was open N min** for a minute, then goes away.

### Dashboards and services

- **Status** and **Progress** sensors per appliance (status attributes include
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
