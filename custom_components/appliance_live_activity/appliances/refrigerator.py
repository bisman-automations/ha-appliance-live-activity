"""Refrigerator appliance definition.

Fridges don't run "cycles" the way a washer or oven does, so this plugin
disables progress-bar math (supports_progress=False) and uses the Live
Activity to show that a door is open. Point state_entity at a door
binary_sensor ("on" = open) or a door status sensor ("Open"/"Closed").
Only listed states count as open, so unrecognised states never start
an activity.
"""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="refrigerator",
        display_name="Refrigerator",
        icon="mdi:fridge",
        color="#03A9F4",
        active_states=["on", "Open", "Door Open"],
        pause_states=[],
        complete_states=[],
        idle_states=["off", "Closed", "Door Closed"],
        running_message="Door Open",
        paused_message="Paused",
        complete_message="Door Closed",
        finished_alert_message="Door closed.",
        supports_progress=False,
        unknown_is_running=False,
    )
)
