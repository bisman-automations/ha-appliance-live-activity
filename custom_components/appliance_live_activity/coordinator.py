"""Data coordinator for a single configured appliance.

This replaces the Jinja logic that used to live inside every copy of the
blueprint (progress calculation, total-cycle capture, pause handling,
completion handling) with one generic implementation that reads its
per-appliance defaults from ApplianceDefinition (see appliance.py).
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
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
    CONF_ICON,
    CONF_ICON_COLOR,
    CONF_NAME,
    CONF_NOTIFICATION_TAG,
    CONF_PAUSE_STATES,
    CONF_PHASE_ENTITY,
    CONF_REMAINING_ENTITY,
    CONF_STATE_ENTITY,
    DOMAIN,
    STATUS_COMPLETE,
    STATUS_IDLE,
    STATUS_PAUSED,
    STATUS_RUNNING,
    STORAGE_VERSION,
)
from .notify import async_send_live_activity

_LOGGER = logging.getLogger(__name__)


class ApplianceCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Tracks one appliance's state and drives its Live Activity notifications."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{entry.entry_id}", update_interval=None)
        self.hass = hass
        self.entry = entry

        cfg = {**entry.data, **entry.options}
        self.appliance_type: str = cfg[CONF_APPLIANCE_TYPE]
        self.definition = APPLIANCE_REGISTRY[self.appliance_type]

        self.name: str = cfg.get(CONF_NAME) or self.definition.display_name
        self.state_entity: str | None = cfg.get(CONF_STATE_ENTITY)
        self.cycle_entity: str | None = cfg.get(CONF_CYCLE_ENTITY) or None
        self.phase_entity: str | None = cfg.get(CONF_PHASE_ENTITY) or None
        self.remaining_entity: str | None = cfg.get(CONF_REMAINING_ENTITY) or None

        self.active_states: list[str] = cfg.get(CONF_ACTIVE_STATES) or self.definition.active_states
        self.pause_states: list[str] = cfg.get(CONF_PAUSE_STATES) or self.definition.pause_states
        self.complete_states: list[str] = cfg.get(CONF_COMPLETE_STATES) or self.definition.complete_states

        self.icon: str = cfg.get(CONF_ICON) or self.definition.icon
        self.icon_color: str = cfg.get(CONF_ICON_COLOR) or self.definition.color
        self.notification_tag: str = cfg.get(CONF_NOTIFICATION_TAG) or f"{DOMAIN}_{entry.entry_id}"
        self.devices: list[str] = cfg.get(CONF_DEVICES) or []

        # Total cycle length isn't exposed by most appliances directly (the
        # original blueprint used an input_number helper to remember it
        # across updates). We persist it ourselves via Store so it survives
        # HA restarts without the user having to create a helper entity.
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
        self._total_minutes: float = 0

        self._unsub_state = None
        self._unsub_timer = None

        self.data: dict[str, Any] = {
            "status": STATUS_IDLE,
            "phase": "",
            "cycle": "",
            "remaining": 0,
            "progress": 0,
        }

    async def async_setup(self) -> None:
        """Load persisted state and start listening for updates."""
        stored = await self._store.async_load()
        if stored:
            self._total_minutes = stored.get("total_minutes", 0)

        tracked_entities = [e for e in (self.state_entity, self.phase_entity) if e]
        if tracked_entities:
            self._unsub_state = async_track_state_change_event(
                self.hass, tracked_entities, self._handle_event
            )

        # Mirrors the blueprint's `time_pattern minutes: "/1"` trigger so the
        # remaining-time countdown keeps refreshing even if the source
        # sensor doesn't fire its own state_changed event every minute.
        self._unsub_timer = async_track_time_interval(
            self.hass, self._handle_event, timedelta(minutes=1)
        )

        await self._async_refresh(notify=False)

    async def async_unload(self) -> None:
        if self._unsub_state:
            self._unsub_state()
        if self._unsub_timer:
            self._unsub_timer()

    @callback
    def _handle_event(self, event=None) -> None:
        self.hass.async_create_task(self._async_refresh(notify=True))

    def _get_state(self, entity_id: str | None) -> str:
        if not entity_id:
            return ""
        state = self.hass.states.get(entity_id)
        return state.state if state else ""

    def _get_float(self, entity_id: str | None) -> float:
        if not entity_id:
            return 0.0
        state = self.hass.states.get(entity_id)
        if state is None:
            return 0.0
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return 0.0

    async def _async_refresh(self, notify: bool = True) -> None:
        appliance_state = self._get_state(self.state_entity)
        cycle = self._get_state(self.cycle_entity)
        phase = self._get_state(self.phase_entity) or appliance_state
        remaining = round(self._get_float(self.remaining_entity))

        if appliance_state in self.active_states:
            status = STATUS_RUNNING
        elif appliance_state in self.pause_states:
            status = STATUS_PAUSED
        elif appliance_state in self.complete_states:
            status = STATUS_COMPLETE
        else:
            status = STATUS_IDLE

        # Capture the starting cycle length exactly once per cycle, same as
        # the blueprint's input_number.set_value step -- then clear it once
        # the appliance goes idle/complete so the next cycle starts fresh.
        if status == STATUS_RUNNING and self._total_minutes == 0 and remaining > 0:
            self._total_minutes = remaining
            await self._async_save()
        elif status in (STATUS_IDLE, STATUS_COMPLETE) and self._total_minutes:
            self._total_minutes = 0
            await self._async_save()

        progress = 0
        if self.definition.supports_progress and self._total_minutes:
            progress = round((1 - (remaining / self._total_minutes)) * 100)
            progress = max(0, min(100, progress))

        self.data = {
            "status": status,
            "phase": phase,
            "cycle": cycle,
            "remaining": remaining,
            "progress": progress,
        }
        self.async_set_updated_data(self.data)

        if notify:
            await async_send_live_activity(self.hass, self, status, phase, cycle, remaining, progress)

    async def _async_save(self) -> None:
        await self._store.async_save({"total_minutes": self._total_minutes})
