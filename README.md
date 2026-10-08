<img src="custom_components/appliance_live_activity/brand/icon.png" alt="Appliance Live Activity" width="96" align="right">

# Appliance Live Activity

Live Activities (iOS) and Live Updates (Android) for your appliances in Home
Assistant — plus critical alerts when something is left open or left on.

| Appliance | What you get |
|---|---|
| **Washer, dryer, dishwasher** | Live Activity with the current phase, cycle, a live countdown and progress bar → **Done** → dismissed when the door opens. **Delayed starts** count down to the start. Washer and dryer share **one Live Activity per load**. Reminders to **move the laundry** (with **Start dryer** / **Laundry moved** buttons), **refill** detergent, pods and dryer sheets, and a critical alert for a **blocked dryer vent** |
| **Oven** | Live Activity while **preheating** and cooking, plus separate ones for the **kitchen timer** and the **meat probe** + **preheated** alert + **cooktop left-on** critical alerts. Double ovens supported |
| **Any appliance** | **Water leak** critical alerts from leak sensors |
| **Refrigerator / freezer** | Live Activity while a door is open → **critical alerts** if it stays open → **Closed**, plus **too warm** critical alerts and **water filter** reminders |
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

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bisman-automations&repository=ha-appliance-live-activity&category=integration)

1. Click the button above (or HACS → ⋮ → **Custom repositories** → add
   `https://github.com/bisman-automations/ha-appliance-live-activity`, category
   **Integration**).
2. Install **Appliance Live Activity** and restart Home Assistant.
3. Add the integration:

   [![Open your Home Assistant instance and start setting up Appliance Live Activity.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=appliance_live_activity)

   or Settings → Devices & services → **Add integration** → *Appliance Live Activity*.

## Setup

Add one entry per appliance.

- **GE appliance (SmartHQ) — automatic:** choose the GE device. State,
  sub-cycle, cycle, time remaining, end-of-cycle, door, oven temperature,
  cooktop, kitchen timer, meat probe, delay timer, dryer start button,
  blocked-vent sensor, supply levels, water filter and every fridge/freezer
  door are found automatically. Then choose your phones and alert settings.
  For a **double oven**, choose the upper or lower oven, then add the
  integration again for the other one.
- **Any appliance or door:** choose the type (washer, dryer, dishwasher,
  oven, refrigerator, door), then its sensors, then your phones.

Alert settings can be changed later with **Configure** (grouped into
sections: Laundry, Cooking, Fridge & freezer, Appliance health, Leak
sensors, Speaker announcements, Quiet hours, Icon). To change which sensors
an appliance uses — or have the GE sensors found again — use
**⋮ → Reconfigure**.

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

### Laundry: one Live Activity per load

The washer and dryer share a single Live Activity: washing →
*Wash Complete · move to the dryer* → drying → *Dry Complete*. Its title is
the name of whichever is running, or one title of your choice (washer's
Configure → Laundry). Washing a new load while the last one dries? Each
load keeps its own Live Activity. Opening the
washer door to move the load keeps it up; the dryer takes it over when it
starts. It ends when the dryer door opens (or after the dismiss delay).
Turn it off in the washer's **Configure** to get two separate activities.

### Dryer wrinkle tumble

If the dryer finishes into extended tumble, the Live Activity shows
*Dry Complete · tumbling to prevent wrinkles* and stays up until you open
the door.

### Oven kitchen timer

A timer set on the oven gets its own Live Activity counting down, then a
time-sensitive **Timer done** alert. Cancelling the timer ends it.

### Meat probe

While the probe is plugged in, a Live Activity shows its temperature. GE
ovens don't report the probe target, so set it on the appliance's
**Probe Target** number (e.g. from a dashboard) — then it shows
*Probe 128°F → 145°F* with a progress bar, and you get an alert when it's
reached. 0 = just show the temperature. Unplugging the probe ends it.

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

### Appliance health

- **Blocked dryer vent** — a critical alert (it's a fire risk) while the
  dryer reports it, repeated every 30 minutes.
- **Refill reminders** — after a cycle, one notification listing what's low:
  detergent tank, dishwasher pods or rinse aid, dryer sheets (3 or fewer by
  default, or 25 % for tank levels). Each is mentioned once until refilled.
- **Filters** — fridge: a reminder when the water filter needs replacing or
  has expired, a critical alert if it reports a leak. Dishwasher: a reminder
  when the filter needs cleaning.

### Quiet hours

Set a start and end time (Configure → Quiet hours) and regular alerts —
Done, laundry reminders, refills, filters — wait until quiet hours end.
Only the latest of each is delivered, and anything dealt with overnight
(e.g. you tapped *Laundry moved*) is dropped. Live Activities, critical
alerts and cooking alerts (preheated, kitchen timer, probe) always come
through. Held alerts don't survive a Home Assistant restart.

### Fridge & freezer too warm

If the fridge or freezer stays above its limit for 30 minutes — a door left
ajar, a power cut — you get a **critical alert**, repeated every hour, then
*back to normal* once it's cold again. Limits default to 45 °F / 7 °C for
the fridge and 15 °F / -9 °C for the freezer. An optional notification when
the ice bucket is full is off by default.

### Move the laundry (washers)

15 minutes after the washer finishes, a reminder to move the laundry repeats
every 15 minutes (up to 3 times) until the washer door opens or the dryer
starts. The GE dryer is found automatically.

The finished alert and the reminders have two buttons:

- **Start dryer** — starts the dryer (its **Remote Start** must be on; if it
  isn't, you're told so instead).
- **Laundry moved** — stops the reminders and clears the washer's alerts.

### Unload the dryer

30 minutes after the dryer finishes, *Unload the dryer* (repeated once)
until the dryer door opens or you tap **Unloaded**.

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

### Only alert people who are home

Turn on *Only alert people who are home* in Configure and Done alerts and
reminders go only to phones whose owner is home (from the Companion app's
location). If nobody is home, everyone gets them. Live Activities and
critical alerts always go to everyone.

### Dishwasher: ready to unload

When the dishwasher reports clean dishes, its Live Activity shows
*Dishes Clean · ready to unload* and stays up until the door opens.

### Live Activity titles

A Live Activity is titled with the appliance's name — rename the device in
Home Assistant and it follows — or a title of your own (Configure → Live
Activity title & icon).

### Tapping a notification

Tapping a Live Activity or alert opens the appliance's device page in the
Home Assistant app (the GE appliance's own page for GE setups).

### Dashboards and services

- **Status** and **Progress** sensors per appliance, plus **Time Left** and
  **Finishes At** for washers, dryers, dishwashers and ovens (status attributes include
  phase, cycle, remaining minutes, door open minutes and cooktop on-time).
- **Cycles This Week** and **Average Cycle** sensors for washers, dryers,
  dishwashers and ovens.
- An **event entity** per appliance for automations: `started`,
  `scheduled`, `finished`, `cancelled` (fridges and doors: `door_left_open`,
  `door_closed`). Use it as a trigger: *Entity → Event*.
- **Probe Target** number for ovens with a meat probe.
- `appliance_live_activity.update` re-sends an appliance's Live Activity.

## Troubleshooting

- **Settings → Repairs** tells you when a phone can't receive alerts (e.g.
  after renaming it in the Companion app) or a sensor an appliance uses is
  gone.
- **Download diagnostics** (⋮ on the appliance) gives the settings, what the
  appliance reports and what the integration is doing — attach it to bug
  reports.

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
