"""Turns coordinator decisions into notify.* service calls.

Payload keys follow the Companion app's Live Activities / Live Updates docs:
https://companion.home-assistant.io/docs/notifications/live-activities/

- ``live_update: true`` + ``tag`` start or update the activity
- ``chronometer`` + ``when`` + ``when_relative`` let the phone run the
  countdown itself, so we don't need (and iOS won't accept) a push per minute
- ``message: clear_notification`` with the same ``tag`` ends it
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify

if TYPE_CHECKING:
    from .coordinator import ApplianceCoordinator

_LOGGER = logging.getLogger(__name__)

NOTIFY = "notify"


def notify_services_for_device(hass: HomeAssistant, device_id: str) -> list[str]:
    """Return notify service names (without the 'notify.' prefix) for a phone.

    The Companion app registers a legacy service ``notify.mobile_app_<device
    name>``; it does not create notify *entities*, so look the service up by
    the device's name (and also accept any notify entity-backed service, in
    case a future app version adds one).
    """
    services: list[str] = []
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        for name in (device.name, device.name_by_user):
            if name:
                candidate = f"mobile_app_{slugify(name)}"
                if hass.services.has_service(NOTIFY, candidate) and candidate not in services:
                    services.append(candidate)

    ent_reg = er.async_get(hass)
    for entry in er.async_entries_for_device(ent_reg, device_id):
        if entry.domain == NOTIFY:
            candidate = entry.entity_id.split(".", 1)[1]
            if hass.services.has_service(NOTIFY, candidate) and candidate not in services:
                services.append(candidate)

    if not services:
        _LOGGER.warning(
            "No notify.mobile_app_* service found for device %s (%s). If the phone "
            "was renamed after it registered, check Developer Tools > Actions",
            device_id,
            device.name if device else "unknown device",
        )
    return services


async def _async_send(
    hass: HomeAssistant,
    coordinator: ApplianceCoordinator,
    payload: dict[str, Any],
    devices: list[str] | None = None,
) -> None:
    targets = list(dict.fromkeys(coordinator.devices if devices is None else devices))
    for device_id in targets:
        for service in notify_services_for_device(hass, device_id):
            try:
                await hass.services.async_call(NOTIFY, service, payload, blocking=False)
            except Exception:  # noqa: BLE001 - one bad phone must not stop the others
                _LOGGER.exception("Failed to send notification via notify.%s", service)


def _join(*parts: str) -> str:
    return " · ".join(p for p in parts if p)


async def async_send_progress(
    hass: HomeAssistant,
    coordinator: ApplianceCoordinator,
    *,
    paused: bool,
    phase: str,
    cycle: str,
    temperature: str,
    remaining: float,
    progress: int | None,
) -> None:
    """Start or update the Live Activity for a running / paused appliance."""
    definition = coordinator.definition
    headline = definition.paused_message if paused else (phase or definition.running_message)
    minutes_left = round(remaining)
    message = _join(
        headline,
        cycle,
        temperature,
        f"{minutes_left} min left" if minutes_left > 0 else "",
    )
    data: dict[str, Any] = {
        "tag": coordinator.notification_tag,
        "live_update": True,
        "critical_text": headline,
        "notification_icon": "mdi:pause-circle" if paused else coordinator.icon,
        "notification_icon_color": coordinator.icon_color,
        # Android
        "color": coordinator.icon_color,
    }
    if progress is not None:
        data["progress"] = progress
        data["progress_max"] = 100
    if not paused and remaining > 0:
        data["chronometer"] = True
        data["when"] = int(remaining * 60)
        data["when_relative"] = True
    await _async_send(
        hass, coordinator, {"title": coordinator.name, "message": message, "data": data}
    )


async def async_send_done(hass: HomeAssistant, coordinator: ApplianceCoordinator, cycle: str) -> None:
    """Switch the Live Activity to its finished state."""
    data: dict[str, Any] = {
        "tag": coordinator.notification_tag,
        "live_update": True,
        "critical_text": "Done",
        "notification_icon": "mdi:check-circle",
        "notification_icon_color": "#4CAF50",
        "color": "#4CAF50",
    }
    if coordinator.definition.supports_progress:
        data["progress"] = 100
        data["progress_max"] = 100
    await _async_send(
        hass,
        coordinator,
        {
            "title": coordinator.name,
            "message": _join(coordinator.definition.complete_message, cycle),
            "data": data,
        },
    )


async def async_send_finished_alert(hass: HomeAssistant, coordinator: ApplianceCoordinator) -> None:
    """A regular, time-sensitive alert -- a Live Activity update doesn't always alert."""
    await _async_send(
        hass,
        coordinator,
        {
            "title": f"✅ {coordinator.name} finished",
            "message": coordinator.definition.finished_alert_message,
            "data": {
                "tag": f"{coordinator.notification_tag}_done",
                "push": {"interruption-level": "time-sensitive"},
                "ttl": 0,
                "priority": "high",
            },
        },
    )


