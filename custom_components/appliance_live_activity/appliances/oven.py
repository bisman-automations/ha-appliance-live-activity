"""Oven appliance definition.

Ovens commonly expose a distinct "Preheating" phase before the cook cycle
proper begins. That phase is handled automatically because the coordinator
already prefers phase_entity (sub-cycle sensor) over state_entity for the
displayed message -- "Preheating" will show up as-is without any
oven-specific code.
"""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="oven",
        display_name="Oven",
        icon="mdi:stove",
        color="#F44336",
        active_states=["Run", "Running", "run", "running", "Bake", "Baking", "Preheat", "Preheating"],
        pause_states=["Paused", "Pause", "paused"],
        complete_states=["Finished", "Off", "off", "Complete", "complete", "finished"],
        running_message="Baking",
        paused_message="Paused",
        complete_message="Oven Off",
    )
)
