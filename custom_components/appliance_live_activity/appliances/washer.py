"""Washer appliance definition."""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="washer",
        display_name="Washer",
        icon="mdi:washing-machine",
        color="#2196F3",
        active_states=["Run", "Running", "Wash", "Washing", "Rinse", "Spin"],
        pause_states=["Pause"],
        complete_states=["Finished", "End Of Cycle", "Complete", "Done"],
        running_message="Washing",
        paused_message="Paused",
        complete_message="Wash Complete",
        finished_alert_message="Time to move the laundry.",
    )
)
