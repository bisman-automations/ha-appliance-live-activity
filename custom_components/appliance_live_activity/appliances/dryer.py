"""Dryer appliance definition."""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="dryer",
        display_name="Dryer",
        icon="mdi:tumble-dryer",
        color="#FF9800",
        active_states=["Run", "Running", "run", "running", "Dry", "Drying"],
        pause_states=["Paused", "Pause", "paused"],
        complete_states=["Finished", "End of Cycle", "Complete", "complete", "finished"],
        running_message="Drying",
        paused_message="Paused",
        complete_message="Dry Complete",
    )
)
