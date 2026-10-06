"""Cooktop left-on alerts for ovens / ranges.

Ported from the "Critical Gas Cooktop Left On Alert" blueprint:

* Any cooktop sensor on continuously for ``alert_minutes`` (default 30)
  -> critical notification (bypasses Silent / Focus) and an optional
  speaker announcement.
* Repeats every ``repeat_minutes`` (default 15) while still on.
* **Acknowledge** button stops the repeats for this time the cooktop is on.
* Turning the cooktop off stops everything and removes the notification.

This never turns the cooktop off.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import EVENT_NOTIFICATION_ACTION
from .notify import async_clear_tag, async_send_cooktop_critical, async_speak

if TYPE_CHECKING:
    from .coordinator import ApplianceCoordinator

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=30)


class CooktopMonitor:
    """Watches cooktop sensors for one oven / range."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: ApplianceCoordinator,
        *,
        entities: list[str],
        alert_minutes: float,
        repeat_minutes: float,
        tts_entity: str | None,
        speakers: list[str],
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entities = entities
        self.alert_after = alert_minutes * 60
        self.repeat = max(60.0, repeat_minutes * 60)
        self.tts_entity = tts_entity
        self.speakers = speakers
        self.tag = f"{coordinator.notification_tag}_cooktop"
        self.ack_action = f"{coordinator.notification_tag}_cooktop_ack".upper()

        self._on_since: float | None = None
        self._last_alert: float | None = None
        self._acknowledged = False
        self._unsubs: list[CALLBACK_TYPE] = []

    @property
    def is_on(self) -> bool:
        return any(
            (state := self.hass.states.get(e)) is not None and state.state == STATE_ON
            for e in self.entities
        )

    @property
    def minutes_on(self) -> float:
        if self._on_since is None:
            return 0.0
        return (dt_util.utcnow().timestamp() - self._on_since) / 60

    async def async_setup(self) -> None:
        self._unsubs.append(
            async_track_state_change_event(self.hass, self.entities, self._handle_change)
        )
        self._unsubs.append(async_track_time_interval(self.hass, self._handle_change, TICK))
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_NOTIFICATION_ACTION, self._handle_action)
        )
        await self.async_evaluate()

    async def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _handle_change(self, _event=None) -> None:
        self.hass.async_create_task(self.async_evaluate())

    @callback
    def _handle_action(self, event: Event) -> None:
        if event.data.get("action") == self.ack_action and self._on_since is not None:
            self._acknowledged = True
            self.hass.async_create_task(async_clear_tag(self.hass, self.coordinator, self.tag))

    async def async_evaluate(self) -> None:
        now = dt_util.utcnow().timestamp()
        if not self.is_on:
            if self._last_alert is not None and self.coordinator.devices:
                await async_clear_tag(self.hass, self.coordinator, self.tag)
            self._on_since = None
            self._last_alert = None
            self._acknowledged = False
            self.coordinator.async_update_listeners()
            return

        if self._on_since is None:
            on_states = [
                state.last_changed.timestamp()
                for e in self.entities
                if (state := self.hass.states.get(e)) is not None and state.state == STATE_ON
            ]
            self._on_since = min(on_states) if on_states else now
            self.coordinator.async_update_listeners()

        if self._acknowledged or now - self._on_since < self.alert_after:
            return
        if self._last_alert is not None and now - self._last_alert < self.repeat - 1:
            return

        minutes = round((now - self._on_since) / 60)
        self._last_alert = now
        if self.coordinator.devices:
            await async_send_cooktop_critical(
                self.hass,
                self.coordinator,
                tag=self.tag,
                minutes_on=minutes,
                acknowledge_action=self.ack_action,
            )
        await async_speak(
            self.hass,
            self.tts_entity,
            self.speakers,
            f"Warning. The cooktop has been on for {minutes} minutes. Please check it.",
        )