async def async_clear(hass: HomeAssistant, coordinator: ApplianceCoordinator) -> None:
    """End the Live Activity."""
    await _async_send(
        hass,
        coordinator,
        {"message": "clear_notification", "data": {"tag": coordinator.notification_tag}},
    )


# ----------------------------------------------------------------------
# Door monitoring (refrigerator / freezer)
# ----------------------------------------------------------------------
def _door_text(labels: list[str]) -> str:
    if not labels:
        return "Door"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " & " + labels[-1]


async def async_send_door_open(
    hass: HomeAssistant,
    coordinator: ApplianceCoordinator,
    *,
    labels: list[str],
    opened_at: float,
    critical: bool,
) -> None:
    """Live Activity counting up from when the door opened."""
    doors = _door_text(labels)
    color = "#F44336" if critical else coordinator.icon_color
    data: dict[str, Any] = {
        "tag": coordinator.notification_tag,
        "live_update": True,
        "critical_text": "Still open" if critical else "Open",
        "notification_icon": "mdi:fridge-alert" if critical else "mdi:door-open",
        "notification_icon_color": color,
        "color": color,
        # Count up from the moment the door opened
        "chronometer": True,
        "when": int(opened_at),
    }
    await _async_send(
        hass,
        coordinator,
        {
            "title": coordinator.name,
            "message": f"{doors} {'are' if len(labels) > 1 else 'is'} open",
            "data": data,
        },
    )


async def async_send_door_critical(
    hass: HomeAssistant,
    coordinator: ApplianceCoordinator,
    *,
    labels: list[str],
    minutes_open: int,
    devices: list[str] | None = None,
) -> None:
    """Critical alert (bypasses Silent / Focus on iOS, alarm stream on Android)."""
    doors = _door_text(labels)
    await _async_send(
        hass,
        coordinator,
        {
            "title": f"🚨 {coordinator.name}: {doors} open",
            "message": f"Open for {minutes_open} min — please close it.",
            "data": {
                "tag": f"{coordinator.notification_tag}_critical",
                "push": {
                    "interruption-level": "critical",
                    "sound": {"name": "default", "critical": 1, "volume": 1.0},
                },
                "ttl": 0,
                "priority": "high",
                "channel": "alarm_stream",
            },
        },
        devices,
    )


async def async_send_door_closed(
    hass: HomeAssistant, coordinator: ApplianceCoordinator, *, minutes_open: int
) -> None:
    """Show 'Closed' on the Live Activity (it is ended a minute later)."""
    await _async_send(
        hass,
        coordinator,
        {
            "title": coordinator.name,
            "message": f"Closed · was open {minutes_open} min" if minutes_open else "Closed",
            "data": {
                "tag": coordinator.notification_tag,
                "live_update": True,
                "critical_text": "Closed",
                "notification_icon": "mdi:check-circle",
                "notification_icon_color": "#4CAF50",
                "color": "#4CAF50",
            },
        },
    )


async def async_clear_tag(
    hass: HomeAssistant, coordinator: ApplianceCoordinator, tag: str, devices: list[str] | None = None
) -> None:
    """Remove a notification by tag."""
    await _async_send(
        hass, coordinator, {"message": "clear_notification", "data": {"tag": tag}}, devices
    )


# ----------------------------------------------------------------------
# Cooktop left on
# ----------------------------------------------------------------------
async def async_send_cooktop_critical(
    hass: HomeAssistant,
    coordinator: ApplianceCoordinator,
    *,
    tag: str,
    minutes_on: int,
    acknowledge_action: str | None,
) -> None:
    """Critical 'cooktop still on' alert with an optional Acknowledge button."""
    data: dict[str, Any] = {
        "tag": tag,
        "push": {
            "interruption-level": "critical",
            "sound": {"name": "default", "critical": 1, "volume": 1.0},
        },
        "ttl": 0,
        "priority": "high",
        "channel": "alarm_stream",
    }
    if acknowledge_action:
        data["actions"] = [{"action": acknowledge_action, "title": "Acknowledge"}]
    await _async_send(
        hass,
        coordinator,
        {
            "title": "🔥 Cooktop still on",
            "message": f"{coordinator.name}: the cooktop has been on for {minutes_on} min. "
            "Please check it.",
            "data": data,
        },
    )


# ----------------------------------------------------------------------
# Speaker announcements
# ----------------------------------------------------------------------
async def async_speak(
    hass: HomeAssistant, tts_entity: str | None, speakers: list[str], message: str
) -> None:
    """Announce on speakers via a TTS entity (no-op if not configured)."""
    if not tts_entity or not speakers:
        return
    try:
        await hass.services.async_call(
            "tts",
            "speak",
            {"media_player_entity_id": speakers, "message": message},
            target={"entity_id": tts_entity},
            blocking=False,
        )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("TTS announcement failed")
