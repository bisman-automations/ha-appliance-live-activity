<p align="center">
  <img src="https://raw.githubusercontent.com/bisman-automations/ha-appliance-mgmt/main/custom_components/appliance_mgmt/brand/icon.png" alt="Appliance Mgmt icon" width="128">
</p>

# Appliance Mgmt

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.8%2B-blue.svg)](https://www.home-assistant.io/)
[![GitHub Release](https://img.shields.io/github/v/release/bisman-automations/ha-appliance-mgmt)](https://github.com/bisman-automations/ha-appliance-mgmt/releases)
[![Test](https://github.com/bisman-automations/ha-appliance-mgmt/actions/workflows/test.yml/badge.svg)](https://github.com/bisman-automations/ha-appliance-mgmt/actions/workflows/test.yml)
[![Validate](https://github.com/bisman-automations/ha-appliance-mgmt/actions/workflows/validate.yml/badge.svg)](https://github.com/bisman-automations/ha-appliance-mgmt/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/bisman-automations/ha-appliance-mgmt)](LICENSE)

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

- Home Assistant **2026.8** or newer
- Companion app: iOS **17.2+** (Live Activities) or Android **16+** (Live Updates)
- iOS: allow **Critical Alerts** for the Companion app (Settings → Notifications → Home Assistant)

## Installation

Requires **Home Assistant 2026.8 or newer**.

### Marketplace (Home Assistant 2026.11 and newer, recommended)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=bisman-automations&repository=ha-appliance-mgmt&category=integration)

1. Open the Marketplace and search for **Appliance Mgmt**, or select the button above to open this repository in the Marketplace.
2. Download **Appliance Mgmt** and restart Home Assistant.

New versions show up under **Settings > Updates**. Already installed Appliance Mgmt with
HACS? There's nothing to do: Home Assistant moves it into the Marketplace the
first time it starts on 2026.11.

### HACS (Home Assistant 2026.10 and older)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bisman-automations&repository=ha-appliance-mgmt&category=integration)

1. Open HACS and search for **Appliance Mgmt**, or select the button above to open this repository in HACS.
2. Download **Appliance Mgmt** and restart Home Assistant.

### Custom repository

If **Appliance Mgmt** does not appear in search:

1. In HACS open the menu, choose **Custom repositories**, and add `https://github.com/bisman-automations/ha-appliance-mgmt` as an **Integration**.
2. Download **Appliance Mgmt** and restart Home Assistant.

### Manual

Download `appliance_mgmt.zip` from the [latest release](https://github.com/bisman-automations/ha-appliance-mgmt/releases/latest), unzip it into `config/custom_components/appliance_mgmt/`, and restart Home Assistant.

### Upgrading from Appliance Live Activity

Appliance Live Activity was renamed Appliance Mgmt in 2.0.0. Your appliances,
settings, entities, history and pictures move across by themselves, but the
Marketplace (HACS) can't make the switch for you: it won't update across the
rename, and it won't remove Appliance Live Activity while appliances are set
up with it. So the switch is done by hand, once.

> **Don't press Delete and uninstall** if the Marketplace offers it. It
> deletes your appliances, and then there's nothing left to move.

1. Open a terminal with access to your configuration folder (for example the
   Terminal & SSH add-on) and run:

   ```sh
   cd /config/custom_components
   mkdir appliance_mgmt
   curl -L -o /tmp/appliance_mgmt.zip https://github.com/bisman-automations/ha-appliance-mgmt/releases/latest/download/appliance_mgmt.zip
   unzip /tmp/appliance_mgmt.zip -d appliance_mgmt
   rm -r appliance_live_activity
   ```

   No terminal? Do the same with a file editor add-on or a network share:
   unzip the latest `appliance_mgmt.zip` from the
   [releases](https://github.com/bisman-automations/ha-appliance-mgmt/releases)
   into a new `custom_components/appliance_mgmt` folder, and delete
   `custom_components/appliance_live_activity`.
2. Restart Home Assistant. Each appliance now shows under **Appliance Mgmt**
   with the same entities, and the Appliance Live Activity entries are gone.
3. In the Marketplace, **Remove** Appliance Live Activity (nothing is set up
   with it any more), then **Download** Appliance Mgmt, so it offers you
   updates from now on.

If the old folder is still there after a restart, nothing moves and Home
Assistant shows the repair **Remove the old Appliance Live Activity folder**.
Select **Submit** to delete it, then restart.

Automations that call the **Appliance Live Activity: Update** action need the
new one, **Appliance Mgmt: Update** (`appliance_mgmt.update`). Everything that
uses the entities keeps working.

## Setup

[![Open your Home Assistant instance and start setting up Appliance Mgmt.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=appliance_mgmt)

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

### One notification per load

Each load gets its own notification, named after the wash cycle, that stays
in Notification Center after the Live Activity is gone: *✅ Towels: washed —
load it into the dryer*, which becomes *✅ Towels: load complete — washed and
dried, please take care of it* when that load finishes drying. Two loads at
once each keep their own.

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

### Oven light

Pick the oven's light in **Configure → Cooking → Oven light** and it comes on
when the oven starts and goes off when the oven turns off. An on/off light or
switch simply follows the oven. A setting with levels, like GE's **Oven
Light** (Off / High / Dim), is set to **High**, and any level other than Off
counts as on. A light that was already on when the oven started, or that you
turned off while cooking, is left alone. Leave it empty to not control the
light.

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

### Linked devices

Each appliance gets a device of this integration (e.g. "Kitchen Oven Live
Activity") marked as a service, holding its sensors, event and Probe Target.
When the appliance has a device of its own — the GE appliance, or for other
brands the device the state sensor belongs to — the two pages list each other
under **Linked devices** (Home Assistant 2026.8+), the same way UniFi Network
links its client devices. Appliances without a device of their own (e.g. a
template sensor) just get this integration's service entry, named after the
appliance.

### Tapping a notification

Tapping a Live Activity or alert opens the appliance's device page in the
Home Assistant app (the GE appliance's own page for GE setups).

### Dashboards and services

The name you see is the device name plus the entity: **Kitchen Dishwasher Live Activity Status**. A new entity id uses the appliance name only, for example `sensor.kitchen_dishwasher_status` and `sensor.kitchen_dishwasher_time_left`. An entity id that is already in Home Assistant is left as it is, including one you renamed.

- **Status** and **Progress** sensors per appliance, plus **Time Left** and
  **Finishes At** for washers, dryers, dishwashers and ovens (status attributes include
  phase, cycle, remaining minutes, door open minutes and cooktop on-time).
- **Cycles This Week** and **Average Cycle** sensors for washers, dryers,
  dishwashers and ovens.
- An **event entity** per appliance for automations: `started`,
  `scheduled`, `finished`, `cancelled` (fridges and doors: `door_left_open`,
  `door_closed`). Use it as a trigger: *Entity → Event*.
- **Probe Target** number for ovens with a meat probe.
- **Update Live Activity** button on each appliance to re-send its current
  activity if it was dismissed from the notification center.
- `appliance_mgmt.update` re-sends an appliance's Live Activity.

### Appliances dashboard

**Appliances** in the sidebar lists every appliance you have set up, on one page. The page is added once, when the integration loads, and it stays while you add, reload or remove appliances. Each appliance has a card with:

- a picture of the appliance, or its icon in its color, with its state on top (Running, Paused, Delayed start, Done or Idle; Open or Closed for doors and fridges);
- what it's doing now (the cycle phase, when a delayed start begins, when the last load finished, or how long a door has been open), with a progress bar, time left and when it'll be done while it runs;
- anything that needs you: a water leak, a blocked dryer vent, the cooktop left on, low rinse aid or detergent, a filter to clean or replace, a fridge or freezer too warm, plus the meat probe and kitchen timer;
- fridge and freezer temperatures, cycles this week, the usual cycle length and the last cycle;
- **Recent cycles** (the last 10, when each finished and how long it ran), and **Update Live Activity**.

Appliances that are running come first, then ones that need attention (a finished load, an open door, an alert), then the most recently used. With two or more appliances you can search, show only some (running now, needs attention, not running) and sort by name or type instead; the choice is remembered on each device. Tap an appliance's name to open its device page.

Admins can **Add picture** to each appliance from their phone's camera or photos, or change or remove it. Pictures use Home Assistant's own image upload, the same as person pictures (part of `default_config`). Everyone can see the dashboard; only admins can change pictures.

### Matter (Home Assistant Matter Hub)

Washers, dryers and dishwashers can be shared over Matter with [Home Assistant Matter Hub](https://riddix.github.io/home-assistant-matter-hub/supported-device-types#dishwashers-washers-and-dryers-entity-mapping-override). They then show up in Google Home, SmartThings and other Matter apps as a Dishwasher, Laundry Washer or Laundry Dryer, with their running state.

- Each has a **Power** switch, which is on while a cycle is running, paused or waiting for a delayed start. GE appliances can't be started or stopped from Home Assistant, so turning it on or off from Home Assistant or a Matter app does nothing and shows an error.
- The **Status** sensor's states are *idle*, *delayed*, *running*, *paused* and *complete*. Ovens use the same sensor; doors and fridges keep theirs as it was.

In Matter Hub, add the **Power** switch (for example `switch.kitchen_dishwasher_power`) to a bridge, and set its device type in the Entity Mapping to Dishwasher, Laundry Washer or Laundry Dryer. Matter Hub finds the **Status** sensor on the same device by itself and reports Running, Paused or Stopped, and when a cycle has finished. A delayed start counts as stopped until the cycle starts.

## Adding an appliance type

Appliance types are plugins in
`custom_components/appliance_mgmt/appliances/`. Add a file with an
`ApplianceDefinition` (see `washer.py`) and one import line in
`appliances/__init__.py`.

## Troubleshooting

- **Settings → Repairs** tells you when a phone can't receive alerts (e.g.
  after renaming it in the Companion app) or a sensor an appliance uses is
  gone.
- **Download diagnostics** (⋮ on the appliance) gives the settings, what the
  appliance reports and what the integration is doing — attach it to bug
  reports.

### Diagnostics and debug logs

When something goes wrong, download diagnostics from **Settings → Devices & services → Appliance Mgmt → ⋮ → Download diagnostics** and check the file before you share it.

For debug logs, use **Enable debug logging** on the integration page, or add this to `configuration.yaml` and restart:

```yaml
logger:
  logs:
    custom_components.appliance_mgmt: debug
```

Then open an [issue](https://github.com/bisman-automations/ha-appliance-mgmt/issues/new/choose) with the diagnostics, the log, and your Home Assistant and Appliance Mgmt versions.

## Development

Tests run inside a real Home Assistant through
[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component).
You need Python 3.14 for the current Home Assistant.

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest
```

To test against the oldest supported Home Assistant (2026.8), use Python 3.14 and
`pip install -r requirements_test_min.txt` instead.

CI runs the same checks on every push and pull request, on both Home Assistant
versions, plus hassfest, HACS validation and the shared repo standards, using the
workflows in [bisman-automations/.github](https://github.com/bisman-automations/.github).
Releases are drafted from [CHANGELOG.md](CHANGELOG.md); see [CLAUDE.md](CLAUDE.md).

## License

MIT. See [LICENSE](LICENSE).
