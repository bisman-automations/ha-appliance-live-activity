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
CLOSED_DISPLAY_SECONDS = 60  # show "Closed" this long before ending the activity

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
]
