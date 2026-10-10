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
    CONF_ACTIVITY_TITLE,
    CONF_APPLIANCE_TYPE,
    CONF_CLEAN_ENTITY,
    CONF_COMBINE_LAUNDRY,
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
    CONF_FILTER_ENTITY,
    CONF_FINISHED_ALERT,
    CONF_FREEZER_MAX_TEMP,
    CONF_FREEZER_TEMP_ENTITY,
    CONF_FRIDGE_MAX_TEMP,
    CONF_FRIDGE_TEMP_ENTITY,
    CONF_ONLY_HOME,
    CONF_ICE_ENTITY,
    CONF_ICE_FULL_ALERT,
    CONF_ICON,
    CONF_ICON_COLOR,
    CONF_IDLE_STATES,
    CONF_LAUNDRY_TITLE,
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
    CONF_PROBE_ENTITY,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_REMAINING_ENTITY,
    CONF_SOURCE_DEVICE,
    CONF_SPEAKERS,
    CONF_STATE_ENTITY,
    CONF_SUPPLY_ENTITIES,
    CONF_SUPPLY_LOW,
    CONF_TARGET_TEMPERATURE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_TIMER_ENTITY,
    CONF_TTS_ENTITY,
    CONF_TUMBLE_ENTITY,
    CONF_VENT_ENTITY,
    CONF_WARM_MINUTES,
    DEFAULT_COOKTOP_ALERT_MINUTES,
    DEFAULT_COOKTOP_REPEAT_MINUTES,
    DEFAULT_DISMISS_MINUTES,
    DEFAULT_DRYER_MAX_REMINDERS,
    DEFAULT_DRYER_REMINDER_MINUTES,
    DEFAULT_DRYER_REPEAT_MINUTES,
    DEFAULT_FREEZER_MAX_C,
    DEFAULT_FREEZER_MAX_F,
    DEFAULT_FRIDGE_MAX_C,
    DEFAULT_FRIDGE_MAX_F,
    DEFAULT_LEAK_REPEAT_MINUTES,
    DEFAULT_MOVE_MAX_REMINDERS,
    DEFAULT_MOVE_REMINDER_MINUTES,
    DEFAULT_MOVE_REPEAT_MINUTES,
    DEFAULT_SUPPLY_LOW,
    DEFAULT_WARM_MINUTES,
    DOMAIN,
    DRIFT_MINUTES,
    EVENT_CANCELLED,
    EVENT_FINISHED,
    EVENT_NOTIFICATION_ACTION,
    EVENT_SCHEDULED,
    EVENT_STARTED,
    HISTORY_AVERAGE_OF,
    HISTORY_MAX,
    FINISHED_THRESHOLD_MINUTES,
    PREHEAT_TOLERANCE,
    STATUS_COMPLETE,
    STATUS_DELAYED,
    STATUS_IDLE,
    STATUS_PAUSED,
    STATUS_RUNNING,
    STORAGE_VERSION,
)
from .helpers import classify_state, color_to_hex, in_quiet_hours, meaningful, to_minutes
from .notify import (
    async_clear,
    async_clear_tag,
    async_send_delayed,
    async_send_done,
    async_send_dryer_remote_off,
    async_send_finished_alert,
    async_send_move_reminder,
    async_send_preheated,
    async_deliver,
    async_send_progress,
    async_send_stopped,
)

_LOGGER = logging.getLogger(__name__)

