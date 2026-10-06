"""Generic door (garage, patio, gate, chest freezer...).

Uses the same door monitoring as refrigerators (DoorCoordinator): Live
Activity while open, critical alerts if left open, then "Closed".
"""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="door",
        display_name="Door (garage, patio, gate…)",
        icon="mdi:door-open",
        color="#FF9800",
        active_states=["on", "Open", "Opening", "Door Open"],
        pause_states=[],
        complete_states=[],
        idle_states=["off", "Closed", "Closing", "Door Closed"],
        running_message="Open",
        complete_message="Closed",
        finished_alert_message="Closed.",
        supports_progress=False,
        unknown_is_running=False,
    )
)
