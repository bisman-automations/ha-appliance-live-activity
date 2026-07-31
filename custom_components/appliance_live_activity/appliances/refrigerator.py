"""Refrigerator appliance definition.

Fridges don't run "cycles" the way a washer or oven does, so this plugin
disables progress-bar math (supports_progress=False) and repurposes the
active/complete states for door-open monitoring by default. Point
state_entity at a door sensor (or the fridge's overall status sensor if
your integration exposes one) and override active/complete states in the
config flow if your model uses different text, e.g. an ice-maker-running
sensor instead of a door sensor.
"""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="refrigerator",
        display_name="Refrigerator",
        icon="mdi:fridge",
        color="#03A9F4",
        active_states=["Open", "open", "Door Open", "door open"],
        pause_states=[],
        complete_states=["Closed", "closed", "Door Closed", "door closed"],
        running_message="Door Open",
        paused_message="Paused",
        complete_message="Door Closed",
        supports_progress=False,
    )
)
