"""Constants for the Appliance Live Activity integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "appliance_live_activity"
STORAGE_VERSION = 1

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Config keys
CONF_APPLIANCE_TYPE = "appliance_type"
CONF_NAME = "name"
CONF_STATE_ENTITY = "state_entity"
CONF_CYCLE_ENTITY = "cycle_entity"
CONF_PHASE_ENTITY = "phase_entity"
CONF_REMAINING_ENTITY = "remaining_entity"
CONF_ACTIVE_STATES = "active_states"
CONF_PAUSE_STATES = "pause_states"
CONF_COMPLETE_STATES = "complete_states"
CONF_ICON = "icon"
CONF_ICON_COLOR = "icon_color"
CONF_NOTIFICATION_TAG = "notification_tag"
CONF_DEVICES = "devices"

# Status values reported by sensors / used internally
STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_PAUSED = "paused"
STATUS_COMPLETE = "complete"
