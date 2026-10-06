"""Appliance health alerts.

* **Blocked dryer vent** (GE reports it): critical alert -- a blocked vent is
  a fire risk -- repeated every 30 minutes while flagged, removed when it
  clears.
* **Refill reminders**: after a cycle finishes, one notification listing the
  supplies that are low (washer detergent tank, dishwasher pods / rinse
  aid, dryer sheets). Each supply is mentioned once until it's refilled.
* **Fridge / freezer too warm** (e.g. a door left ajar or a power cut): a
  critical alert once it has been above the limit for a while, repeated every
  hour, then "back to normal". Optional ice-bucket-full notification.
* **Filter**: fridge water filter -- a notification when it needs replacing
  or has expired, a critical alert if it reports a leak; dishwasher -- a
  notification when the filter needs cleaning.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import ATTR_FRIENDLY_NAME, ATTR_UNIT_OF_MEASUREMENT, STATE_ON
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import SUPPLY_LOW_PERCENT, UNAVAILABLE_STATES, VENT_REPEAT_MINUTES, WARM_REPEAT_MINUTES
from .notify import async_clear_tag, async_send_alert, async_speak

if TYPE_CHECKING:
    from .coordinator import ApplianceCoordinator

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(minutes=1)

LOW_WORDS = {"low", "empty", "on", "true", "yes", "add", "add rinse aid", "refill"}
OK_WORDS = {"off", "false", "no", "full", "good", "ok", "normal"}

# Friendly names for GE's supply sensors
SUPPLY_LABELS = (
    (r"(loads_left|tank_status)$", "Detergent", "loads"),
    (r"pods_remaining(_value)?$", "Dishwasher pods", "pods"),
    (r"rinse_aid$", "Rinse aid", ""),
    (r"sheet_inventory$", "Dryer sheets", "sheets"),
)


def supply_low(state: str, unit: str | None, low: float) -> bool | None:
    """True / False, or None if the sensor has nothing useful to say."""
    text = (state or "").strip().lower()
    if text in UNAVAILABLE_STATES or text == "n/a":
        return None
    if text in LOW_WORDS:
        return True
    if text in OK_WORDS:
        return False
    try:
        value = float(text)
    except ValueError:
        return None
    if unit == "%":
        return value <= SUPPLY_LOW_PERCENT
    return value <= low


class _Base:
    def __init__(self, hass: HomeAssistant, coordinator: ApplianceCoordinator, entities: list[str]):
        self.hass = hass
        self.coordinator = coordinator
        self.entities = entities
        self._unsubs: list[CALLBACK_TYPE] = []

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
        raise NotImplementedError


class VentMonitor(_Base):
    """GE 'blocked vent fault' -> critical alert."""

    def __init__(self, hass, coordinator, entity: str, tts_entity: str | None, speakers: list[str]):
        super().__init__(hass, coordinator, [entity])
        self.tag = f"{coordinator.notification_tag}_vent"
        self.tts_entity = tts_entity
        self.speakers = speakers
        self._last_alert: float | None = None

    @property
    def blocked(self) -> bool:
        state = self.hass.states.get(self.entities[0])
        return state is not None and state.state == STATE_ON

    async def async_evaluate(self) -> None:
        now = dt_util.utcnow().timestamp()
        if not self.blocked:
            if self._last_alert is not None:
                self._last_alert = None
                if self.coordinator.devices:
                    await async_clear_tag(self.hass, self.coordinator, self.tag)
                self.coordinator.async_update_listeners()
            return
        if self._last_alert is not None and now - self._last_alert < VENT_REPEAT_MINUTES * 60 - 1:
            return
        first = self._last_alert is None
        self._last_alert = now
        _LOGGER.warning("%s: blocked vent reported", self.coordinator.name)
        if self.coordinator.devices:
            await async_send_alert(
                self.hass,
                self.coordinator,
                tag=self.tag,
                title=f"🔥 {self.coordinator.name}: vent blocked",
                message="The dryer reports a blocked vent — a fire risk. Stop the dryer "
                "and clear the lint trap, vent hose and outside vent.",
                level="critical",
            )
        await async_speak(
            self.hass,
            self.tts_entity,
            self.speakers,
            f"Warning. The {self.coordinator.name} reports a blocked vent.",
        )
        if first:
            self.coordinator.async_update_listeners()


class SupplyMonitor(_Base):
    """Refill reminders, sent after a cycle finishes."""

    def __init__(self, hass, coordinator, entities: list[str], low: float):
        super().__init__(hass, coordinator, entities)
        self.low = low
        self.tag = f"{coordinator.notification_tag}_supplies"
        self._reminded: set[str] = set()

    def _label(self, entity_id: str) -> tuple[str, str]:
        for pattern, label, unit in SUPPLY_LABELS:
            if re.search(pattern, entity_id):
                return label, unit
        state = self.hass.states.get(entity_id)
        name = (state.attributes.get(ATTR_FRIENDLY_NAME) if state else None) or entity_id
        if name.lower().startswith(self.coordinator.name.lower() + " "):
            name = name[len(self.coordinator.name) + 1 :]
        return name, ""

    def low_supplies(self) -> list[tuple[str, str]]:
        """(entity_id, description) for every supply that is low."""
        result = []
        for entity_id in self.entities:
            state = self.hass.states.get(entity_id)
            if state is None or entity_id.endswith("_clean_filter"):
                continue  # a filter reminder, not a supply
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            if not supply_low(state.state, unit, self.low):
                continue
            label, count_unit = self._label(entity_id)
            try:
                value = float(state.state)
            except ValueError:
                result.append((entity_id, f"{label}: {state.state.lower()}"))
                continue
            if unit == "%":
                result.append((entity_id, f"{label}: {round(value)}% left"))
            else:
                result.append((entity_id, f"{label}: {round(value)} {unit or count_unit} left".replace("  ", " ")))
        return result

    async def async_evaluate(self) -> None:
        # Forget reminders for supplies that have been refilled
        low = {entity_id for entity_id, _ in self.low_supplies()}
        self._reminded &= low

    async def async_after_cycle(self) -> None:
        """Called by the coordinator when a cycle finishes."""
        items = [(e, text) for e, text in self.low_supplies() if e not in self._reminded]
        if not items or not self.coordinator.devices:
            return
        self._reminded |= {e for e, _ in items}
        await async_send_alert(
            self.hass,
            self.coordinator,
            tag=self.tag,
            title=f"🧴 {self.coordinator.name}: time to refill",
            message=" · ".join(text for _, text in items),
            level="active",
        )


CLEAN_FILTER_STATES = {"on", "true", "yes", "clean", "dirty", "replace"}


class FilterMonitor(_Base):
    """Fridge water filter ('Replace', 'Expired', 'Leak Detected') or the
    dishwasher's 'clean filter' reminder."""

    def __init__(self, hass, coordinator, entity: str):
        super().__init__(hass, coordinator, [entity])
        self.tag = f"{coordinator.notification_tag}_filter"
        self._alerted: str | None = None

    @property
    def status(self) -> str:
        state = self.hass.states.get(self.entities[0])
        return state.state.strip().lower() if state else ""

    async def async_evaluate(self) -> None:
        status = self.status
        if status in UNAVAILABLE_STATES or status == "n/a":
            return
        if self.coordinator.appliance_type == "dishwasher":
            await self._async_dishwasher(status in CLEAN_FILTER_STATES)
            return
        if status not in ("replace", "expired", "leak detected"):
            if self._alerted is not None:
                self._alerted = None
                if self.coordinator.devices:
                    await async_clear_tag(self.hass, self.coordinator, self.tag)
            return
        if status == self._alerted or not self.coordinator.devices:
            self._alerted = status
            return
        self._alerted = status
        if status == "leak detected":
            await async_send_alert(
                self.hass,
                self.coordinator,
                tag=self.tag,
                title=f"💧 {self.coordinator.name}: water filter leak",
                message="The water filter reports a leak. Check it now.",
                level="critical",
            )
        else:
            await async_send_alert(
                self.hass,
                self.coordinator,
                tag=self.tag,
                title=f"🚰 {self.coordinator.name}: replace the water filter",
                message="The water filter has expired." if status == "expired"
                else "The water filter is due to be replaced.",
                level="active",
            )

    async def _async_dishwasher(self, needs_cleaning: bool) -> None:
        if not needs_cleaning:
            if self._alerted is not None:
                self._alerted = None
                if self.coordinator.devices:
                    await async_clear_tag(self.hass, self.coordinator, self.tag)
            return
        if self._alerted is not None:
            return
        self._alerted = "clean"
        if self.coordinator.devices:
            await async_send_alert(
                self.hass,
                self.coordinator,
                tag=self.tag,
                title=f"🧽 {self.coordinator.name}: clean the filter",
                message="The dishwasher says its filter needs cleaning.",
                level="active",
            )


