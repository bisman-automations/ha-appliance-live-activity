"""Constants for the Appliance Live Activity integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "appliance_live_activity"
STORAGE_VERSION = 1

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.EVENT]

# Config keys
CONF_SOURCE = "source"
CONF_SOURCE_DEVICE = "source_device"
CONF_GE_DISCOVERY = "ge_discovery"
CONF_APPLIANCE_TYPE = "appliance_type"
CONF_NAME = "name"
CONF_STATE_ENTITY = "state_entity"
CONF_CYCLE_ENTITY = "cycle_entity"
CONF_PHASE_ENTITY = "phase_entity"
CONF_REMAINING_ENTITY = "remaining_entity"
CONF_DONE_ENTITY = "done_entity"
CONF_DOOR_ENTITY = "door_entity"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_ACTIVE_STATES = "active_states"
CONF_PAUSE_STATES = "pause_states"
CONF_COMPLETE_STATES = "complete_states"
CONF_IDLE_STATES = "idle_states"
CONF_ICON = "icon"
CONF_ICON_COLOR = "icon_color"
CONF_NOTIFICATION_TAG = "notification_tag"
CONF_DEVICES = "devices"
CONF_FINISHED_ALERT = "finished_alert"
CONF_DISMISS_MINUTES = "dismiss_minutes"
# Door monitoring (refrigerator / freezer)
CONF_DOOR_ENTITIES = "door_entities"
CONF_OPEN_DELAY_SECONDS = "open_delay_seconds"
CONF_CRITICAL_AFTER_MINUTES = "critical_after_minutes"
CONF_CRITICAL_REPEAT_MINUTES = "critical_repeat_minutes"
CONF_ESCALATION_DEVICES = "escalation_devices"
CONF_ESCALATE_AFTER = "escalate_after"
CONF_ALERT_LIGHTS = "alert_lights"
# Announcements (doors + cooktop)
CONF_TTS_ENTITY = "tts_entity"
CONF_SPEAKERS = "speakers"
# Cooktop left on (ovens / ranges)
CONF_COOKTOP_ENTITIES = "cooktop_entities"
CONF_COOKTOP_ALERT_MINUTES = "cooktop_alert_minutes"
CONF_COOKTOP_REPEAT_MINUTES = "cooktop_repeat_minutes"
# Oven preheat
CONF_TARGET_TEMPERATURE_ENTITY = "target_temperature_entity"
CONF_PREHEAT_ALERT = "preheat_alert"
# Leak sensors (any appliance)
CONF_LEAK_ENTITIES = "leak_entities"
CONF_LEAK_REPEAT_MINUTES = "leak_repeat_minutes"
# Washer -> dryer reminder
CONF_MOVE_REMINDER_MINUTES = "move_reminder_minutes"
CONF_MOVE_REPEAT_MINUTES = "move_repeat_minutes"
CONF_MOVE_MAX_REMINDERS = "move_max_reminders"
CONF_DRYER_ENTITY = "dryer_entity"
CONF_DRYER_START_ENTITY = "dryer_start_entity"
# Delayed start
CONF_DELAY_ENTITY = "delay_entity"
CONF_DELAY_START = "delay_start"
# Door alert snooze button (0 = no button)
CONF_SNOOZE_MINUTES = "snooze_minutes"
# Oven extras
CONF_OVEN_CAVITY = "oven_cavity"
CONF_TIMER_ENTITY = "timer_entity"
CONF_PROBE_ENTITY = "probe_entity"
# Dryer extras
CONF_TUMBLE_ENTITY = "tumble_entity"
CONF_VENT_ENTITY = "vent_entity"
# Washer + dryer share one Live Activity
CONF_COMBINE_LAUNDRY = "combine_laundry"
# Refill reminders / maintenance
CONF_SUPPLY_ENTITIES = "supply_entities"
CONF_SUPPLY_LOW = "supply_low"
CONF_FILTER_ENTITY = "filter_entity"
# Fridge temperatures / ice
CONF_FRIDGE_TEMP_ENTITY = "fridge_temp_entity"
CONF_FREEZER_TEMP_ENTITY = "freezer_temp_entity"
CONF_ICE_ENTITY = "ice_entity"
CONF_FRIDGE_MAX_TEMP = "fridge_max_temp"
CONF_FREEZER_MAX_TEMP = "freezer_max_temp"
CONF_WARM_MINUTES = "warm_minutes"
CONF_ICE_FULL_ALERT = "ice_full_alert"
# Quiet hours (non-critical alerts wait until they end)
CONF_QUIET_START = "quiet_start"
CONF_QUIET_END = "quiet_end"
# Only send regular alerts to phones of people who are home
CONF_ONLY_HOME = "only_home"
# Dishwasher "clean" sensor: keep "ready to unload" up until the door opens
CONF_CLEAN_ENTITY = "clean_entity"

# Cycle events (event entity)
EVENT_STARTED = "started"
EVENT_FINISHED = "finished"
EVENT_CANCELLED = "cancelled"
EVENT_SCHEDULED = "scheduled"
EVENT_DOOR_LEFT_OPEN = "door_left_open"
EVENT_DOOR_CLOSED = "door_closed"
CYCLE_EVENTS = [EVENT_STARTED, EVENT_FINISHED, EVENT_CANCELLED, EVENT_SCHEDULED]
DOOR_EVENTS = [EVENT_DOOR_LEFT_OPEN, EVENT_DOOR_CLOSED]

# Cycle history kept per appliance
HISTORY_MAX = 100
HISTORY_AVERAGE_OF = 10
# Problems are reported in Settings -> Repairs after this long (lets other
# integrations finish starting first), then rechecked this often
HEALTH_FIRST_CHECK_SECONDS = 300
HEALTH_CHECK_MINUTES = 30

# Appliance types handled by the door monitor
DOOR_TYPES = ("refrigerator", "door")

# Setup sources
SOURCE_GE_HOME = "ge_home"
SOURCE_MANUAL = "manual"

# Integration domain of the GE Home Appliances (SmartHQ) custom integration
GE_HOME_DOMAIN = "ge_home"

# Status values reported by sensors / used internally
STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETE = "complete"
STATUS_DELAYED = "delayed"

# Behaviour tuning
DEFAULT_DISMISS_MINUTES = 30
# Re-send a running update only if the appliance's own estimate drifts this many
# minutes away from the countdown the phone is already showing.
DRIFT_MINUTES = 3
# If an appliance stops with this many minutes (or fewer) left, treat it as
# finished rather than cancelled (for appliances without an end-of-cycle signal).
FINISHED_THRESHOLD_MINUTES = 5

# Door monitoring defaults
DEFAULT_OPEN_DELAY_SECONDS = 30  # ignore quick grabs; saves iOS push-to-start budget
DEFAULT_CRITICAL_AFTER_MINUTES = 5
DEFAULT_CRITICAL_REPEAT_MINUTES = 1
DEFAULT_ESCALATE_AFTER = 0  # 0 = escalate with the first critical alert
CLOSED_DISPLAY_SECONDS = 60  # show "Closed" this long before ending the activity

# Cooktop defaults
DEFAULT_COOKTOP_ALERT_MINUTES = 30
DEFAULT_COOKTOP_REPEAT_MINUTES = 15

# Oven preheat: "reached" when within this many degrees of the set temperature
PREHEAT_TOLERANCE = 5

# Leak defaults
DEFAULT_LEAK_REPEAT_MINUTES = 5

# Washer -> dryer reminder defaults (0 minutes = off)
DEFAULT_MOVE_REMINDER_MINUTES = 15
DEFAULT_MOVE_REPEAT_MINUTES = 15
DEFAULT_MOVE_MAX_REMINDERS = 3

# Door alert snooze
DEFAULT_SNOOZE_MINUTES = 10

# Refill reminders: a count (loads, pods, sheets) at or below this is "low";
# a percentage at or below SUPPLY_LOW_PERCENT is "low"
DEFAULT_SUPPLY_LOW = 3
SUPPLY_LOW_PERCENT = 25

# Blocked dryer vent: repeat the critical alert this often while it's flagged
VENT_REPEAT_MINUTES = 30

# Dryer "unload me" reminder defaults (0 minutes = off)
DEFAULT_DRYER_REMINDER_MINUTES = 30
DEFAULT_DRYER_REPEAT_MINUTES = 30
DEFAULT_DRYER_MAX_REMINDERS = 2

# Fridge / freezer too warm (in the Home Assistant unit system's unit)
DEFAULT_FRIDGE_MAX_F = 45
DEFAULT_FREEZER_MAX_F = 15
DEFAULT_FRIDGE_MAX_C = 7
DEFAULT_FREEZER_MAX_C = -9
DEFAULT_WARM_MINUTES = 30
WARM_REPEAT_MINUTES = 60

# Notification action buttons (suffixes; the full action id is
# "<NOTIFICATION TAG>_<SUFFIX>" so every appliance has its own)
ACTION_START_DRYER = "START_DRYER"
ACTION_LAUNDRY_MOVED = "LAUNDRY_MOVED"
ACTION_SILENCE_LEAK = "SILENCE_LEAK"
ACTION_SNOOZE_DOOR = "SNOOZE_DOOR"

# Event fired by the Companion app when a notification action is tapped
EVENT_NOTIFICATION_ACTION = "mobile_app_notification_action"

# States that always mean "not running", regardless of appliance type.
UNAVAILABLE_STATES = {"", "unknown", "unavailable", "none"}

# Default idle states shared by all appliances (case-insensitive exact match).
DEFAULT_IDLE_STATES = [
    "Off",
    "Ready",
    "Standby",
    "Low Power",
    "Power Up",
    "Power Off",
    "Idle",
    "N/A",
    "---",
    "Delay Run",
    "Delay Start",
    "Delay",
    "Delayed Start",
]
