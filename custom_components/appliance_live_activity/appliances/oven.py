"""Oven appliance definition.

Ovens commonly expose a distinct "Preheating" phase before the cook cycle
proper begins. That phase is handled automatically because the coordinator
prefers phase_entity (cook mode / sub-cycle sensor) over state_entity for
the displayed message.

"Off" is an *idle* state, not a completion state: turning the oven off
only counts as "finished" when a cook timer was running and had (nearly)
run out -- the coordinator handles that with FINISHED_THRESHOLD_MINUTES.
"""
from ..appliance import ApplianceDefinition, register

register(
    ApplianceDefinition(
        key="oven",
        display_name="Oven",
        icon="mdi:stove",
        color="#F44336",
        active_states=["Run", "Running", "Bake", "Baking", "Preheat", "Preheating", "Broil", "Convection Bake"],
        pause_states=["Pause"],
        complete_states=["Finished", "Complete", "Done"],
        running_message="Cooking",
        paused_message="Paused",
        complete_message="Cooking Done",
        finished_alert_message="Cooking is done.",
    )
)