class FridgeMonitor(_Base):
    """Fridge / freezer temperature limits and the ice bucket."""

    def __init__(
        self,
        hass,
        coordinator,
        *,
        zones: dict[str, tuple[str, float]],
        warm_minutes: float,
        ice_entity: str | None,
    ):
        super().__init__(
            hass, coordinator, [e for e, _ in zones.values()] + ([ice_entity] if ice_entity else [])
        )
        self.zones = zones
        self.warm_after = warm_minutes * 60
        self.ice_entity = ice_entity
        self._warm_since: dict[str, float] = {}
        self._warm_alert: dict[str, float] = {}
        self._ice_alerted = False

    def _temp(self, entity_id: str) -> tuple[float | None, str]:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None, ""
        try:
            return float(state.state), state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or "°"
        except ValueError:
            return None, ""

    @property
    def too_warm(self) -> list[str]:
        return sorted(self._warm_alert)

    async def async_evaluate(self) -> None:
        now = dt_util.utcnow().timestamp()
        for zone, (entity_id, limit) in self.zones.items():
            temp, unit = self._temp(entity_id)
            if temp is None:
                continue  # unavailable (e.g. a power cut): keep the current state
            tag = f"{self.coordinator.notification_tag}_{zone}_warm"
            label = "Fridge" if zone == "fridge" else "Freezer"
            if temp <= limit:
                self._warm_since.pop(zone, None)
                if self._warm_alert.pop(zone, None) is not None and self.coordinator.devices:
                    await async_send_alert(
                        self.hass,
                        self.coordinator,
                        tag=tag,
                        title=f"✅ {self.coordinator.name}: {label.lower()} back to {round(temp)}{unit}",
                        message=f"The {label.lower()} is cold again.",
                        level="active",
                        deferrable=False,
                    )
                    self.coordinator.async_update_listeners()
                continue
            since = self._warm_since.setdefault(zone, now)
            if now - since < self.warm_after:
                continue
            last = self._warm_alert.get(zone)
            if last is not None and now - last < WARM_REPEAT_MINUTES * 60 - 1:
                continue
            self._warm_alert[zone] = now
            minutes = round((now - since) / 60)
            _LOGGER.warning("%s: %s at %s for %s min", self.coordinator.name, zone, temp, minutes)
            if self.coordinator.devices:
                await async_send_alert(
                    self.hass,
                    self.coordinator,
                    tag=tag,
                    title=f"🌡️ {self.coordinator.name}: {label.lower()} too warm",
                    message=f"The {label.lower()} has been at {round(temp)}{unit} for {minutes} min "
                    f"(limit {round(limit)}{unit}). Check the door and the power.",
                    level="critical",
                )
            self.coordinator.async_update_listeners()

        if self.ice_entity:
            state = self.hass.states.get(self.ice_entity)
            text = state.state.strip().lower() if state else ""
            if text in UNAVAILABLE_STATES or text == "n/a":
                return
            full = text in ("full", "on", "true")
            tag = f"{self.coordinator.notification_tag}_ice"
            if full and not self._ice_alerted:
                self._ice_alerted = True
                if self.coordinator.devices:
                    await async_send_alert(
                        self.hass,
                        self.coordinator,
                        tag=tag,
                        title=f"🧊 {self.coordinator.name}: ice bucket full",
                        message="The ice bucket is full.",
                        level="passive",
                    )
            elif not full and self._ice_alerted:
                self._ice_alerted = False
                if self.coordinator.devices:
                    await async_clear_tag(self.hass, self.coordinator, tag)
