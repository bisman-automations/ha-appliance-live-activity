"""Water leak alerts for any appliance.

* Any selected moisture sensor turns on -> **critical** alert right away
  (bypasses Silent / Focus) and an optional speaker announcement.
* Repeats every ``repeat_minutes`` (default 5) while still wet.
* All sensors dry -> the critical alert is replaced with "leak cleared".
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import ATTR_FRIENDLY_NAME, STATE_ON
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .notify import async_send_leak, async_send_leak_cleared, async_speak

if TYPE_CHECKING:
    from .coordinator import ApplianceCoordinator

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=30)


class LeakMonitor:
    """Watches leak (moisture) sensors for one appliance."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ApplianceCoordinator,
        *,
        entities: list[str],
        repeat_minutes: float,
        tts_entity: str | None,
        speakers: list[str],
        extra_devices: list[str],
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entities = entities
        self.repeat = max(60.0, repeat_minutes * 60)
        self.tts_entity = tts_entity
        self.speakers = speakers
        self.extra_devices = extra_devices
        self.tag = f"{coordinator.notification_tag}_leak"

        self._last_alert: float | None = None
        self._unsubs: list[CALLBACK_TYPE] = []

    @property
    def wet(self) -> list[str]:
        """Entity ids currently reporting water."""
        return [
            e
            for e in self.entities
            if (state := self.hass.states.get(e)) is not None and state.state == STATE_ON
        ]

    @property
    def devices(self) -> list[str]:
        return list(dict.fromkeys(self.coordinator.devices + self.extra_devices))

    def _label(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        name = (state.attributes.get(ATTR_FRIENDLY_NAME) if state else None) or entity_id
        # "Kitchen Dishwasher Leak Sensor Water leak" -> "Leak Sensor"
        name = name.removesuffix(" Water leak").removesuffix(" Moisture")
        if name.lower().startswith(self.coordinator.name.lower() + " "):
            name = name[len(self.coordinator.name) + 1 :]
        return name or "Leak sensor"

    async def async_setup(self) -> None:
        self._unsubs.append(
            async_track_state_change_event(self.hass, self.entities, self._handle_change)
        )
        self._unsubs.append(async_track_time_interval(self.hass, self._handle_change, TICK))
        await self.async_evaluate()

    async def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _handle_change(self, _event=None) -> None:
        self.hass.async_create_task(self.async_evaluate())

    async def async_evaluate(self) -> None:
        now = dt_util.utcnow().timestamp()
        wet = self.wet
        if not wet:
            if self._last_alert is not None:
                self._last_alert = None
                await async_send_leak_cleared(
                    self.hass, self.coordinator, tag=self.tag, devices=self.devices
                )
                self.coordinator.async_update_listeners()
            return

        if self._last_alert is not None and now - self._last_alert < self.repeat - 1:
            return
        first = self._last_alert is None
        self._last_alert = now
        labels = [self._label(e) for e in wet]
        _LOGGER.warning("%s: water leak detected by %s", self.coordinator.name, ", ".join(wet))
        await async_send_leak(
            self.hass, self.coordinator, tag=self.tag, sensors=labels, devices=self.devices
        )
        await async_speak(
            self.hass,
            self.tts_entity,
            self.speakers,
            f"Warning. Water leak detected at the {self.coordinator.name}.",
        )
        if first:
            self.coordinator.async_update_listeners()
