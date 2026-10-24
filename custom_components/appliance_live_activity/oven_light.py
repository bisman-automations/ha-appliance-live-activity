"""Oven light on while the oven is on.

When enabled in Configure → Cooking, the oven light (a GE "Oven Light"
select, or any light / switch) turns on when the oven starts heating and
off again when the oven turns off. A light that was already on when the
oven started is left alone, and so is one the user turned off while
cooking. A blip where the oven reports "unavailable" changes nothing.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON

from .const import UNAVAILABLE_STATES

if TYPE_CHECKING:
    from .coordinator import ApplianceCoordinator

_LOGGER = logging.getLogger(__name__)

# Preferred "on" level for a select-based light (GE: Off / High / Dim)
SELECT_ON_OPTIONS = ("High", "Bright", "On")


class OvenLight:
    """Follows the oven's on/off state with its light."""

    def __init__(self, coordinator: ApplianceCoordinator, entity_id: str) -> None:
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.entity_id = entity_id
        # Oven on/off as last seen (None until the first evaluation)
        self._oven_on: bool | None = None
        # We turned the light on for this cook (persisted across restarts)
        self.turned_on = False

    def _light_state(self) -> str | None:
        state = self.hass.states.get(self.entity_id)
        if state is None or state.state.lower() in UNAVAILABLE_STATES:
            return None
        return state.state

    def light_is_on(self) -> bool | None:
        state = self._light_state()
        if state is None:
            return None
        return state.lower() not in (STATE_OFF, "0")

    async def async_update(self, oven_on: bool, oven_raw_state: str) -> None:
        """Called on every evaluation with whether the oven is on."""
        if oven_raw_state.strip().lower() in UNAVAILABLE_STATES:
            return  # unknown whether the oven is on: leave the light as it is
        first = self._oven_on is None
        if oven_on == self._oven_on:
            return
        self._oven_on = oven_on
        light_on = self.light_is_on()
        if light_on is None:
            return  # light unavailable
        if oven_on:
            if light_on:
                # Already on: the user's light, not ours -- unless we turned it
                # on before a restart
                if not (first and self.turned_on):
                    self.turned_on = False
                return
            await self._async_set(True)
            self.turned_on = True
        else:
            if self.turned_on and light_on:
                await self._async_set(False)
            self.turned_on = False

    async def _async_set(self, on: bool) -> None:
        domain = self.entity_id.split(".", 1)[0]
        try:
            if domain == "select":
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {ATTR_ENTITY_ID: self.entity_id, "option": self._select_option(on)},
                    blocking=True,
                )
            else:
                await self.hass.services.async_call(
                    domain,
                    "turn_on" if on else "turn_off",
                    {ATTR_ENTITY_ID: self.entity_id},
                    blocking=True,
                )
        except Exception as err:  # noqa: BLE001 - a light failing must not break the Live Activity
            _LOGGER.warning(
                "%s: could not turn the oven light %s: %s",
                self.coordinator.name,
                STATE_ON if on else STATE_OFF,
                err,
            )

    def _select_option(self, on: bool) -> str:
        state = self.hass.states.get(self.entity_id)
        options = list(state.attributes.get("options") or []) if state else []
        if not on:
            return next((o for o in options if o.lower() == STATE_OFF), "Off")
        for wanted in SELECT_ON_OPTIONS:
            match = next((o for o in options if o.lower() == wanted.lower()), None)
            if match:
                return match
        return next((o for o in options if o.lower() != STATE_OFF), "High")
