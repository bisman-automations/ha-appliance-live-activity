"""Constants for the Appliance Live Activity integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "appliance_live_activity"
STORAGE_VERSION = 1

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Config keys
CONF_SOURCE = "source"
CONF_SOURCE_DEVICE = "source_device"
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
