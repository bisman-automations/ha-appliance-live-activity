"""Oven kitchen timer and meat probe Live Activities.

Kitchen timer
    A timer set on the oven gets its own Live Activity counting down on the
    phone, then a time-sensitive "Timer done" alert. Cancelling the timer
    just ends the activity.

Meat probe
    While the probe is plugged in, a Live Activity shows its temperature
    climbing. With a target set (the appliance's "Probe Target" number
    entity) it shows "128°F → 145°F" with a progress bar, and sends a
    time-sensitive alert when the probe reaches the target. Unplugging the
    probe ends it. GE ovens don't report the target temperature, hence the
    number entity.

Both only push when something visible changes so iOS doesn't throttle them.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import UNAVAILABLE_STATES
from .helpers import to_minutes
from .notify import async_clear_tag, async_send_alert, async_send_live

if TYPE_CHECKING:
    from .coordinator import ApplianceCoordinator

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=30)
# Timer: re-send only when the oven's countdown and the phone's disagree by this much
TIMER_DRIFT_MINUTES = 1.5
# Timer stopping with this little left (by either clock) counts as "done"
TIMER_DONE_MINUTES = 1.5
# Probe without a target: re-send every this many degrees
PROBE_STEP_DEGREES = 5
# Probe with a target: re-send every this many percent
PROBE_STEP_PERCENT = 10


class _Monitor:
    """Shared plumbing: listen to one entity plus a tick."""

    def __init__(self, hass: HomeAssistant, coordinator: ApplianceCoordinator, entity: str) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.entity = entity
        self._unsubs: list[CALLBACK_TYPE] = []

    async def async_setup(self) -> None:
        self._unsubs.append(
            async_track_state_change_event(self.hass, [self.entity], self._handle_change)
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

    async def async_evaluate(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    @property
    def _send(self) -> bool:
        return bool(self.coordinator.devices)


class KitchenTimerMonitor(_Monitor):
    """Oven kitchen timer -> its own countdown Live Activity."""

    def __init__(self, hass: HomeAssistant, coordinator: ApplianceCoordinator, entity: str) -> None:
        super().__init__(hass, coordinator, entity)
        self.tag = f"{coordinator.notification_tag}_timer"
        self.done_tag = f"{coordinator.notification_tag}_timer_done"
        self._running = False
        self._sent_remaining = 0.0
        self._sent_at = 0.0
        self._last_remaining = 0.0

    @property
    def remaining(self) -> float:
        return self._last_remaining if self._running else 0.0

    async def async_evaluate(self) -> None:
        state = self.hass.states.get(self.entity)
        if state is None or state.state.strip().lower() in UNAVAILABLE_STATES:
            return
        remaining = to_minutes(state.state, state.attributes.get(ATTR_UNIT_OF_MEASUREMENT))
        now = dt_util.utcnow().timestamp()
        expected = self._sent_remaining - (now - self._sent_at) / 60

        if remaining > 0:
            first = not self._running
            if first:
                self._running = True
                if self._send:
                    await async_clear_tag(self.hass, self.coordinator, self.done_tag)
            self._last_remaining = remaining
            if self._send and (first or abs(remaining - expected) > TIMER_DRIFT_MINUTES):
                await async_send_live(
                    self.hass,
                    self.coordinator,
                    tag=self.tag,
                    title=f"{self.coordinator.name} timer",
                    message=f"Timer · {_duration(remaining)}",
                    critical_text="Timer",
                    icon="mdi:timer-outline",
                    countdown_minutes=remaining,
                )
                self._sent_remaining, self._sent_at = remaining, now
            self.coordinator.async_update_listeners()
            return

        if not self._running:
            return
        # Stopped: done if it ran out (by the oven's last report or by the clock)
        done = min(self._last_remaining, max(expected, 0.0)) <= TIMER_DONE_MINUTES
        self._running = False
        self._last_remaining = 0.0
        self.coordinator.async_update_listeners()
        if not self._send:
            return
        await async_clear_tag(self.hass, self.coordinator, self.tag)
        if done:
            await async_send_alert(
                self.hass,
                self.coordinator,
                tag=self.done_tag,
                title=f"⏰ {self.coordinator.name} timer done",
                message="Your kitchen timer is up.",
            )


class ProbeMonitor(_Monitor):
    """Meat probe temperature -> Live Activity + "reached target" alert."""

    def __init__(self, hass: HomeAssistant, coordinator: ApplianceCoordinator, entity: str) -> None:
        super().__init__(hass, coordinator, entity)
        self.tag = f"{coordinator.notification_tag}_probe"
        self.done_tag = f"{coordinator.notification_tag}_probe_done"
        self.target: float = 0.0
        self._active = False
        self._start: float | None = None
        self._alerted = False
        self._sent_signature: tuple | None = None
        self.temperature: float = 0.0

    def _unit(self) -> str:
        state = self.hass.states.get(self.entity)
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) if state else None
        return unit or self.hass.config.units.temperature_unit

    async def async_set_target(self, value: float) -> None:
        """Called by the Probe Target number entity."""
        self.target = max(0.0, float(value))
        self._alerted = self._alerted and self.temperature >= self.target > 0
        self._sent_signature = None
        await self.async_evaluate()

    async def async_evaluate(self) -> None:
        state = self.hass.states.get(self.entity)
        try:
            temp = float(state.state) if state is not None else 0.0
        except (TypeError, ValueError):
            temp = 0.0
        if temp != self.temperature:
            self.temperature = temp
            self.coordinator.async_update_listeners()

        if temp <= 0:
            # Probe unplugged (GE reports 0 / unknown)
            if self._active:
                self._active = False
                self._start = None
                self._alerted = False
                self._sent_signature = None
                if self._send:
                    await async_clear_tag(self.hass, self.coordinator, self.tag)
                    await async_clear_tag(self.hass, self.coordinator, self.done_tag)
                self.coordinator.async_update_listeners()
            return

        if not self._active:
            self._active = True
            self._start = temp
            self.coordinator.async_update_listeners()
        unit = self._unit()
        target = self.target
        reached = target > 0 and temp >= target
        progress: int | None = None
        if target > 0:
            start = self._start if self._start is not None and self._start < target else 0.0
            progress = 100 if reached else max(0, round((temp - start) / (target - start) * 100))

        if reached and not self._alerted:
            self._alerted = True
            if self._send:
                await async_send_alert(
                    self.hass,
                    self.coordinator,
                    tag=self.done_tag,
                    title=f"🍖 {self.coordinator.name}: probe at {round(temp)}{unit}",
                    message=f"The probe reached your target of {round(target)}{unit}.",
                )

        if reached:
            signature: tuple = ("reached",)
        elif target > 0:
            signature = ("target", target, (progress or 0) // PROBE_STEP_PERCENT)
        else:
            signature = ("temp", int(temp // PROBE_STEP_DEGREES))
        if not self._send or signature == self._sent_signature:
            return
        if reached:
            message = f"Probe {round(temp)}{unit} · target {round(target)}{unit} reached"
            critical, icon, color = "Ready", "mdi:check-circle", "#4CAF50"
        elif target > 0:
            message = f"Probe {round(temp)}{unit} → {round(target)}{unit}"
            critical, icon, color = f"{round(temp)}{unit}", "mdi:thermometer-probe", None
        else:
            message = f"Probe {round(temp)}{unit}"
            critical, icon, color = f"{round(temp)}{unit}", "mdi:thermometer-probe", None
        await async_send_live(
            self.hass,
            self.coordinator,
            tag=self.tag,
            title=f"{self.coordinator.name} probe",
            message=message,
            critical_text=critical,
            icon=icon,
            color=color,
            progress=progress,
        )
        self._sent_signature = signature


def _duration(minutes: float) -> str:
    total = round(minutes)
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"{hours} h {mins} min"
    if hours:
        return f"{hours} h"
    return f"{mins} min"
