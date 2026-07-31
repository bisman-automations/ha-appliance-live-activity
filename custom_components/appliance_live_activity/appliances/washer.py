"""Washer appliance definition."""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="washer",
        display_name="Washer",
        icon="mdi:washing-machine",
        color="#2196F3",
        active_states=["Run", "Running", "run", "running", "Wash"],
        pause_states=["Paused", "Pause", "paused"],
        complete_states=["Finished", "End of Cycle", "Complete", "complete", "finished"],
        running_message="Washing",
        paused_message="Paused",
        complete_message="Wash Complete",
    )
)
