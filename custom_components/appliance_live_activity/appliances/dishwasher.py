"""Dishwasher appliance definition.

GE Home (SmartHQ) dishwashers report "Cycle Active" on their operating-mode
sensor while running; that's covered by the active list (and by
``unknown_is_running`` for other integrations' wording).
"""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="dishwasher",
        display_name="Dishwasher",
        icon="mdi:dishwasher",
        color="#00BCD4",
        active_states=["Run", "Running", "Cycle Active", "Wash", "Rinse", "Dry"],
        pause_states=["Pause"],
        complete_states=["Finished", "End Of Cycle", "Complete", "Done"],
        running_message="Washing Dishes",
        paused_message="Paused",
        complete_message="Dishes Clean",
        finished_alert_message="Dishes are clean.",
    )
)
