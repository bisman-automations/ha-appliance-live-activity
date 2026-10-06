"""Coordinator for a single configured appliance.

Drives one Live Activity per appliance:

* **Start / update** only when something visible changes (status, phase,
  cycle) or the appliance's time estimate drifts more than DRIFT_MINUTES
  from the countdown the phone is already running. The phone counts down
  on its own via ``chronometer``, so there is no per-minute push -- iOS
  throttles activities that update too often.
* **Finish** once: show "Done", optionally send a regular alert, then end
  the activity when the appliance door opens or after a delay.
* **Cancel**: if the appliance stops early, end the activity right away.

Cycle length, whether a cycle is in progress and a pending dismissal are
persisted, so a Home Assistant restart resumes cleanly without helpers.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .appliance import APPLIANCE_REGISTRY
from .const import (
    CONF_ACTIVE_STATES,
    CONF_APPLIANCE_TYPE,
    CONF_COMPLETE_STATES,
    CONF_CYCLE_ENTITY,
    CONF_DEVICES,
    CONF_DISMISS_MINUTES,
    CONF_DONE_ENTITY,
    CONF_DOOR_ENTITY,
    CONF_FINISHED_ALERT,
    CONF_ICON,
    CONF_ICON_COLOR,
    CONF_IDLE_STATES,
    CONF_NAME,
    CONF_NOTIFICATION_TAG,
    CONF_PAUSE_STATES,
    CONF_PHASE_ENTITY,
    CONF_REMAINING_ENTITY,
    CONF_STATE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    DEFAULT_DISMISS_MINUTES,
    DOMAIN,
    DRIFT_MINUTES,
    FINISHED_THRESHOLD_MINUTES,
    STATUS_COMPLETE,
    STATUS_IDLE,
    STATUS_PAUSED,
    STATUS_RUNNING,
    STORAGE_VERSION,
)
from .helpers import classify_state, meaningful, to_minutes
from .notify import async_clear, async_send_done, async_send_finished_alert, async_send_progress

_LOGGER = logging.getLogger(__name__)

ACTIVE = (STATUS_RUNNING, STATUS_PAUSED)


class ApplianceCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Tracks one appliance's state and drives its Live Activity."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{entry.entry_id}", update_interval=None)
        self.entry = entry

        cfg = {**entry.data, **entry.options}
        self.appliance_type: str = cfg[CONF_APPLIANCE_TYPE]
        self.definition = APPLIANCE_REGISTRY[self.appliance_type]

        self.name: str = cfg.get(CONF_NAME) or self.definition.display_name
        self.state_entity: str | None = cfg.get(CONF_STATE_ENTITY) or None
        self.cycle_entity: str | None = cfg.get(CONF_CYCLE_ENTITY) or None
        self.phase_entity: str | None = cfg.get(CONF_PHASE_ENTITY) or None
        self.remaining_entity: str | None = cfg.get(CONF_REMAINING_ENTITY) or None
        self.done_entity: str | None = cfg.get(CONF_DONE_ENTITY) or None
        self.door_entity: str | None = cfg.get(CONF_DOOR_ENTITY) or None
        self.temperature_entity: str | None = cfg.get(CONF_TEMPERATURE_ENTITY) or None

        self.active_states: list[str] = cfg.get(CONF_ACTIVE_STATES) or self.definition.active_states
        self.pause_states: list[str] = cfg.get(CONF_PAUSE_STATES) or self.definition.pause_states
        self.complete_states: list[str] = cfg.get(CONF_COMPLETE_STATES) or self.definition.complete_states
        self.idle_states: list[str] = cfg.get(CONF_IDLE_STATES) or self.definition.idle_states

        self.icon: str = cfg.get(CONF_ICON) or self.definition.icon
        self.icon_color: str = cfg.get(CONF_ICON_COLOR) or self.definition.color
        self.notification_tag: str = cfg.get(CONF_NOTIFICATION_TAG) or f"{DOMAIN}_{entry.entry_id}"
        self.devices: list[str] = cfg.get(CONF_DEVICES) or []
        self.finished_alert: bool = cfg.get(CONF_FINISHED_ALERT, True)
        self.dismiss_minutes: float = float(cfg.get(CONF_DISMISS_MINUTES, DEFAULT_DISMISS_MINUTES))

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}"
        )
        # Persisted cycle state
        self._total_minutes: float = 0.0
        self._in_cycle: bool = False
        self._last_remaining: float = 0.0
        self._dismiss_at: float | None = None  # epoch seconds

        # What the phone is currently showing (not persisted: after a
        # restart we always re-send once, which also resumes the activity)
        self._sent_signature: tuple | None = None
        self._sent_remaining: float = 0.0
        self._sent_at: float = 0.0

        self._unsubs: list[CALLBACK_TYPE] = []
        self._dismiss_unsub: CALLBACK_TYPE | None = None

        self.data = {
            "status": STATUS_IDLE,
            "phase": "",
            "cycle": "",
            "remaining": 0,
            "progress": 0,
        }

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------
    async def async_setup(self) -> None:
        """Load persisted state and start listening."""
        stored = await self._store.async_load() or {}
        self._total_minutes = float(stored.get("total_minutes", 0) or 0)
        self._in_cycle = bool(stored.get("in_cycle", False))
        self._last_remaining = float(stored.get("last_remaining", 0) or 0)
        self._dismiss_at = stored.get("dismiss_at")

        tracked = [
            e
            for e in (
                self.state_entity,
                self.phase_entity,
                self.cycle_entity,
                self.remaining_entity,
                self.done_entity,
                self.door_entity,
            )
            if e
        ]
        if tracked:
            self._unsubs.append(
                async_track_state_change_event(self.hass, tracked, self._handle_state_event)
            )
        # Only used to notice drift between the appliance's estimate and the
        # phone's countdown -- it never sends on its own.
        self._unsubs.append(
            async_track_time_interval(self.hass, self._handle_tick, timedelta(minutes=1))
        )

        if self._dismiss_at is not None:
            self._schedule_dismiss(max(0.0, self._dismiss_at - time.time()))

        await self.async_evaluate(send=True)

    async def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._cancel_dismiss()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    @callback
    def _handle_state_event(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        if (
            entity_id == self.door_entity
            and self._dismiss_at is not None
            and new_state is not None
            and new_state.state == STATE_ON
        ):
            self.hass.async_create_task(self._async_dismiss())
            return
        self.hass.async_create_task(self.async_evaluate(send=True))

    @callback
    def _handle_tick(self, _now=None) -> None:
        self.hass.async_create_task(self.async_evaluate(send=True))

    # ------------------------------------------------------------------
    # State reading
    # ------------------------------------------------------------------
    def _state(self, entity_id: str | None) -> str:
        if not entity_id:
            return ""
        state = self.hass.states.get(entity_id)
        return state.state if state else ""

    def _remaining_minutes(self) -> float:
        if not self.remaining_entity:
            return 0.0
        state = self.hass.states.get(self.remaining_entity)
        if state is None:
            return 0.0
        return to_minutes(state.state, state.attributes.get(ATTR_UNIT_OF_MEASUREMENT))

    def _temperature_text(self) -> str:
        if not self.temperature_entity:
            return ""
        state = self.hass.states.get(self.temperature_entity)
        if state is None:
            return ""
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return ""
        if value <= 0:
            return ""
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or ""
        return f"{round(value)}{unit}"

    def _status(self) -> str:
        return classify_state(
            self._state(self.state_entity),
            active=self.active_states,
            paused=self.pause_states,
            complete=self.complete_states,
            idle=self.idle_states,
            unknown_is_running=self.definition.unknown_is_running,
            done_signal=bool(self.done_entity) and self._state(self.done_entity) == STATE_ON,
        )

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------
    async def async_evaluate(self, send: bool = True, force: bool = False) -> None:
        """Re-read the appliance and update sensors / the Live Activity."""
        status = self._status()
        raw_state = self._state(self.state_entity)
        phase = meaningful(self._state(self.phase_entity)) or meaningful(raw_state)
        cycle = meaningful(self._state(self.cycle_entity))
        remaining = self._remaining_minutes()

        if status in ACTIVE:
            await self._async_on_active(status, phase, cycle, remaining, send, force)
        else:
            await self._async_on_inactive(status, cycle, send)

        progress = self._progress(remaining) if status in ACTIVE else (
            100 if status == STATUS_COMPLETE and self.definition.supports_progress else 0
        )
        self.async_set_updated_data(
            {
                "status": status,
                "phase": phase,
                "cycle": cycle,
                "remaining": round(remaining),
                "progress": progress or 0,
            }
        )

    def _progress(self, remaining: float) -> int | None:
        if not self.definition.supports_progress or self._total_minutes <= 0:
            return None
        pct = round((1 - remaining / self._total_minutes) * 100)
        return max(0, min(100, pct))

    async def _async_on_active(
        self, status: str, phase: str, cycle: str, remaining: float, send: bool, force: bool
    ) -> None:
        changed = False  # cycle bookkeeping changed -> save now
        if not self._in_cycle:
            # New cycle: forget any leftover "Done" activity first
            self._cancel_dismiss()
            self._dismiss_at = None
            self._in_cycle = True
            self._total_minutes = remaining
            self._sent_signature = None
            changed = True
        elif self._total_minutes <= 0 and remaining > 0:
            self._total_minutes = remaining
            changed = True
        elif remaining > self._total_minutes:
            # Some appliances raise the estimate early in the cycle
            self._total_minutes = remaining
            changed = True

        if status == STATUS_RUNNING and remaining > 0:
            if not changed and abs(remaining - self._last_remaining) >= 1:
                # Countdown progress: batch writes instead of saving every minute
                self._store.async_delay_save(self._data_to_save, 60)
            self._last_remaining = remaining
        if changed:
            await self._async_save()

        if not send or not self.devices:
            return

        temperature = self._temperature_text()
        signature = (status, phase, cycle, temperature if self.appliance_type == "oven" else "")
        now = time.time()
        expected = self._sent_remaining - (now - self._sent_at) / 60
        drifted = (
            status == STATUS_RUNNING
            and remaining > 0
            and abs(remaining - expected) > DRIFT_MINUTES
        )
        if not (force or signature != self._sent_signature or drifted):
            return

        await async_send_progress(
            self.hass,
            self,
            paused=status == STATUS_PAUSED,
            phase=phase,
            cycle=cycle,
            temperature=temperature,
            remaining=remaining,
            progress=self._progress(remaining),
        )
        self._sent_signature = signature
        self._sent_remaining = remaining
        self._sent_at = now

    async def _async_on_inactive(self, status: str, cycle: str, send: bool) -> None:
        if not self._in_cycle:
            return

        # Finished = an explicit completion signal, or the countdown had
        # (nearly) run out when the appliance stopped. Stopping with a lot of
        # time left -- or with no timer at all, like an oven without a cook
        # timer or a fridge door closing -- just ends the activity.
        had_timer = self._total_minutes > 0
        finished = status == STATUS_COMPLETE or (
            had_timer and self._last_remaining <= FINISHED_THRESHOLD_MINUTES
        )

        self._in_cycle = False
        self._total_minutes = 0.0
        self._last_remaining = 0.0
        self._sent_signature = None

        if send and self.devices:
            if finished and self.definition.supports_progress:
                await async_send_done(self.hass, self, cycle)
                if self.finished_alert:
                    await async_send_finished_alert(self.hass, self)
                self._dismiss_at = time.time() + self.dismiss_minutes * 60
                self._schedule_dismiss(self.dismiss_minutes * 60)
            else:
                # Cancelled, or a door that closed: just end the activity
                await async_clear(self.hass, self)
        await self._async_save()

    # ------------------------------------------------------------------
    # Dismissal
    # ------------------------------------------------------------------
    def _schedule_dismiss(self, delay_seconds: float) -> None:
        self._cancel_dismiss()

        @callback
        def _fire(_now) -> None:
            self._dismiss_unsub = None
            self.hass.async_create_task(self._async_dismiss())

        self._dismiss_unsub = async_call_later(self.hass, delay_seconds, _fire)

    def _cancel_dismiss(self) -> None:
        if self._dismiss_unsub is not None:
            self._dismiss_unsub()
            self._dismiss_unsub = None

    async def _async_dismiss(self) -> None:
        self._cancel_dismiss()
        if self._dismiss_at is None or self._in_cycle:
            return
        self._dismiss_at = None
        await self._async_save()
        if self.devices:
            await async_clear(self.hass, self)

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        return {
            "total_minutes": self._total_minutes,
            "in_cycle": self._in_cycle,
            "last_remaining": self._last_remaining,
            "dismiss_at": self._dismiss_at,
        }

    async def _async_save(self) -> None:
        await self._store.async_save(self._data_to_save())
