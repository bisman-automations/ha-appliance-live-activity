# Appliance Live Activity

Turn any Home Assistant appliance sensor into rich phone notifications — iOS
Live Activities today, with Android progress notifications and Wear OS
planned — for washers, dryers, dishwashers, ovens, and refrigerators.
Brand-agnostic: it works with GE, LG, Samsung, Bosch, Whirlpool, Miele, or
any appliance integration that exposes state/phase/remaining-time sensors.

This started as a single blueprint (`applianceminder.yaml`) that grew a
full copy of its progress/pause/completion logic for every appliance type.
This repo replaces that duplication with one generic integration: appliance
types are small plugins, and the state-machine + notification logic lives
in exactly one place.

## Install via HACS

1. HACS → Integrations → ⋮ → Custom repositories → add this repo URL,
   category **Integration**.
2. Install **Appliance Live Activity**, restart Home Assistant.
3. Settings → Devices & Services → Add Integration → **Appliance Live
   Activity**.

## Setup (config flow, no YAML)

1. **Pick an appliance type** — Washer, Dryer, Dishwasher, Oven, or
   Refrigerator — and give it a name.
2. **Pick entities** — a state sensor is required; phase/cycle/remaining-time
   sensors are optional and improve the notification detail.
3. **Pick phones** — choose which mobile-app devices get the Live Activity.

Repeat for each appliance. Options (icon, color, devices) can be changed
later from the integration's **Configure** button.

## What it does

- Watches your state/phase sensors and a 1-minute timer, same triggers as
  the original blueprint.
- Classifies each update as **running / paused / complete / idle** using
  per-appliance default state lists (overridable per instance).
- Captures the starting "remaining minutes" once per cycle and computes
  progress percentage from it — persisted across HA restarts, no
  `input_number` helper required.
- Sends a `notify.*` call per selected phone with `tag`, `live_update`,
  `progress`, `critical_text`, and icon/color, matching the fields the iOS
  Companion App uses to drive a Live Activity.
- Exposes a **Status** sensor (state + phase/cycle/remaining as attributes)
  and a **Progress** sensor per appliance for dashboards.

## Adding a new appliance type

Appliance types are plugins under `custom_components/appliance_live_activity/appliances/`.
To add one (microwave, air fryer, coffee maker, robot vacuum...):

1. Create `appliances/my_appliance.py` with an `ApplianceDefinition` (see
   `washer.py` for the shortest example).
2. Add one import line to `appliances/__init__.py`.

No changes needed anywhere else — the config flow, coordinator, and
notification logic all read from the plugin registry.

## Optional blueprint

`blueprints/automation/appliance_live_activity.yaml` is a thin helper that
just calls the `appliance_live_activity.update` service. Most users won't
need it, since the integration tracks state changes on its own — it's there
for edge cases like forcing a refresh from a physical button or on HA
startup.

## Roadmap

- **v1.1** — smart appliance discovery, Android progress notifications,
  Wear OS / Apple Watch companions.
- **v1.2** — microwave, air fryer, range, coffee maker, dehumidifier plugins.
- **v2.0** — Matter appliance support, energy dashboard integration,
  statistics, dashboard cards.

## License

MIT — see [LICENSE](LICENSE).
