"""Refrigerator / freezer appliance definition.

Fridges don't run cycles; this type uses DoorCoordinator (door.py):
a Live Activity while a door is open, critical alerts if it stays open,
then "Closed" for a minute. Point it at one or more door binary sensors
("on" = open) or door status sensors ("Open"/"Closed").
"""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="refrigerator",
        display_name="Refrigerator / Freezer",
        icon="mdi:fridge",
        color="#03A9F4",
        active_states=["on", "Open", "Door Open"],
        pause_states=[],
        complete_states=[],
        idle_states=["off", "Closed", "Door Closed"],
        running_message="Door Open",
        paused_message="Paused",
        complete_message="Closed",
        finished_alert_message="Door closed.",
        supports_progress=False,
        unknown_is_running=False,
    )
)
