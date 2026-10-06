"""Dryer appliance definition."""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="dryer",
        display_name="Dryer",
        icon="mdi:tumble-dryer",
        color="#FF9800",
        active_states=["Run", "Running", "Dry", "Drying", "Cool Down"],
        pause_states=["Pause"],
        complete_states=["Finished", "End Of Cycle", "Complete", "Done"],
        running_message="Drying",
        paused_message="Paused",
        complete_message="Dry Complete",
        finished_alert_message="Laundry is dry.",
    )
)