ACTIVE = (STATUS_RUNNING, STATUS_PAUSED)
# Seconds "Off" / "Stopped" shows before the Live Activity is ended
STOPPED_DISPLAY_SECONDS = 60


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

        # Laundry left in the machine: washer "move it to the dryer", dryer
        # "unload it" (0 minutes = off)
        if self.appliance_type == "dryer":
            defaults = (DEFAULT_DRYER_REMINDER_MINUTES, DEFAULT_DRYER_REPEAT_MINUTES, DEFAULT_DRYER_MAX_REMINDERS)
        else:
            defaults = (DEFAULT_MOVE_REMINDER_MINUTES, DEFAULT_MOVE_REPEAT_MINUTES, DEFAULT_MOVE_MAX_REMINDERS)
        self.move_minutes: float = float(
            cfg.get(CONF_MOVE_REMINDER_MINUTES, defaults[0]) or 0
        ) if self.appliance_type in ("washer", "dryer") else 0.0
        self.move_repeat: float = float(cfg.get(CONF_MOVE_REPEAT_MINUTES, defaults[1]) or defaults[1])
        self.move_max: int = int(cfg.get(CONF_MOVE_MAX_REMINDERS, defaults[2]) or 1)

        # Regular alerts only to phones whose owner is home
        self.home_only: bool = bool(cfg.get(CONF_ONLY_HOME, False))
        # Dishwasher: keep "Done" up while clean dishes are inside
        self.clean_entity: str | None = (
            cfg.get(CONF_CLEAN_ENTITY) or None if self.appliance_type == "dishwasher" else None
        )
        # Event entity + cycle history
        self._event_listeners: list[Any] = []
        self._history: list[list[float]] = []  # [finished_at, minutes]
        self._cycle_started: float | None = None
        # Tag of the Live Activity this appliance is showing (see activity_tag)
        self._active_tag: str | None = None
        # Laundry loads: each load gets its own finished notification, which
        # follows it from the washer to the dryer
        self._load: dict[str, Any] | None = None
        self._washed_loads: list[dict[str, Any]] = []
        self._load_counter = 0
        self._last_load_tag: str | None = None

        # Quiet hours: regular alerts wait until they end
        self.quiet_start: str | None = cfg.get(CONF_QUIET_START) or None
        self.quiet_end: str | None = cfg.get(CONF_QUIET_END) or None
        self._deferred: dict[str, tuple[dict[str, Any], list[str] | None, bool]] = {}
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

        # Oven kitchen timer / meat probe Live Activities
        self.timer = None
        self.probe = None
        if self.appliance_type == "oven":
            from .oven_extras import KitchenTimerMonitor, ProbeMonitor  # noqa: PLC0415

            if cfg.get(CONF_TIMER_ENTITY):
                self.timer = KitchenTimerMonitor(hass, self, cfg[CONF_TIMER_ENTITY])
                self.monitors.append(self.timer)
            if cfg.get(CONF_PROBE_ENTITY):
                self.probe = ProbeMonitor(hass, self, cfg[CONF_PROBE_ENTITY])
                self.monitors.append(self.probe)

        # Health: blocked dryer vent, refill reminders, water filter
        from .maintenance import FilterMonitor, SupplyMonitor, VentMonitor  # noqa: PLC0415

        self.vent = None
        if self.appliance_type == "dryer" and cfg.get(CONF_VENT_ENTITY):
            self.vent = VentMonitor(
                hass,
                self,
                cfg[CONF_VENT_ENTITY],
                cfg.get(CONF_TTS_ENTITY) or None,
                list(cfg.get(CONF_SPEAKERS) or []),
            )
            self.monitors.append(self.vent)
        self.supplies = None
        supply_entities = list(cfg.get(CONF_SUPPLY_ENTITIES) or [])
        if supply_entities:
            self.supplies = SupplyMonitor(
                hass, self, supply_entities, float(cfg.get(CONF_SUPPLY_LOW, DEFAULT_SUPPLY_LOW))
            )
            self.monitors.append(self.supplies)
        self.filter = None
        if cfg.get(CONF_FILTER_ENTITY):
            self.filter = FilterMonitor(hass, self, cfg[CONF_FILTER_ENTITY])
            self.monitors.append(self.filter)

        # Fridge / freezer too warm, ice bucket full
        self.fridge = None
        if self.appliance_type == "refrigerator":
            from .maintenance import FridgeMonitor  # noqa: PLC0415

            fahrenheit = hass.config.units.temperature_unit == "°F"
            zones = {
                "fridge": (
                    cfg.get(CONF_FRIDGE_TEMP_ENTITY),
                    cfg.get(CONF_FRIDGE_MAX_TEMP, DEFAULT_FRIDGE_MAX_F if fahrenheit else DEFAULT_FRIDGE_MAX_C),
                ),
                "freezer": (
                    cfg.get(CONF_FREEZER_TEMP_ENTITY),
                    cfg.get(CONF_FREEZER_MAX_TEMP, DEFAULT_FREEZER_MAX_F if fahrenheit else DEFAULT_FREEZER_MAX_C),
                ),
            }
            zones = {z: (e, float(limit)) for z, (e, limit) in zones.items() if e and limit is not None}
            ice = cfg.get(CONF_ICE_ENTITY) if cfg.get(CONF_ICE_FULL_ALERT, False) else None
            if zones or ice:
                self.fridge = FridgeMonitor(
                    hass,
                    self,
                    zones=zones,
                    warm_minutes=float(cfg.get(CONF_WARM_MINUTES, DEFAULT_WARM_MINUTES)),
                    ice_entity=ice,
                )
                self.monitors.append(self.fridge)

        # Dryer: extended (wrinkle-guard) tumble after the cycle
        self.tumble_entity: str | None = (
            cfg.get(CONF_TUMBLE_ENTITY) or None if self.appliance_type == "dryer" else None
        )
        self.custom_title: str = (cfg.get(CONF_ACTIVITY_TITLE) or "").strip()
        self.laundry_title: str = (cfg.get(CONF_LAUNDRY_TITLE) or "").strip()
        # Washer + dryer share one Live Activity
        self.combine_laundry: bool = (
            self.appliance_type == "washer"
            and bool(self.dryer_entity)
            and cfg.get(CONF_COMBINE_LAUNDRY, True) is not False
        )

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
        self._stop_unsub: CALLBACK_TYPE | None = None

        self.data = {
            "status": STATUS_IDLE,
            "phase": "",
            "cycle": "",
            "remaining": 0,
            "progress": 0,
        }

    # ------------------------------------------------------------------
    # Shared washer + dryer Live Activity
    # ------------------------------------------------------------------
    def partner(self) -> ApplianceCoordinator | None:
        """The washer <-> dryer this appliance shares its Live Activity with."""
        coordinators = [
            c
            for c in self.hass.data.get(DOMAIN, {}).values()
            if isinstance(c, ApplianceCoordinator) and c is not self
        ]
        if self.combine_laundry:
            return next(
                (c for c in coordinators if c.appliance_type == "dryer" and c.state_entity == self.dryer_entity),
                None,
            )
        if self.appliance_type == "dryer" and self.state_entity:
            return next(
                (
                    c
                    for c in coordinators
                    if c.combine_laundry and c.dryer_entity == self.state_entity
                ),
                None,
            )
        return None

    @property
    def activity_tag(self) -> str:
        """Tag of this appliance's Live Activity. Fixed for as long as the
        activity is up (see _async_claim_activity)."""
        if self._active_tag:
            return self._active_tag
        return self._preferred_tag()[0]

    def _preferred_tag(self) -> tuple[str, ApplianceCoordinator | None]:
        """(tag, appliance whose finished activity is taken over).

        A washer + dryer share one Live Activity per load: the dryer takes
        over the washer's finished "move to the dryer" activity. If both run
        at the same time (a new wash while the last load dries), the one
        that starts second gets a Live Activity of its own, so the two never
        overwrite each other.
        """
        partner = self.partner()
        if partner is None:
            return self.notification_tag, None
        if self.appliance_type == "dryer":
            if partner._active_tag and not partner.owns_activity():
                return partner._active_tag, partner  # the washed load moves on
            if partner.owns_activity():
                return self.notification_tag, None  # washer busy: own activity
            return partner.notification_tag, None
        shared = self.notification_tag
        if partner._active_tag == shared:
            return f"{shared}_2", None  # the dryer is showing the last load
        return shared, None

    async def _async_claim_activity(self) -> None:
        """Fix the Live Activity this cycle uses."""
        if self._active_tag is not None:
            return
        tag, previous = self._preferred_tag()
        if previous is not None:
            await previous._async_hand_over()
        self._active_tag = tag

    async def _async_hand_over(self) -> None:
        """The partner took over this appliance's finished Live Activity."""
        self._cancel_dismiss()
        self._dismiss_at = None
        self._active_tag = None
        await self._async_save()

    async def _async_end_activity(self) -> None:
        """End this appliance's Live Activity (unless the partner took it)."""
        tag = self.activity_tag
        self._active_tag = None
        await self._async_save()
        partner = self.partner()
        if partner is not None and partner._active_tag == tag:
            return
        if self.devices:
            await async_clear(self.hass, self, tag)

    @property
    def activity_title(self) -> str:
        """Live Activity title: the custom title, else the appliance's name
        (as renamed in Home Assistant). A shared washer + dryer activity
        follows whichever is running, unless the washer sets one title."""
        partner = self.partner()
        if partner is not None:
            washer = self if self.combine_laundry else partner
            if washer.laundry_title:
                return washer.laundry_title
        return self.display_title

    @property
    def display_title(self) -> str:
        if self.custom_title:
            return self.custom_title
        device = dr.async_get(self.hass).async_get_device(identifiers={(DOMAIN, self.entry.entry_id)})
        if device is not None and device.name_by_user:
            return device.name_by_user
        return self.name

    def owns_activity(self) -> bool:
        """This appliance is currently showing something on the Live Activity."""
        return self._in_cycle or self._delay_sent is not None

    # ------------------------------------------------------------------
    # Laundry loads
    # ------------------------------------------------------------------
    def _washer_for_dryer(self) -> ApplianceCoordinator | None:
        """The washer that feeds this dryer (its dryer sensor is this dryer)."""
        if self.appliance_type != "dryer" or not self.state_entity:
            return None
        return next(
            (
                c
                for c in self.hass.data.get(DOMAIN, {}).values()
                if isinstance(c, ApplianceCoordinator)
                and c.appliance_type == "washer"
                and c.dryer_entity == self.state_entity
            ),
            None,
        )

    def _start_load(self, cycle: str) -> None:
        if self.appliance_type not in ("washer", "dryer"):
            return
        now = dt_util.utcnow().timestamp()
        if self.appliance_type == "dryer":
            washer = self._washer_for_dryer()
            if washer is not None:
                # Loads washed in the last day, oldest first
                washer._washed_loads = [
                    load for load in washer._washed_loads if now - load.get("at", now) < 86400
                ]
                if washer._washed_loads:
                    self._load = washer._washed_loads.pop(0)
                    washer._store.async_delay_save(washer._data_to_save, 1)
                    return
        self._load_counter += 1
        self._load = {
            "tag": f"{self.notification_tag}_load_{self._load_counter}",
            "name": cycle or None,
            "washed": False,
            "at": now,
        }

    def _load_alert(self) -> tuple[str | None, str | None, str | None]:
        """(title, message, tag) of the finished alert for the current load."""
        load = self._load
        if load is None or self.appliance_type not in ("washer", "dryer"):
            return None, None, None
        name = load.get("name")
        who = self.display_title
        if self.appliance_type == "washer":
            next_step = "Load it into the dryer." if self.dryer_entity else "Time to take it out."
            if name:
                return (
                    f"✅ {name}: washed",
                    f"{who} finished the {name} cycle. {next_step}",
                    load["tag"],
                )
            return f"✅ {who} finished", f"The wash is done. {next_step}", load["tag"]
        if load.get("washed"):
            if name:
                return (
                    f"✅ {name}: load complete",
                    f"Your {name} load has been washed and dried. Please take care of it.",
                    load["tag"],
                )
            return (
                "✅ Laundry load complete",
                "Your load has been washed and dried. Please take care of it.",
                load["tag"],
            )
        if name:
            return (
                f"✅ {name}: dry",
                f"{who} finished the {name} cycle. Please take care of it.",
                load["tag"],
            )
        return f"✅ {who} finished", "The laundry is dry. Please take care of it.", load["tag"]

    def _finish_load(self, finished: bool) -> None:
        load, self._load = self._load, None
        if load is None or not finished:
            return  # a cancelled cycle isn't a load
        self._last_load_tag = load["tag"]
        if self.appliance_type == "washer":
            load["washed"] = True
            load["at"] = dt_util.utcnow().timestamp()
            self._washed_loads = (self._washed_loads + [load])[-3:]

    def configured_entities(self) -> list[str]:
        """Every entity this appliance was set up to use (for Repairs / diagnostics)."""
        cfg = {**self.entry.data, **self.entry.options}
        found: list[str] = []
        for key, value in cfg.items():
            if not (key.endswith("_entity") or key.endswith("_entities")) or not value:
                continue
            for entity_id in value if isinstance(value, list) else [value]:
                if isinstance(entity_id, str) and "." in entity_id and entity_id not in found:
                    found.append(entity_id)
        return found

    def diagnostics(self) -> dict[str, Any]:
        """Internal state for the diagnostics download."""
        return {
            "in_cycle": self._in_cycle,
            "total_minutes": self._total_minutes,
            "last_remaining": self._last_remaining,
            "dismiss_at": self._dismiss_at,
            "move_since": self._move_since,
            "move_count": self._move_count,
            "delay_target": self._delay_target,
            "activity_tag": self.activity_tag,
            "partner": self.partner().name if self.partner() else None,
            "quiet_now": self.quiet_now(),
            "held_alerts": list(self._deferred),
            "history": self._history[-20:],
            "monitors": [type(m).__name__ for m in self.monitors],
        }

    def action_id(self, suffix: str) -> str:
        """Notification button id, unique to this appliance."""
        return f"{self.notification_tag}_{suffix}".upper()

    # ------------------------------------------------------------------
    # Quiet hours
    # ------------------------------------------------------------------
    def quiet_now(self) -> bool:
        return in_quiet_hours(
            dt_util.as_local(dt_util.utcnow()).time(), self.quiet_start, self.quiet_end
        )

    def defer(
        self,
        tag: str | None,
        payload: dict[str, Any],
        devices: list[str] | None,
        home_filter: bool = False,
    ) -> None:
        """Hold a regular alert until quiet hours end (the latest per tag wins)."""
        _LOGGER.debug("%s: quiet hours, holding %s", self.name, tag)
        self._deferred[tag or f"_{len(self._deferred)}"] = (payload, devices, home_filter)

    def drop_deferred(self, tag: str | None) -> None:
        if tag:
            self._deferred.pop(tag, None)

    @callback
    def _handle_quiet_tick(self, _now=None) -> None:
        if self._deferred and not self.quiet_now():
            self.hass.async_create_task(self._async_flush_deferred())

    async def _async_flush_deferred(self) -> None:
        pending, self._deferred = self._deferred, {}
        for payload, devices, home_filter in pending.values():
            await async_deliver(self.hass, self, payload, devices, home_filter)

    def washer_actions(self) -> list[dict[str, str]]:
        """Buttons on the washer's / dryer's finished alert and reminders."""
        if self.appliance_type == "dryer":
            if self.move_minutes <= 0:
                return []
            return [{"action": self.action_id(ACTION_LAUNDRY_MOVED), "title": "Unloaded"}]
        actions: list[dict[str, str]] = []
        if self.dryer_start_entity:
            actions.append({"action": self.action_id(ACTION_START_DRYER), "title": "Start dryer"})
        if self.move_minutes > 0 or self.dryer_start_entity:
            actions.append({"action": self.action_id(ACTION_LAUNDRY_MOVED), "title": "Laundry moved"})
        return actions

    def tap_path(self) -> str:
        """Where tapping a notification / Live Activity goes in the app.

        The appliance's own device page (e.g. the GE washer, with its controls,
        or another brand's device the state sensor belongs to) when there is
        one, else this integration's device for the appliance, else the
        integration page.
        """
        from .device import appliance_device_id  # noqa: PLC0415

        dev_reg = dr.async_get(self.hass)
        appliance = appliance_device_id(self.hass, self)
        if appliance is not None:
            return f"/config/devices/device/{appliance}"
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
        self._history = [list(h) for h in stored.get("history", []) if len(h) == 2][-HISTORY_MAX:]
        self._cycle_started = stored.get("cycle_started")
        self._active_tag = stored.get("active_tag")
        self._load = stored.get("load")
        self._washed_loads = list(stored.get("washed_loads") or [])
        self._load_counter = int(stored.get("load_counter", 0) or 0)
        self._last_load_tag = stored.get("last_load_tag")

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
                self.tumble_entity,
                self.clean_entity,
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
        from .health import async_setup_health  # noqa: PLC0415

        self._unsubs.extend(async_setup_health(self.hass, self))
        self._unsubs.append(
            self.hass.bus.async_listen(EVENT_NOTIFICATION_ACTION, self._handle_action)
        )
        self._unsubs.append(
            async_track_time_interval(self.hass, self._handle_quiet_tick, timedelta(minutes=1))
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
            # "move the laundry" reminders. A shared laundry activity stays
            # up until the dryer takes it over (or the dismiss delay).
            if self._dismiss_at is not None and not self.combine_laundry:
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
        if self.appliance_type == "dryer":
            return {self.action_id(ACTION_LAUNDRY_MOVED): self._async_laundry_moved}
        if self.appliance_type != "washer":
            return {}
        return {
            self.action_id(ACTION_LAUNDRY_MOVED): self._async_laundry_moved,
            self.action_id(ACTION_START_DRYER): self._async_start_dryer,
        }

    async def _async_laundry_moved(self) -> None:
        """'Laundry moved' / 'Unloaded': stop reminders and remove the finished
        alert / activity. A washed load headed for the dryer keeps its
        notification -- the dryer finishes it."""
        await self._async_cancel_move("laundry moved")
        if self.devices and not (self.appliance_type == "washer" and self.dryer_entity):
            await async_clear_tag(
                self.hass, self, self._last_load_tag or f"{self.notification_tag}_done"
            )
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
        if self._tumbling(status):
            # Cycle is over; the drum just turns now and then to stop wrinkles
            return STATUS_COMPLETE
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

    def _clean_inside(self) -> bool:
        """Dishwasher reports clean dishes and the door hasn't been opened."""
        if not self.clean_entity or self._state(self.clean_entity) != STATE_ON:
            return False
        return not (self.door_entity and self._state(self.door_entity) == STATE_ON)

    # ------------------------------------------------------------------
    # Event entity + cycle history
    # ------------------------------------------------------------------
    @callback
    def add_event_listener(self, listener) -> CALLBACK_TYPE:
        self._event_listeners.append(listener)

        @callback
        def _remove() -> None:
            if listener in self._event_listeners:
                self._event_listeners.remove(listener)

        return _remove

    @callback
    def fire_event(self, event_type: str, attributes: dict[str, Any] | None = None) -> None:
        for listener in list(self._event_listeners):
            listener(event_type, {k: v for k, v in (attributes or {}).items() if v not in (None, "")})

    def cycles_since(self, days: float) -> int:
        cutoff = dt_util.utcnow().timestamp() - days * 86400
        return sum(1 for finished_at, _ in self._history if finished_at >= cutoff)

    def average_minutes(self) -> float | None:
        recent = [m for _, m in self._history[-HISTORY_AVERAGE_OF:]]
        return round(sum(recent) / len(recent)) if recent else None

    def _tumbling(self, status: str | None = None) -> bool:
        """Dryer in extended (wrinkle-guard) tumble after the cycle."""
        if self.appliance_type != "dryer":
            return False
        if self.door_entity and self._state(self.door_entity) == STATE_ON:
            return False  # door opened: laundry is being taken out
        phase = self._state(self.phase_entity).lower()
        if "extended tumble" in phase or "wrinkle" in phase:
            return True
        if not self.tumble_entity or self._state(self.tumble_entity).lower() not in ("enable", "on", "enabled"):
            return False
        # The tumble setting can stay "Enable"; the dryer must also still be on
        raw = self._state(self.state_entity).strip().lower()
        if not raw or raw in {i.lower() for i in self.idle_states} or raw in ("off", "unavailable", "unknown"):
            return False
        if status is None:
            status = STATUS_COMPLETE if self._dismiss_at is not None else STATUS_IDLE
        return status == STATUS_COMPLETE and self._remaining_minutes() <= 0

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
        await self._async_claim_activity()

        now = dt_util.utcnow().timestamp()
        value, minutes = self._delay_minutes()
        # Recompute the start time only when the sensor reports something new:
        # GE laundry / ovens count down, GE dishwashers only report the chosen
        # delay, which must not push the start time forward every minute.
        if self._delay_value is None and self._delay_target is None:
            self.fire_event(EVENT_SCHEDULED, {"cycle": cycle, "starts_in_minutes": round(minutes) or None})
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
        if sent and send and not self._in_cycle and self._dismiss_at is None:
            await self._async_end_activity()

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
            self._cycle_started = dt_util.utcnow().timestamp()
            await self._async_claim_activity()
            self._start_load(cycle)
            changed = True
            self.fire_event(EVENT_STARTED, {"cycle": cycle, "minutes_left": round(remaining)})
        elif self._load is not None and not self._load.get("name") and cycle and not self._load.get("washed"):
            # The cycle name often arrives a moment after the machine starts
            self._load["name"] = cycle
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
        now = dt_util.utcnow().timestamp()
        duration = (now - self._cycle_started) / 60 if self._cycle_started else None
        self._cycle_started = None
        if finished:
            if duration is not None and duration > 0:
                self._history = (self._history + [[now, round(duration, 1)]])[-HISTORY_MAX:]
            self.fire_event(
                EVENT_FINISHED,
                {"cycle": cycle, "minutes": round(duration) if duration is not None else None},
            )
        else:
            self.fire_event(EVENT_CANCELLED, {"cycle": cycle})

        if send and self.devices:
            if finished and self.definition.supports_progress:
                note = ""
                if self._tumbling(status):
                    note = "tumbling to prevent wrinkles"
                elif self._clean_inside():
                    note = "ready to unload"
                elif self.combine_laundry:
                    note = "move to the dryer"
                await async_send_done(self.hass, self, cycle, note)
                if self.finished_alert:
                    title, message, tag = self._load_alert()
                    await async_send_finished_alert(
                        self.hass,
                        self,
                        actions=self.washer_actions()
                        if self.appliance_type in ("washer", "dryer")
                        else None,
                        title=title,
                        message=message,
                        tag=tag,
                    )
                self._dismiss_at = dt_util.utcnow().timestamp() + self.dismiss_minutes * 60
                self._schedule_dismiss(self.dismiss_minutes * 60)
            elif self._active_tag is not None:
                # Turned off before finishing (e.g. an oven used without a cook
                # timer): show it, then end the activity a minute later
                await async_send_stopped(self.hass, self, minutes=duration)
                self._schedule_stop_end()
            else:
                await self._async_end_activity()
        self._finish_load(finished)
        if finished and self.move_minutes > 0:
            # Washer done: remind to move the laundry unless the door opens
            self._move_since = dt_util.utcnow().timestamp()
            self._move_count = 0
        await self._async_save()
        if finished and self.supplies is not None:
            await self.supplies.async_after_cycle()

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
        if self._stop_unsub is not None:
            self._stop_unsub()
            self._stop_unsub = None

    def _schedule_stop_end(self) -> None:
        if self._stop_unsub is not None:
            self._stop_unsub()

        @callback
        def _fire(_now) -> None:
            self._stop_unsub = None
            if not self._in_cycle and self._delay_sent is None and self._dismiss_at is None:
                self.hass.async_create_task(self._async_end_activity())

        self._stop_unsub = async_call_later(self.hass, STOPPED_DISPLAY_SECONDS, _fire)

    async def _async_dismiss(self) -> None:
        self._cancel_dismiss()
        if self._dismiss_at is None or self._in_cycle:
            _LOGGER.debug("%s: dismiss skipped (in cycle: %s)", self.name, self._in_cycle)
            return
        if self._tumbling(STATUS_COMPLETE) or self._clean_inside():
            # Still tumbling / clean dishes inside: keep "Done" up until the door opens
            self._dismiss_at = dt_util.utcnow().timestamp() + self.dismiss_minutes * 60
            self._schedule_dismiss(self.dismiss_minutes * 60)
            await self._async_save()
            return
        _LOGGER.debug("%s: dismissing finished Live Activity", self.name)
        self._dismiss_at = None
        await self._async_end_activity()

    @callback
    def _data_to_save(self) -> dict[str, Any]:
        return {
            "total_minutes": self._total_minutes,
            "in_cycle": self._in_cycle,
            "last_remaining": self._last_remaining,
            "dismiss_at": self._dismiss_at,
            "move_since": self._move_since,
            "move_count": self._move_count,
            "history": self._history,
            "cycle_started": self._cycle_started,
            "active_tag": self._active_tag,
            "load": self._load,
            "washed_loads": self._washed_loads,
            "load_counter": self._load_counter,
            "last_load_tag": self._last_load_tag,
        }

    async def _async_save(self) -> None:
        await self._store.async_save(self._data_to_save())
