# Appliance Live Activity

Live Activities (iOS) and Live Updates (Android) for your washer, dryer,
dishwasher, oven and refrigerator in Home Assistant: the current phase, cycle,
a live countdown and a progress bar on your Lock Screen, then **Done** when it
finishes.

- **GE Home Appliances (SmartHQ)** — pick the appliance, everything else is
  found automatically.
- **Any other brand** (LG, Samsung, Bosch, Whirlpool, Miele…) — pick its
  state / phase / time-remaining sensors.
- **Doors left open** (fridge, freezer, garage…) — a Live Activity counting
  how long it's been open, then critical alerts until it's closed.

Two ways to use it — pick one per appliance:

| | **Integration** (HACS) | **Blueprint** (GE only) |
|---|---|---|
| Setup | Settings → Add Integration | Import blueprint, create an automation |
| Brands | Any | GE Home (SmartHQ) |
| Several appliances | One entry each | One automation each |
| Dashboard sensors (status, progress) | ✅ | — |
| Survives restarts mid-cycle | ✅ (keeps progress) | ✅ (progress restarts from current estimate) |
| Installs the GE blueprint for you | ✅ | — |

## Requirements

- Home Assistant **2026.7** or newer
- Companion app: iOS **17.2+** (Live Activities) or Android **16+** (Live Updates)

## Integration

### Install via HACS

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/donavanbecker/ha-appliance-live-activity`, category
   **Integration**.
2. Install **Appliance Live Activity** and restart Home Assistant.
3. Settings → Devices & services → **Add integration** → *Appliance Live Activity*.

### Setup

- **GE appliance (SmartHQ) — automatic:** choose the GE device. The state,
  sub-cycle, cycle, time-remaining, end-of-cycle and door entities are found
  for you. Then choose your phones.
- **Any appliance:** choose the appliance type, then its entities (only the
  state sensor is required), then your phones.

Phones, the "finished" alert, dismiss delay, icon and color can be changed
later with **Configure**.

### How it behaves

- **Starts** a Live Activity when the appliance starts running.
- **Updates only when something changes** — state, phase, cycle, or the
  appliance's estimate drifting more than 3 minutes from the countdown. The
  phone runs the countdown itself (`chronometer`), so there's no update every
  minute for iOS to throttle.
- Reads the time-remaining unit from the sensor (GE reports **hours** for
  dishwashers and ovens, **minutes** for laundry).
- **Finishes once:** shows *Done* with a full progress bar, optionally sends
  a regular time-sensitive "finished" alert, and **ends the Live Activity when
  the door opens** (or after 30 minutes).
- **Cancelled** cycles (stopped with time left) just end the activity.
- **Refrigerator / freezer doors:** after a door has been open 30 s (so quick
  grabs don't start one), a Live Activity counts up how long it's been open.
  After 5 minutes it turns red and **critical alerts** repeat every minute
  until the door is closed. When it closes, the alerts are removed and the
  Live Activity shows **Closed** for a minute, then goes away. GE fridges get
  every door (fridge left/right, freezer) automatically; all three timings
  are configurable.
- Adds **Status** and **Progress** sensors per appliance for dashboards.
- Service `appliance_live_activity.update` re-sends the activity on demand.

### Adding an appliance type

Appliance types are plugins in
`custom_components/appliance_live_activity/appliances/`. Add a file with an
`ApplianceDefinition` (see `washer.py`) and one import line in
`appliances/__init__.py` — nothing else changes.

## Blueprint (GE Home / SmartHQ)

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdonavanbecker%2Fha-appliance-live-activity%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fge_appliance_live_activity.yaml)

`blueprints/automation/ge_appliance_live_activity.yaml` does the same thing
for one GE appliance without installing the integration: pick the GE device
and your phones. It is also installed automatically to
`blueprints/automation/appliance_live_activity/` when you install the
integration (and kept up to date, unless you've edited your copy).

## Blueprint: Door Left Open (any door)

[![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdonavanbecker%2Fha-appliance-live-activity%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fdoor_left_open.yaml)

`blueprints/automation/door_left_open.yaml` — the same door flow for any
door `binary_sensor` (garage, patio, a fridge from another brand), with extras:
optional Snooze button, escalation to more phones, speaker announcements and
turning lights red.

> Use either the integration **or** the blueprint for a given appliance, not
> both — they would send competing updates to the same phone.

## Development

- `blueprints/automation/` is the source of truth for blueprints; run
  `scripts/sync_blueprints.sh` to copy them into the integration (CI checks
  the copies match).
- Tests: `pip install pytest-homeassistant-custom-component && pytest`

## License

MIT — see [LICENSE](LICENSE).
