"""Door monitoring for refrigerators / freezers.

Flow for one appliance (any of its doors):

1. A door has been open for ``open_delay`` (default 30 s, so quick grabs
   don't start an activity) -> Live Activity "Freezer Door is open",
   counting up on the phone.
2. Still open after ``critical_after`` minutes (default 5) -> the activity
   turns red and a **critical** notification is sent, repeated every
   ``critical_repeat`` minutes until the door closes.
3. Closed -> the critical notification is removed, the activity shows
   "Closed" for a minute, then it is ended.
"""
from __future__ import annotations

import logging

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_FRIENDLY_NAME, STATE_ON, STATE_OPEN
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)

from .const import (
    CLOSED_DISPLAY_SECONDS,
    CONF_CRITICAL_AFTER_MINUTES,
    CONF_CRITICAL_REPEAT_MINUTES,
    CONF_DOOR_ENTITIES,
    CONF_DOOR_ENTITY,
    CONF_OPEN_DELAY_SECONDS,
    CONF_STATE_ENTITY,
    DEFAULT_CRITICAL_AFTER_MINUTES,
    DEFAULT_CRITICAL_REPEAT_MINUTES,
    DEFAULT_OPEN_DELAY_SECONDS,
    STATUS_IDLE,
    STATUS_RUNNING,
)
from .coordinator import ApplianceCoordinator
from .notify import (
    async_clear_tag,
    async_send_door_closed,
    async_send_door_critical,
    async_send_door_open,
)

_LOGGER = logging.getLogger(__name__)

OPEN_STATES = {STATE_ON, STATE_OPEN, "door open"}
TICK = timedelta(seconds=15)


class DoorCoordinator(ApplianceCoordinator):
    """Live Activity + critical alerts while any of an appliance's doors is open."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry)
        cfg = {**entry.data, **entry.options}
        doors: list[str] = list(cfg.get(CONF_DOOR_ENTITIES) or [])
        for single in (cfg.get(CONF_STATE_ENTITY), cfg.get(CONF_DOOR_ENTITY)):
            if single and single not in doors:
                doors.insert(0, single)
        self.doors = doors
        self.open_delay = float(cfg.get(CONF_OPEN_DELAY_SECONDS, DEFAULT_OPEN_DELAY_SECONDS))
        self.critical_after = float(cfg.get(CONF_CRITICAL_AFTER_MINUTES, DEFAULT_CRITICAL_AFTER_MINUTES)) * 60
        self.critical_repeat = max(
            30.0, float(cfg.get(CONF_CRITICAL_REPEAT_MINUTES, DEFAULT_CRITICAL_REPEAT_MINUTES)) * 60
        )
        self.critical_tag = f"{self.notification_tag}_critical"

        self._open_since: float | None = None
        self._activity_started = False
        self._sent_signature: tuple | None = None
        self._last_critical: float | None = None
        self._closed_clear_unsub: CALLBACK_TYPE | None = None

    async def async_setup(self) -> None:
        if self.doors:
            self._unsubs.append(
                async_track_state_change_event(self.hass, self.doors, self._handle_door_event)
            )
        self._unsubs.append(async_track_time_interval(self.hass, self._handle_tick, TICK))
        await self.async_evaluate(send=True)

    async def async_unload(self) -> None:
        await super().async_unload()
        self._cancel_closed_clear()

    @callback
    def _handle_door_event(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_evaluate(send=True))

    # ------------------------------------------------------------------
    def _is_open(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state.lower() in OPEN_STATES

    def _label(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        name = (state.attributes.get(ATTR_FRIENDLY_NAME) if state else None) or entity_id
        # "Kitchen Refrigerator Freezer Door" -> "Freezer Door"
        if name.lower().startswith(self.name.lower() + " "):
            name = name[len(self.name) + 1 :]
        return name

    async def async_evaluate(self, send: bool = True, force: bool = False) -> None:
        now = dt_util.utcnow().timestamp()
        open_doors = [d for d in self.doors if self._is_open(d)]

        if open_doors:
            self._cancel_closed_clear()
            if self._open_since is None:
                changed = [
                    self.hass.states.get(d).last_changed.timestamp() for d in open_doors
                ]
                self._open_since = min(changed) if changed else now
            elapsed = now - self._open_since
            labels = [self._label(d) for d in open_doors]

            if send and self.devices and (self._activity_started or elapsed >= self.open_delay):
                critical = elapsed >= self.critical_after
                signature = (tuple(labels), critical)
                if force or signature != self._sent_signature:
                    await async_send_door_open(
                        self.hass, self, labels=labels, opened_at=self._open_since, critical=critical
                    )
                    self._sent_signature = signature
                    self._activity_started = True
                if critical and (
                    self._last_critical is None or now - self._last_critical >= self.critical_repeat - 1
                ):
                    await async_send_door_critical(
                        self.hass, self, labels=labels, minutes_open=round(elapsed / 60)
                    )
                    self._last_critical = now

            self.async_set_updated_data(
                {
                    "status": STATUS_RUNNING,
                    "phase": ", ".join(labels),
                    "cycle": "",
                    "remaining": 0,
                    "progress": 0,
                    "open_minutes": round(elapsed / 60, 1),
                }
            )
            return

        # All doors closed
        if self._open_since is not None:
            minutes_open = round((now - self._open_since) / 60)
            if send and self.devices and self._activity_started:
                if self._last_critical is not None:
                    await async_clear_tag(self.hass, self, self.critical_tag)
                await async_send_door_closed(self.hass, self, minutes_open=minutes_open)
                self._schedule_closed_clear()
        self._open_since = None
        self._activity_started = False
        self._sent_signature = None
        self._last_critical = None
        self.async_set_updated_data(
            {"status": STATUS_IDLE, "phase": "", "cycle": "", "remaining": 0, "progress": 0}
        )

    # ------------------------------------------------------------------
    def _schedule_closed_clear(self) -> None:
        self._cancel_closed_clear()

        @callback
        def _fire(_now) -> None:
            self._closed_clear_unsub = None
            self.hass.async_create_task(async_clear_tag(self.hass, self, self.notification_tag))

        self._closed_clear_unsub = async_call_later(self.hass, CLOSED_DISPLAY_SECONDS, _fire)

    def _cancel_closed_clear(self) -> None:
        if self._closed_clear_unsub is not None:
            self._closed_clear_unsub()
            self._closed_clear_unsub = None
