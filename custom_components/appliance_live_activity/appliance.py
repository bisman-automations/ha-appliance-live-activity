"""Appliance plugin definitions.

Each appliance module (appliances/washer.py, appliances/dryer.py, ...)
registers an ApplianceDefinition describing its default states, icon,
color, and messaging. The coordinator is completely generic and only
ever talks to this registry -- adding a new appliance type never
requires touching coordinator.py, notify.py, or config_flow.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .const import DEFAULT_IDLE_STATES


@dataclass
class ApplianceDefinition:
    """Describes one appliance type's default behavior.

    State matching is case-insensitive:
    - ``active_states`` / ``idle_states``: exact match
    - ``pause_states`` / ``complete_states``: exact match *or* substring
      (so "Pause" also matches "Paused", and "End Of Cycle" matches
      "End Of Cycle - Clean")
    Any state that matches none of the lists counts as running when
    ``unknown_is_running`` is true (the default), because appliance
    integrations use many different words for "running" ("Cycle Active",
    "Bake", "Wash"...), but very few for "off".
    """

    key: str
    display_name: str
    icon: str
    color: str
    active_states: list[str]
    pause_states: list[str] = field(default_factory=list)
    complete_states: list[str] = field(default_factory=list)
    idle_states: list[str] = field(default_factory=lambda: list(DEFAULT_IDLE_STATES))
    running_message: str = "Running"
    paused_message: str = "Paused"
    complete_message: str = "Cycle Complete"
    finished_alert_message: str = "Cycle complete."
    supports_progress: bool = True
    unknown_is_running: bool = True


APPLIANCE_REGISTRY: dict[str, ApplianceDefinition] = {}


def register(definition: ApplianceDefinition) -> None:
    """Register an appliance definition. Called by appliances/*.py at import time."""
    APPLIANCE_REGISTRY[definition.key] = definition
