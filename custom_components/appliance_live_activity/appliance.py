"""Appliance plugin definitions.

Each appliance module (appliances/washer.py, appliances/dryer.py, ...)
registers an ApplianceDefinition describing its default states, icon,
color, and messaging. The coordinator is completely generic and only
ever talks to this registry -- adding a new appliance type never
requires touching coordinator.py, notify.py, or config_flow.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ApplianceDefinition:
    """Describes one appliance type's default behavior."""

    key: str
    display_name: str
    icon: str
    color: str
    active_states: list[str]
    pause_states: list[str] = field(default_factory=list)
    complete_states: list[str] = field(default_factory=list)
    running_message: str = "Running"
    paused_message: str = "Paused"
    complete_message: str = "Cycle Complete"
    supports_progress: bool = True


APPLIANCE_REGISTRY: dict[str, ApplianceDefinition] = {}


def register(definition: ApplianceDefinition) -> None:
    """Register an appliance definition. Called by appliances/*.py at import time."""
    APPLIANCE_REGISTRY[definition.key] = definition
