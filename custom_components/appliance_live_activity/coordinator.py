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

from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_ON
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .appliance import APPLIANCE_REGISTRY
from .const import (
    ACTION_LAUNDRY_MOVED,
    ACTION_START_DRYER,
    CONF_ACTIVE_STATES,
    CONF_APPLIANCE_TYPE,
    CONF_COMPLETE_STATES,
    CONF_COOKTOP_ALERT_MINUTES,
    CONF_COOKTOP_ENTITIES,
    CONF_COOKTOP_REPEAT_MINUTES,
    CONF_CYCLE_ENTITY,
    CONF_DELAY_ENTITY,
    CONF_DELAY_START,
    CONF_DEVICES,
    CONF_DISMISS_MINUTES,
    CONF_DONE_ENTITY,
    CONF_DOOR_ENTITY,
    CONF_DRYER_ENTITY,
    CONF_DRYER_START_ENTITY,
    CONF_ESCALATION_DEVICES,
    CONF_FINISHED_ALERT,
    CONF_ICON,
    CONF_ICON_COLOR,
    CONF_IDLE_STATES,
    CONF_LEAK_ENTITIES,
    CONF_LEAK_REPEAT_MINUTES,
    CONF_MOVE_MAX_REMINDERS,
    CONF_MOVE_REMINDER_MINUTES,
    CONF_MOVE_REPEAT_MINUTES,
    CONF_NAME,
    CONF_NOTIFICATION_TAG,
    CONF_PAUSE_STATES,
    CONF_PHASE_ENTITY,
    CONF_PREHEAT_ALERT,
    CONF_REMAINING_ENTITY,
    CONF_SOURCE_DEVICE,
    CONF_SPEAKERS,
    CONF_STATE_ENTITY,
    CONF_TARGET_TEMPERATURE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_TTS_ENTITY,
    DEFAULT_COOKTOP_ALERT_MINUTES,
    DEFAULT_COOKTOP_REPEAT_MINUTES,
    DEFAULT_DISMISS_MINUTES,
    DEFAULT_LEAK_REPEAT_MINUTES,
    DEFAULT_MOVE_MAX_REMINDERS,
    DEFAULT_MOVE_REMINDER_MINUTES,
    DEFAULT_MOVE_REPEAT_MINUTES,
    DOMAIN,
    DRIFT_MINUTES,
    EVENT_NOTIFICATION_ACTION,
    FINISHED_THRESHOLD_MINUTES,
    PREHEAT_TOLERANCE,
    STATUS_COMPLETE,
    STATUS_DELAYED,
    STATUS_IDLE,
    STATUS_PAUSED,
    STATUS_RUNNING,
    STORAGE_VERSION,
)
from .helpers import classify_state, color_to_hex, meaningful, to_minutes
from .notify import (
    async_clear,
    async_clear_tag,
    async_send_delayed,
    async_send_done,
    async_send_dryer_remote_off,
    async_send_finished_alert,
    async_send_move_reminder,
    async_send_preheated,
    async_send_progress,
)

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
        self.source_device: str | None = cfg.get(CONF_SOURCE_DEVICE) or None
        self.state_entity: str | None = cfg.get(CONF_STATE_ENTITY) or None
        self.cycle_entity: str | None = cfg.get(CONF_CYCLE_ENTITY) or None
        self.phase_entity: str | None = cfg.get(CONF_PHASE_ENTITY) or None
        self.remaining_entity: str | None = cfg.get(CONF_REMAINING_ENTITY) or None
        self.done_entity: str | None = cfg.get(CONF_DONE_ENTITY) or None
        self.door_entity: str | None = cfg.get(CONF_DOOR_ENTITY) or None
        self.temperature_entity: str | None = cfg.get(CONF_TEMPERATURE_ENTITY) or None
        self.target_entity: str | None = cfg.get(CONF_TARGET_TEMPERATURE_ENTITY) or None
        self.preheat_alert: bool = cfg.get(CONF_PREHEAT_ALERT, True) is not False

        self.active_states: list[str] = cfg.get(CONF_ACTIVE_STATES) or self.definition.active_states
        self.pause_states: list[str] = cfg.get(CONF_PAUSE_STATES) or self.definition.pause_states
        self.complete_states: list[str] = cfg.get(CONF_COMPLETE_STATES) or self.definition.complete_states
        self.idle_states: list[str] = cfg.get(CONF_IDLE_STATES) or self.definition.idle_states

        self.icon: str = cfg.get(CONF_ICON) or self.definition.icon
        self.icon_color: str = color_to_hex(cfg.get(CONF_ICON_COLOR), self.definition.color)
        self.notification_tag: str = cfg.get(CONF_NOTIFICATION_TAG) or f"{DOMAIN}_{entry.entry_id}"
        self.devices: list[str] = cfg.get(CONF_DEVICES) or []
        self.finished_alert: bool = cfg.get(CONF_FINISHED_ALERT, True)
        self.dismiss_minutes: float = float(cfg.get(CONF_DISMISS_MINUTES, DEFAULT_DISMISS_MINUTES))

        # Washer -> dryer reminder (washers only; 0 minutes = off)
        self.move_minutes: float = float(
            cfg.get(CONF_MOVE_REMINDER_MINUTES, DEFAULT_MOVE_REMINDER_MINUTES) or 0
        ) if self.appliance_type == "washer" else 0.0
        self.move_repeat: float = float(
            cfg.get(CONF_MOVE_REPEAT_MINUTES, DEFAULT_MOVE_REPEAT_MINUTES) or DEFAULT_MOVE_REPEAT_MINUTES
        )
        self.move_max: int = int(cfg.get(CONF_MOVE_MAX_REMINDERS, DEFAULT_MOVE_MAX_REMINDERS) or 1)
        self.dryer_entity: str | None = cfg.get(CONF_DRYER_ENTITY) or None
        self.dryer_start_entity: str | None = (
            cfg.get(CONF_DRYER_START_ENTITY) or None if self.appliance_type == "washer" else None
        )
        self.move_tag = f"{self.notification_tag}_move"

        # Delayed start ("Starts in 2 h")
        self.delay_entity: str | None = cfg.get(CONF_DELAY_ENTITY) or None
        self.delay_start: bool = cfg.get(CONF_DELAY_START, True) is not False

        # Extra monitors (cooktop, leak) that run alongside the Live Activity
        self.monitors: list[Any] = []

        # Cooktop left-on alerts (ovens / ranges)
        self.cooktop = None
        cooktop_entities = list(cfg.get(CONF_COOKTOP_ENTITIES) or [])
        if cooktop_entities:
            from .cooktop import CooktopMonitor  # noqa: PLC0415 - avoids import cycle

            self.cooktop = CooktopMonitor(
                hass,
                self,
                entities=cooktop_entities,
                alert_minutes=float(cfg.get(CONF_COOKTOP_ALERT_MINUTES, DEFAULT_COOKTOP_ALERT_MINUTES)),
                repeat_minutes=float(cfg.get(CONF_COOKTOP_REPEAT_MINUTES, DEFAULT_COOKTOP_REPEAT_MINUTES)),
                tts_entity=cfg.get(CONF_TTS_ENTITY) or None,
                speakers=list(cfg.get(CONF_SPEAKERS) or []),
            )
            self.monitors.append(self.cooktop)

        # Water leak alerts (any appliance)
        self.leak = None
        leak_entities = list(cfg.get(CONF_LEAK_ENTITIES) or [])
        if leak_entities:
            from .leak import LeakMonitor  # noqa: PLC0415 - avoids import cycle

            self.leak = LeakMonitor(
                hass,
                self,
                entities=leak_entities,
                repeat_minutes=float(cfg.get(CONF_LEAK_REPEAT_MINUTES) or DEFAULT_LEAK_REPEAT_MINUTES),
                tts_entity=cfg.get(CONF_TTS_ENTITY) or None,
                speakers=list(cfg.get(CONF_SPEAKERS) or []),
                extra_devices=list(cfg.get(CONF_ESCALATION_DEVICES) or []),
            )
            self.monitors.append(self.leak)

        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}"
        )
        # Persisted cycle state
        self._total_minutes: float = 0.0
        self._in_cycle: bool = False
        self._last_remaining: float = 0.0
        self._dismiss_at: float | None = None  # epoch seconds
        self._move_since: float | None = None  # washer finished at (epoch)
        self._move_count: int = 0

        # Oven preheat (per cycle, not persisted)
        self._preheat_seen = False
        self._preheat_done = False
        self._was_preheating = False
        self._preheat_start: float | None = None

        # Delayed start (not persisted)
        self._delay_target: float | None = None  # epoch the cycle should start
        self._delay_value: str | None = None  # last delay sensor reading
        self._delay_sent: tuple | None = None  # (cycle, target) on the phone

        # What the phone is currently showing (not persisted: after a
        # restart we always re-send once, which also resumes the activity)
        self._sent_signature: tuple | None = None
        self._sent_remaining: float = 0.0
        self._sent_at: float = 0.0

        self._unsubs: list[CALLBACK_TYPE] = []
        self._finish_time: datetime | None = None
        self._dismiss_unsub: CALLBACK_TYPE | None = None

        self.data = {
            "status": STATUS_IDLE,
            "phase": "",
            "cycle": "",
            "remaining": 0,
            "progress": 0,
        }

    def action_id(self, suffix: str) -> str:
        """Notification button id, unique to this appliance."""
        return f"{self.notification_tag}_{suffix}".upper()

    def washer_actions(self) -> list[dict[str, str]]:
        """Buttons on the washer's finished alert / move reminder."""
        actions: list[dict[str, str]] = []
        if self.dryer_start_entity:
            actions.append({"action": self.action_id(ACTION_START_DRYER), "title": "Start dryer"})
        if self.move_minutes > 0 or self.dryer_start_entity:
            actions.append({"action": self.action_id(ACTION_LAUNDRY_MOVED), "title": "Laundry moved"})
        return actions

    def tap_path(self) -> str:
        """Where tapping a notification / Live Activity goes in the app.

        The appliance's own device page (e.g. the GE washer, with its controls)
        when there is one, else this integration's device for the appliance,
        else the integration page.
        """
        dev_reg = dr.async_get(self.hass)
        if self.source_device and dev_reg.async_get(self.source_device):
            return f"/config/devices/device/{self.source_device}"
        own = dev_reg.async_get_device(identifiers={(DOMAIN, self.entry.entry_id)})
        if own is not None:
            return f"/config/devices/device/{own.id}"
        return f"/config/integrations/integration/{DOMAIN}"

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
        self._move_since = stored.get("move_since")
        self._move_count = int(stored.get("move_count", 0) or 0)

        tracked = [
            e
            for e in (
                self.state_entity,
                self.phase_entity,
                self.cycle_entity,
                self.remaining_entity,
                self.done_entity,
                self.door_entity,
                self.temperature_entity,
                self.target_entity,
                self.dryer_entity,
                self.delay_entity,
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
            self._schedule_dismiss(max(0.0, self._dismiss_at - dt_util.utcnow().timestamp()))

        await self.async_evaluate(send=True)
        await self._async_setup_monitors()

    async def _async_setup_monitors(self) -> None:
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_NOTIFICATION_ACTION, self._handle_action)
        )
        for monitor in self.monitors:
            await monitor.async_setup()

    async def async_unload(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._cancel_dismiss()
        for monitor in self.monitors:
            await monitor.async_unload()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    @callback
    def _handle_state_event(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        new_state = event.data.get("new_state")
        if (
            entity_id == self.door_entity
            and new_state is not None
            and new_state.state == STATE_ON
            and (self._dismiss_at is not None or self._move_since is not None)
        ):
            # Door opened after a finished cycle: dismiss "Done" and stop the
            # "move the laundry" reminders
            if self._dismiss_at is not None:
                self.hass.async_create_task(self._async_dismiss())
            if self._move_since is not None:
                self.hass.async_create_task(self._async_cancel_move("door opened"))
            return
        self.hass.async_create_task(self.async_evaluate(send=True))

    @callback
    def _handle_tick(self, _now=None) -> None:
        self.hass.async_create_task(self.async_evaluate(send=True))

    @callback
    def _handle_action(self, event: Event) -> None:
        """A notification button was tapped on a phone."""
        action = event.data.get("action")
        if not action:
            return
        handler = self._action_handlers().get(action)
        if handler is not None:
            _LOGGER.debug("%s: notification action %s", self.name, action)
            self.hass.async_create_task(handler())

    def _action_handlers(self) -> dict[str, Any]:
        if self.appliance_type != "washer":
            return {}
        return {
            self.action_id(ACTION_LAUNDRY_MOVED): self._async_laundry_moved,
            self.action_id(ACTION_START_DRYER): self._async_start_dryer,
        }

    async def _async_laundry_moved(self) -> None:
        """'Laundry moved': stop reminders and remove the finished alert / activity."""
        await self._async_cancel_move("laundry moved")
        if self.devices:
            await async_clear_tag(self.hass, self, f"{self.notification_tag}_done")
        if self._dismiss_at is not None:
            await self._async_dismiss()

    async def _async_start_dryer(self) -> None:
        """'Start dryer': press the dryer's start button (if it accepts remote starts)."""
        if not self.dryer_start_entity:
            return
        from .ge import async_remote_status_entity  # noqa: PLC0415

        remote = async_remote_status_entity(self.hass, self.dryer_start_entity)
        if remote and self._state(remote) != STATE_ON:
            _LOGGER.info("%s: dryer remote start is off; not starting it", self.name)
            if self.devices:
                await async_send_dryer_remote_off(self.hass, self)
        else:
            try:
                await self.hass.services.async_call(
                    "button", "press", target={"entity_id": self.dryer_start_entity}, blocking=True
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not start the dryer (%s)", self.dryer_start_entity)
        # Either way the laundry is in the dryer now
        await self._async_laundry_moved()

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
        raw = self._state(self.state_entity)
        status = classify_state(
            raw,
            active=self.active_states,
            paused=self.pause_states,
            complete=self.complete_states,
            idle=self.idle_states,
            unknown_is_running=self.definition.unknown_is_running,
            done_signal=bool(self.done_entity) and self._state(self.done_entity) == STATE_ON,
        )
        # An unrecognised state (e.g. GE's "Control Locked") keeps a running
        # cycle running, but must not *start* one -- otherwise a finished
        # appliance flips back to "running" and its Live Activity never clears.
        # Only treat it as a new cycle when a timer is actually counting down.
        if (
            status == STATUS_RUNNING
            and not self._in_cycle
            and raw.strip().lower() not in {s.lower() for s in self.active_states}
            and self._remaining_minutes() <= FINISHED_THRESHOLD_MINUTES
        ):
            _LOGGER.debug("%s: ignoring unrecognised state %r while idle", self.name, raw)
            return STATUS_IDLE
        return status

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

        delayed = False
        if status in ACTIVE:
            self._delay_target = self._delay_value = self._delay_sent = None
            await self._async_on_active(status, phase, cycle, remaining, send, force, raw_state)
        else:
            await self._async_on_inactive(status, cycle, send)
            delayed = self.delay_start and "delay" in raw_state.lower()
            if delayed:
                await self._async_on_delayed(cycle, send, force)
            else:
                await self._async_end_delay(send)
        await self._async_check_move(send)
        if delayed:
            status = STATUS_DELAYED

        progress = self._progress(remaining) if status in ACTIVE else (
            100 if status == STATUS_COMPLETE and self.definition.supports_progress else 0
        )
        active = status in ACTIVE
        self.async_set_updated_data(
            {
                "status": status,
                "phase": phase,
                "cycle": cycle,
                "remaining": round(remaining),
                "progress": progress or 0,
                # Dashboard sensors: only meaningful while a cycle is in progress
                "time_remaining": round(remaining) if active else 0,
                "finishes_at": self._finishes_at(remaining) if status == STATUS_RUNNING else None,
                "starts_at": (
                    dt_util.utc_from_timestamp(self._delay_target)
                    if delayed and self._delay_target
                    else None
                ),
            }
        )

    # ------------------------------------------------------------------
    # Delayed start
    # ------------------------------------------------------------------
    def _delay_minutes(self) -> tuple[str | None, float]:
        if not self.delay_entity:
            return None, 0.0
        state = self.hass.states.get(self.delay_entity)
        if state is None:
            return None, 0.0
        return state.state, to_minutes(state.state, state.attributes.get(ATTR_UNIT_OF_MEASUREMENT))

    def _clock(self, timestamp: float) -> str:
        local = dt_util.as_local(dt_util.utc_from_timestamp(timestamp))
        if self.hass.config.units.temperature_unit == "°F":
            return local.strftime("%I:%M %p").lstrip("0")
        return local.strftime("%H:%M")

    async def _async_on_delayed(self, cycle: str, send: bool, force: bool) -> None:
        """Waiting for a delayed start: Live Activity counting down to the start."""
        if self._dismiss_at is not None:
            # A new cycle was scheduled: the finished activity is replaced
            self._cancel_dismiss()
            self._dismiss_at = None
            await self._async_save()
        await self._async_cancel_move("new cycle scheduled")

        now = dt_util.utcnow().timestamp()
        value, minutes = self._delay_minutes()
        # Recompute the start time only when the sensor reports something new:
        # GE laundry / ovens count down, GE dishwashers only report the chosen
        # delay, which must not push the start time forward every minute.
        if value != self._delay_value or self._delay_target is None:
            self._delay_value = value
            target = now + minutes * 60 if minutes > 0 else None
            if (
                target is None
                or self._delay_target is None
                or abs(target - self._delay_target) > DRIFT_MINUTES * 60
            ):
                self._delay_target = target
        if self._delay_target is not None and self._delay_target <= now:
            # Should have started by now; keep showing "Scheduled" without a countdown
            starts_in = 0.0
        else:
            starts_in = (self._delay_target - now) / 60 if self._delay_target else 0.0

        if not send or not self.devices:
            return
        signature = (cycle, self._delay_target if starts_in > 0 else None)
        if not force and signature == self._delay_sent:
            return
        await async_send_delayed(
            self.hass,
            self,
            cycle=cycle,
            starts_in=starts_in,
            starts_at=self._clock(self._delay_target) if starts_in > 0 else "",
        )
        self._delay_sent = signature

    async def _async_end_delay(self, send: bool) -> None:
        """Delay cancelled (appliance turned off without starting)."""
        sent = self._delay_sent is not None
        self._delay_target = self._delay_value = self._delay_sent = None
        if sent and send and self.devices and not self._in_cycle and self._dismiss_at is None:
            await async_clear(self.hass, self)

    def _finishes_at(self, remaining: float) -> datetime | None:
        """Estimated end time, kept steady unless it moves by a minute or more."""
        if remaining <= 0:
            self._finish_time = None
            return None
        estimate = (dt_util.utcnow() + timedelta(minutes=remaining)).replace(second=0, microsecond=0)
        if self._finish_time is None or abs((estimate - self._finish_time).total_seconds()) >= 120:
            self._finish_time = estimate
        return self._finish_time

    def _progress(self, remaining: float) -> int | None:
        if not self.definition.supports_progress or self._total_minutes <= 0:
            return None
        pct = round((1 - remaining / self._total_minutes) * 100)
        return max(0, min(100, pct))

    async def _async_on_active(
        self,
        status: str,
        phase: str,
        cycle: str,
        remaining: float,
        send: bool,
        force: bool,
        raw_state: str = "",
    ) -> None:
        changed = False  # cycle bookkeeping changed -> save now
        if not self._in_cycle:
            # New cycle: forget any leftover "Done" activity first
            self._cancel_dismiss()
            self._dismiss_at = None
            await self._async_cancel_move("new cycle")
            self._preheat_seen = self._preheat_done = self._was_preheating = False
            self._preheat_start = None
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

        temperature = self._temperature_text()
        progress = self._progress(remaining)
        extra: Any = ""
        if self.appliance_type == "oven":
            preheat_phase, oven_temp, preheat_progress = await self._async_oven(raw_state, send)
            if oven_temp is not None:
                temperature = oven_temp
            if preheat_phase:
                # Preheating: show the temperature climbing as the progress bar.
                # Only re-send per 10 % step so iOS doesn't throttle the activity.
                phase, progress = preheat_phase, preheat_progress
                extra = ("preheat", (preheat_progress or 0) // 10)
            else:
                extra = temperature

        if not send or not self.devices:
            return

        signature = (status, phase, cycle, extra)
        now = dt_util.utcnow().timestamp()
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
            progress=progress,
        )
        self._sent_signature = signature
        self._sent_remaining = remaining
        self._sent_at = now

    async def _async_on_inactive(self, status: str, cycle: str, send: bool) -> None:
        if not self._in_cycle:
            return

        if self._preheat_done and send and self.devices:
            # Oven off: the "preheated" alert is no longer relevant
            await async_clear_tag(self.hass, self, f"{self.notification_tag}_preheat")
        self._preheat_seen = self._preheat_done = self._was_preheating = False
        self._preheat_start = None

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
                    await async_send_finished_alert(
                        self.hass,
                        self,
                        actions=self.washer_actions() if self.appliance_type == "washer" else None,
                    )
                self._dismiss_at = dt_util.utcnow().timestamp() + self.dismiss_minutes * 60
                self._schedule_dismiss(self.dismiss_minutes * 60)
            else:
                # Cancelled, or a door that closed: just end the activity
                await async_clear(self.hass, self)
        if finished and self.move_minutes > 0:
            # Washer done: remind to move the laundry unless the door opens
            self._move_since = dt_util.utcnow().timestamp()
            self._move_count = 0
        await self._async_save()

    # ------------------------------------------------------------------
    # Oven preheat
    # ------------------------------------------------------------------
    def _float_state(self, entity_id: str | None, attribute: str | None = None) -> float:
        if not entity_id:
            return 0.0
        state = self.hass.states.get(entity_id)
        if state is None:
            return 0.0
        value = state.attributes.get(attribute) if attribute else None
        if value is None:
            value = state.state
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _temp_unit(self) -> str:
        for entity_id in (self.temperature_entity, self.target_entity):
            state = self.hass.states.get(entity_id) if entity_id else None
            if state and state.attributes.get(ATTR_UNIT_OF_MEASUREMENT):
                return state.attributes[ATTR_UNIT_OF_MEASUREMENT]
        return "°"

    async def _async_oven(
        self, raw_state: str, send: bool
    ) -> tuple[str | None, str | None, int | None]:
        """Preheat tracking. Returns (phase, temperature text, progress) overrides."""
        target = self._float_state(self.target_entity, "temperature")
        temp = self._float_state(self.temperature_entity)
        unit = self._temp_unit()
        preheating = "preheat" in raw_state.lower()
        below = target > 0 and 0 < temp < target - PREHEAT_TOLERANCE

        if not self._preheat_done and (preheating or below):
            self._preheat_seen = True
        if self._preheat_seen and self._preheat_start is None and temp > 0:
            self._preheat_start = temp

        reached = (
            self._preheat_seen
            and not self._preheat_done
            and (
                (self._was_preheating and not preheating)
                or (target > 0 and temp >= target - PREHEAT_TOLERANCE)
            )
        )
        self._was_preheating = preheating
        if reached:
            self._preheat_done = True
            _LOGGER.debug("%s: preheated (%s / %s)", self.name, temp, target)
            if send and self.devices and self.preheat_alert:
                shown = target if target > 0 else temp
                await async_send_preheated(
                    self.hass, self, temperature=f"{round(shown)}{unit}" if shown > 0 else ""
                )

        if self._preheat_seen and not self._preheat_done:
            if target > 0 and temp > 0:
                text = f"{round(temp)}{unit} → {round(target)}{unit}"
            else:
                text = f"{round(temp)}{unit}" if temp > 0 else ""
            progress = None
            start = self._preheat_start
            if target > 0 and start is not None and target > start:
                progress = max(0, min(100, round((temp - start) / (target - start) * 100)))
            return "Preheating", text, progress
        # Cooking: show the set temperature (steady) rather than the cavity
        # temperature, which wobbles and would cause needless updates
        if target > 0:
            return None, f"{round(target)}{unit}", None
        return None, None, None

    # ------------------------------------------------------------------
    # Washer -> dryer reminder
    # ------------------------------------------------------------------
    def _dryer_running(self) -> bool:
        if not self.dryer_entity:
            return False
        dryer = APPLIANCE_REGISTRY["dryer"]
        status = classify_state(
            self._state(self.dryer_entity),
            active=dryer.active_states,
            paused=dryer.pause_states,
            complete=dryer.complete_states,
            idle=dryer.idle_states,
            unknown_is_running=False,
        )
        return status in ACTIVE

    async def _async_check_move(self, send: bool) -> None:
        if self._move_since is None or self.move_minutes <= 0 or self._in_cycle:
            return
        if self.door_entity and self._state(self.door_entity) == STATE_ON:
            await self._async_cancel_move("door open")
            return
        if self._dryer_running():
            await self._async_cancel_move("dryer started")
            return
        if self._move_count >= self.move_max:
            return
        now = dt_util.utcnow().timestamp()
        due = self._move_since + (self.move_minutes + self._move_count * self.move_repeat) * 60
        if now < due:
            return
        self._move_count += 1
        await self._async_save()
        if send and self.devices:
            await async_send_move_reminder(
                self.hass,
                self,
                tag=self.move_tag,
                minutes_ago=round((now - self._move_since) / 60),
                actions=self.washer_actions(),
            )

    async def _async_cancel_move(self, reason: str) -> None:
        if self._move_since is None:
            return
        _LOGGER.debug("%s: laundry reminder stopped (%s)", self.name, reason)
        sent = self._move_count > 0
        self._move_since = None
        self._move_count = 0
        await self._async_save()
        if sent and self.devices:
            await async_clear_tag(self.hass, self, self.move_tag)

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
            _LOGGER.debug("%s: dismiss skipped (in cycle: %s)", self.name, self._in_cycle)
            return
        _LOGGER.debug("%s: dismissing finished Live Activity", self.name)
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
            "move_since": self._move_since,
            "move_count": self._move_count,
        }

    async def _async_save(self) -> None:
        await self._store.async_save(self._data_to_save())
