"""Settings -> Repairs: problems that otherwise only show up in the log.

* A phone that no longer has a ``notify.mobile_app_*`` service (renamed in
  the Companion app, or removed) -- its alerts silently go nowhere.
* Sensors this appliance uses that no longer exist (deleted or renamed).

Checked a few minutes after start (so other integrations have loaded) and
then every 30 minutes; issues disappear by themselves once fixed.
"""
from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import DOMAIN, HEALTH_CHECK_MINUTES, HEALTH_FIRST_CHECK_SECONDS
from .notify import notify_services_for_device

if TYPE_CHECKING:
    from .coordinator import ApplianceCoordinator


def _phone_issue(entry_id: str, device_id: str) -> str:
    return f"phone_{entry_id}_{device_id}"


def _entities_issue(entry_id: str) -> str:
    return f"missing_entities_{entry_id}"


@callback
def async_setup_health(hass: HomeAssistant, coordinator: ApplianceCoordinator) -> list:
    """Schedule the checks; returns unsubscribe callbacks."""

    @callback
    def _run(_now=None) -> None:
        async_check_health(hass, coordinator)

    return [
        async_call_later(hass, HEALTH_FIRST_CHECK_SECONDS, _run),
        async_track_time_interval(hass, _run, timedelta(minutes=HEALTH_CHECK_MINUTES)),
    ]


@callback
def async_check_health(hass: HomeAssistant, coordinator: ApplianceCoordinator) -> None:
    entry_id = coordinator.entry.entry_id
    dev_reg = dr.async_get(hass)

    phones = list(dict.fromkeys(coordinator.devices + list(getattr(coordinator, "escalation_devices", []) or [])))
    for device_id in phones:
        issue_id = _phone_issue(entry_id, device_id)
        if notify_services_for_device(hass, device_id, warn=False):
            ir.async_delete_issue(hass, DOMAIN, issue_id)
            continue
        device = dev_reg.async_get(device_id)
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="phone_not_found",
            translation_placeholders={
                "phone": (device.name_by_user or device.name) if device else device_id,
                "appliance": coordinator.name,
            },
        )

    ent_reg = er.async_get(hass)
    missing = [
        entity_id
        for entity_id in coordinator.configured_entities()
        if hass.states.get(entity_id) is None and ent_reg.async_get(entity_id) is None
    ]
    if missing:
        ir.async_create_issue(
            hass,
            DOMAIN,
            _entities_issue(entry_id),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_entities",
            translation_placeholders={
                "appliance": coordinator.name,
                "entities": ", ".join(missing),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, _entities_issue(entry_id))


@callback
def async_remove_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The appliance was deleted: its issues go too."""
    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN and entry.entry_id in issue_id:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
