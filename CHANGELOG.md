# Changelog

## 1.0.0

Initial release.

- Config-flow based setup: pick an appliance type, its entities, and which
  phones get notified -- no YAML editing required.
- Five appliance plugins: washer, dryer, dishwasher, oven, refrigerator.
- Generic coordinator ported from the original `applianceminder.yaml`
  blueprint: running / paused / complete detection, progress percentage,
  and total-cycle-length capture, now shared by every appliance instead of
  duplicated per automation.
- Persists total cycle length across HA restarts (no `input_number` helper
  needed).
- Status and Progress sensors per appliance for dashboards.
- `appliance_live_activity.update` service for forcing a manual refresh.
- Optional thin blueprint for triggering a manual refresh from a custom
  trigger.
