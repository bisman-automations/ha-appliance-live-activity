"""Door monitoring for refrigerators / freezers.

Flow for one appliance (any of its doors):

1. A door has been open for ``open_delay`` (default 30 s, so quick grabs
   don't start an activity) -> Live Activity "Freezer Door is open",
   counting up on the phone.
2. Still open after ``critical_after`` minutes (default 5) -> the activity
   turns red and a **critical** notification is sent, repeated every
   ``critical_repeat`` minutes until the door closes.
   After ``escalate_after`` critical alerts (0 = straight away) the
   optional escalation kicks in: extra phones get the alerts too, speakers
   announce it, and chosen lights turn red.
3. Closed -> critical notifications are removed, lights are restored, the
   activity shows "Closed" for a minute, then it is ended.
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

from typing import Any

from .const import (
    ACTION_SNOOZE_DOOR,
    CLOSED_DISPLAY_SECONDS,
    CONF_CRITICAL_AFTER_MINUTES,
    CONF_ALERT_LIGHTS,
    CONF_CRITICAL_REPEAT_MINUTES,
    CONF_DOOR_ENTITIES,
    CONF_DOOR_ENTITY,
    CONF_ESCALATE_AFTER,
    CONF_ESCALATION_DEVICES,
    CONF_OPEN_DELAY_SECONDS,
    CONF_SNOOZE_MINUTES,
    CONF_SPEAKERS,
    CONF_STATE_ENTITY,
    CONF_TTS_ENTITY,
    DEFAULT_CRITICAL_AFTER_MINUTES,
    DEFAULT_CRITICAL_REPEAT_MINUTES,
    DEFAULT_ESCALATE_AFTER,
    DEFAULT_OPEN_DELAY_SECONDS,
    DEFAULT_SNOOZE_MINUTES,
    EVENT_DOOR_CLOSED,
    EVENT_DOOR_LEFT_OPEN,
    STATUS_IDLE,
    STATUS_RUNNING,
)
from .coordinator import ApplianceCoordinator
from .notify import (
    async_clear_tag,
    async_resolve,
    async_send_alert,
    async_send_door_closed,
    async_send_door_critical,
    async_send_door_open,
    async_speak,
)

_LOGGER = logging.getLogger(__name__)

OPEN_STATES = {STATE_ON, STATE_OPEN, "opening", "door open"}
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
        self.escalation_devices: list[str] = list(cfg.get(CONF_ESCALATION_DEVICES) or [])
        self.escalate_after = int(cfg.get(CONF_ESCALATE_AFTER, DEFAULT_ESCALATE_AFTER) or 0)
        self.alert_lights: list[str] = list(cfg.get(CONF_ALERT_LIGHTS) or [])
        self.tts_entity: str | None = cfg.get(CONF_TTS_ENTITY) or None
        self.speakers: list[str] = list(cfg.get(CONF_SPEAKERS) or [])
        self.snooze_minutes = float(cfg.get(CONF_SNOOZE_MINUTES, DEFAULT_SNOOZE_MINUTES) or 0)
        self._snooze_until: float | None = None
        self._critical_count = 0
        self._lights_scene: str = f"scene.{self.notification_tag}_lights"
        self._lights_saved = False

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
        await self._async_setup_monitors()

    async def async_unload(self) -> None:
        await super().async_unload()
        self._cancel_closed_clear()

    @callback
    def _handle_door_event(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_evaluate(send=True))

    # ------------------------------------------------------------------
    # Snooze button on the critical alert
    # ------------------------------------------------------------------
    def _critical_actions(self) -> list[dict[str, str]] | None:
        if self.snooze_minutes <= 0:
            return None
        return [
            {
                "action": self.action_id(ACTION_SNOOZE_DOOR),
                "title": f"Snooze {round(self.snooze_minutes)} min",
            }
        ]

    def _action_handlers(self) -> dict[str, Any]:
        if self.snooze_minutes <= 0:
            return {}
        return {self.action_id(ACTION_SNOOZE_DOOR): self._async_snooze}

    async def _async_snooze(self) -> None:
        """Pause critical alerts (the Live Activity stays) while the door is open."""
        if self._open_since is None:
            return
        self._snooze_until = dt_util.utcnow().timestamp() + self.snooze_minutes * 60
        _LOGGER.debug("%s: door alerts snoozed for %s min", self.name, self.snooze_minutes)
        if self._last_critical is not None:
            # Replace the critical alert (a silent clear isn't reliable on iOS)
            await async_send_alert(
                self.hass,
                self,
                tag=self.critical_tag,
                title=f"🔕 {self.name}: alert snoozed",
                message=f"Snoozed for {round(self.snooze_minutes)} min — it's still open.",
                level="passive",
                devices=self.devices + self.escalation_devices,
                deferrable=False,
            )
        await self.async_evaluate(send=True)

    @property
    def snoozed(self) -> bool:
        return self._snooze_until is not None and dt_util.utcnow().timestamp() < self._snooze_until

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
            if self._closed_clear_unsub is not None:
                # Reopened while the Live Activity still shows "Closed": carry
                # on with that activity (update it now) instead of waiting for
                # the open delay as if it were a new opening
                self._cancel_closed_clear()
                self._activity_started = True
                self._sent_signature = None
            if self._open_since is None:
                changed = [
                    self.hass.states.get(d).last_changed.timestamp() for d in open_doors
                ]
                self._open_since = min(changed) if changed else now
            elapsed = now - self._open_since
            labels = [self._label(d) for d in open_doors]
            if len(labels) > 1:
                # GE also has an overall "Door" sensor: name the specific doors
                labels = [label for label in labels if label.lower() != "door"] or labels

            if send and self.devices and (self._activity_started or elapsed >= self.open_delay):
                critical = elapsed >= self.critical_after
                signature = (tuple(labels), critical)
                if force or signature != self._sent_signature:
                    await async_send_door_open(
                        self.hass, self, labels=labels, opened_at=self._open_since, critical=critical
                    )
                    self._sent_signature = signature
                    self._activity_started = True
                if critical and not self.snoozed and (
                    self._last_critical is None
                    or now - self._last_critical >= self.critical_repeat - 1
                    or self._snooze_until is not None
                ):
                    self._snooze_until = None
                    self._critical_count += 1
                    if self._critical_count == 1:
                        self.fire_event(
                            EVENT_DOOR_LEFT_OPEN,
                            {"doors": ", ".join(labels), "minutes_open": round(elapsed / 60)},
                        )
                    escalated = self._critical_count > self.escalate_after
                    minutes_open = round(elapsed / 60)
                    devices = self.devices + (self.escalation_devices if escalated else [])
                    await async_send_door_critical(
                        self.hass,
                        self,
                        labels=labels,
                        minutes_open=minutes_open,
                        devices=devices,
                        actions=self._critical_actions(),
                    )
                    self._last_critical = now
                    if escalated:
                        doors = " and ".join(labels)
                        await async_speak(
                            self.hass,
                            self.tts_entity,
                            self.speakers,
                            f"The {self.name} {doors} has been open for {minutes_open} minutes.",
                        )
                        await self._async_lights_red()

            self.async_set_updated_data(
                {
                    "status": STATUS_RUNNING,
                    "phase": ", ".join(labels),
                    "cycle": "",
                    "remaining": 0,
                    "progress": 0,
                    "open_minutes": round(elapsed / 60, 1),
                    "snoozed_until": (
                        dt_util.utc_from_timestamp(self._snooze_until) if self.snoozed else None
                    ),
                }
            )
            return

        # All doors closed
        if self._open_since is not None:
            minutes_open = round((now - self._open_since) / 60)
            if self._activity_started or self._critical_count:
                self.fire_event(EVENT_DOOR_CLOSED, {"minutes_open": minutes_open})
            if send and self.devices and self._activity_started:
                if self._last_critical is not None:
                    await async_resolve(
                        self.hass,
                        self,
                        tag=self.critical_tag,
                        title=f"✅ {self.name}: closed",
                        message=f"Closed after {minutes_open} min.",
                        devices=self.devices + self.escalation_devices,
                        still_resolved=lambda: self._open_since is None,
                    )
                await async_send_door_closed(self.hass, self, minutes_open=minutes_open)
                self._schedule_closed_clear()
            await self._async_lights_restore()
        self._open_since = None
        self._activity_started = False
        self._sent_signature = None
        self._last_critical = None
        self._snooze_until = None
        self._critical_count = 0
        self.async_set_updated_data(
            {"status": STATUS_IDLE, "phase": "", "cycle": "", "remaining": 0, "progress": 0}
        )

    # ------------------------------------------------------------------
    async def _async_lights_red(self) -> None:
        """Snapshot the alert lights once, then turn them red."""
        if not self.alert_lights or self._lights_saved:
            return
        scene_id = self._lights_scene.split(".", 1)[1]
        try:
            await self.hass.services.async_call(
                "scene", "create",
                {"scene_id": scene_id, "snapshot_entities": self.alert_lights},
                blocking=True,
            )
            self._lights_saved = True
            await self.hass.services.async_call(
                "light", "turn_on",
                {"rgb_color": [255, 0, 0], "brightness_pct": 100},
                target={"entity_id": self.alert_lights},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not turn alert lights red")

    async def _async_lights_restore(self) -> None:
        if not self._lights_saved:
            return
        self._lights_saved = False
        try:
            await self.hass.services.async_call(
                "scene", "turn_on", target={"entity_id": self._lights_scene}, blocking=True
            )
            await self.hass.services.async_call(
                "scene", "delete", target={"entity_id": self._lights_scene}, blocking=False
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not restore alert lights")

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
