"""Dishwasher appliance definition."""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="dishwasher",
        display_name="Dishwasher",
        icon="mdi:dishwasher",
        color="#00BCD4",
        active_states=["Run", "Running", "run", "running", "Wash", "Rinse", "Dry"],
        pause_states=["Paused", "Pause", "paused"],
        complete_states=["Finished", "Complete", "complete", "finished", "Clean"],
        running_message="Washing Dishes",
        paused_message="Paused",
        complete_message="Dishes Clean",
    )
)
