"""Turns coordinator state changes into notify.* service calls.

This is where the actual Live Activity payload (tag, live_update,
progress, critical_text, notification_icon...) gets built, matching the
fields the original blueprint sent to the iOS Companion App.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import STATUS_COMPLETE, STATUS_PAUSED, STATUS_RUNNING

if TYPE_CHECKING:
    from .coordinator import ApplianceCoordinator

_LOGGER = logging.getLogger(__name__)


def _notify_services_for_device(hass: HomeAssistant, device_id: str) -> list[str]:
    """Find notify.* service names (e.g. 'mobile_app_johns_iphone') for a device."""
    ent_reg = er.async_get(hass)
    return [
        entity.entity_id.split(".", 1)[-1]
        for entity in er.async_entries_for_device(ent_reg, device_id)
        if entity.domain == "notify"
    ]


async def _async_call_notify(
    hass: HomeAssistant, service_name: str, title: str, message: str, data: dict
) -> None:
    if not hass.services.has_service("notify", service_name):
        _LOGGER.warning(
            "notify.%s not found (device may not support notifications); skipping", service_name
        )
        return
    await hass.services.async_call(
        "notify",
        service_name,
        {"title": title, "message": message, "data": data},
        blocking=False,
    )


async def async_send_live_activity(
    hass: HomeAssistant,
    coordinator: "ApplianceCoordinator",
    status: str,
    phase: str,
    cycle: str,
    remaining: int,
    progress: int,
) -> None:
    """Build and send the appropriate notification payload for the current status."""
    if not coordinator.devices:
        return

    if status == STATUS_RUNNING:
        parts = [phase]
        if cycle:
            parts.append(cycle)
        if remaining:
            parts.append(f"{remaining} min remaining")
        message = " · ".join(p for p in parts if p)
        data = {
            "tag": coordinator.notification_tag,
            "live_update": True,
            "critical_text": phase,
            "progress": progress,
            "progress_max": 100,
            "notification_icon": coordinator.icon,
            "notification_icon_color": coordinator.icon_color,
        }
    elif status == STATUS_PAUSED:
        parts = [coordinator.definition.paused_message]
        if cycle:
            parts.append(cycle)
        message = " · ".join(p for p in parts if p)
        data = {
            "tag": coordinator.notification_tag,
            "live_update": True,
            "critical_text": coordinator.definition.paused_message,
            "notification_icon": "mdi:pause-circle",
            "notification_icon_color": coordinator.icon_color,
        }
    elif status == STATUS_COMPLETE:
        parts = [coordinator.definition.complete_message]
        if cycle:
            parts.append(cycle)
        message = " · ".join(p for p in parts if p)
        data = {
            "tag": coordinator.notification_tag,
            "live_update": True,
            "critical_text": "Done",
            "progress": 100,
            "progress_max": 100,
            "notification_icon": "mdi:check-circle",
            "notification_icon_color": "#4CAF50",
        }
    else:
        return

    for device_id in coordinator.devices:
        for service_name in _notify_services_for_device(hass, device_id):
            await _async_call_notify(hass, service_name, coordinator.name, message, data)
