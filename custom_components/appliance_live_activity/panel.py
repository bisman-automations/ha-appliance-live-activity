"""The Appliances sidebar dashboard.

Registered once from ``async_setup`` for the whole Home Assistant run — not
once per config entry, and not removed when the last appliance unloads.
Home Assistant raises ``ValueError: Overwriting panel appliances owned by
custom`` if the same panel is registered again, which used to abort setup of
every appliance after the first. Removing it with the last entry (1.14.1)
then left the page missing after a reload, because nothing registered it a
second time.

The panel reads live states (Status, Time Left, …) from the frontend's own
connection. This module adds what states don't carry: which entities belong
to which appliance, recent cycles, maintenance alerts and each appliance's
picture. The websocket command lists every appliance that is set up, not the
entry that happened to register the page.

Pictures are uploaded with Home Assistant's own image upload (the same one
person pictures use); only the uploaded image's id is stored here.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, DOOR_TYPES

_LOGGER = logging.getLogger(__name__)

PANEL_URL_PATH = "appliances"
PANEL_COMPONENT = "appliance-live-activity-panel"
PANEL_TITLE = "Appliances"
PANEL_ICON = "mdi:washing-machine"
STATIC_URL = f"/{DOMAIN}_static"
FRONTEND_DIR = Path(__file__).parent / "frontend"
# True once this run has claimed the sidebar panel. Set before the await so
# a second caller cannot register it too.
DATA_PANEL = f"{DOMAIN}_panel"
# True once the panel's JavaScript path is registered. Independent of
# DATA_PANEL so a failed panel registration can be retried without
# registering the same static path twice.
DATA_STATIC = f"{DOMAIN}_static"
# True once the websocket commands are registered for this run.
DATA_API = f"{DOMAIN}_panel_api"
DATA_IMAGES = f"{DOMAIN}_images"
IMAGES_STORE = f"{DOMAIN}.images"
RECENT_CYCLES = 10

# Our entities, by the key in their unique id (``<entry_id>_<key>``).
ENTITY_KEYS = {
    "status": "sensor",
    "progress": "sensor",
    "time_left": "sensor",
    "finishes_at": "sensor",
    "cycles_week": "sensor",
    "average_cycle": "sensor",
    "power": "switch",
    "event": "event",
    "update_live_activity": "button",
    "probe_target": "number",
}


class ImageStore:
    """Each appliance's uploaded picture: config entry id -> image id."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, 1, IMAGES_STORE)
        self.images: dict[str, str] = {}

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self.images = {
            k: v
            for k, v in (stored.get("images") or {}).items()
            if isinstance(k, str) and isinstance(v, str)
        }

    async def async_set(self, entry_id: str, image_id: str | None) -> None:
        if image_id:
            self.images[entry_id] = image_id
        else:
            self.images.pop(entry_id, None)
        await self._store.async_save({"images": self.images})


async def async_setup_panel_backend(hass: HomeAssistant) -> None:
    """Load the pictures and register the websocket commands, once per run.

    ``websocket_api.async_register_command`` raises if the same command is
    registered again, so a second call (a retried ``async_setup``) must not
    reach it. The claim is synchronous, before the storage load, so two
    callers cannot both pass the check.
    """
    if hass.data.get(DATA_API):
        return
    hass.data[DATA_API] = True
    try:
        images = ImageStore(hass)
        await images.async_load()
    except Exception:
        # Leave the commands unregistered and let a retry start over.
        hass.data[DATA_API] = False
        raise
    hass.data[DATA_IMAGES] = images
    websocket_api.async_register_command(hass, websocket_appliances)
    websocket_api.async_register_command(hass, websocket_set_image)


def _panel_already_registered(err: BaseException) -> bool:
    """Home Assistant's error when this panel is already in the sidebar."""
    return isinstance(err, ValueError) and "Overwriting panel" in str(err)


async def async_register_panel(hass: HomeAssistant, version: str | None) -> None:
    """Show the Appliances panel in the sidebar, once per Home Assistant run.

    Called from ``async_setup``. The panel stays for the whole run, including
    after the last appliance is removed, and shows an empty state then. It is
    not registered from ``async_setup_entry``: doing that once per appliance
    raises, and only the first appliance loads.

    No-op when this run already registered it. No-op without a frontend
    (tests, or a headless setup); the flag is left unset so a later call can
    still register. An "already registered" error from Home Assistant is the
    outcome we want and is not raised — a failed or repeated setup must not
    take the integration down or hide the other appliances.
    """
    if hass.data.get(DATA_PANEL):
        return
    if "frontend" not in hass.config.components or hass.http is None:
        _LOGGER.debug("Frontend not loaded; skipping the Appliances panel")
        return

    # Claim before the first await. Check and set are synchronous, so a
    # second task cannot pass the check above while this one is waiting.
    hass.data[DATA_PANEL] = True
    try:
        await _async_register_panel_and_static(hass, version)
    except Exception as err:
        if _panel_already_registered(err):
            _LOGGER.debug("Appliances panel is already registered: %s", err)
            return
        # Static path may already be recorded. Clearing only the panel claim
        # lets a retry register the panel without registering the path twice.
        hass.data[DATA_PANEL] = False
        raise


async def _async_register_panel_and_static(
    hass: HomeAssistant, version: str | None
) -> None:
    """Register the script path, then the sidebar panel."""
    from homeassistant.components import panel_custom  # noqa: PLC0415
    from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

    if not hass.data.get(DATA_STATIC):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(STATIC_URL, str(FRONTEND_DIR), cache_headers=False)]
        )
        hass.data[DATA_STATIC] = True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        # The version busts the browser cache after an update.
        module_url=f"{STATIC_URL}/appliance-live-activity-panel.js?v={version or 'dev'}",
        require_admin=False,
        config={},
    )


def image_url(image_id: str | None) -> str | None:
    """Where Home Assistant serves an uploaded picture."""
    return f"/api/image/serve/{image_id}/512x512" if image_id else None


def _alerts(coordinator) -> list[str]:
    """Maintenance problems that states alone don't show."""
    from .maintenance import CLEAN_FILTER_STATES  # noqa: PLC0415

    alerts: list[str] = []
    supplies = getattr(coordinator, "supplies", None)
    if supplies is not None:
        alerts += [text for _entity_id, text in supplies.low_supplies()]
    filter_monitor = getattr(coordinator, "filter", None)
    if filter_monitor is not None:
        status = filter_monitor.status
        if coordinator.appliance_type == "dishwasher":
            if status in CLEAN_FILTER_STATES:
                alerts.append("Filter needs cleaning")
        elif text := {
            "replace": "Replace the water filter",
            "expired": "The water filter has expired",
            "leak detected": "The water filter reports a leak",
        }.get(status):
            alerts.append(text)
    fridge = getattr(coordinator, "fridge", None)
    if fridge is not None:
        alerts += [f"{zone.capitalize()} is too warm" for zone in fridge.too_warm]
    return alerts


@callback
def appliance_summary(hass: HomeAssistant, entry) -> dict[str, Any]:
    """Everything the panel needs about one appliance."""
    from .device import appliance_device_id, own_device  # noqa: PLC0415

    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    entities = {
        key: entity_id
        for key, platform in ENTITY_KEYS.items()
        if (
            entity_id := registry.async_get_entity_id(
                platform, DOMAIN, f"{entry.entry_id}_{key}"
            )
        )
    }
    images: ImageStore | None = hass.data.get(DATA_IMAGES)
    own = own_device(hass, entry)
    fridge = getattr(coordinator, "fridge", None)
    try:
        alerts = _alerts(coordinator)
    except Exception:  # a monitor must never break the dashboard
        _LOGGER.exception("Couldn't read %s's maintenance alerts", coordinator.name)
        alerts = []
    history = list(getattr(coordinator, "_history", []))[-RECENT_CYCLES:]
    return {
        "entry_id": entry.entry_id,
        "name": coordinator.display_title,
        "type": coordinator.appliance_type,
        "type_name": coordinator.definition.display_name,
        "door": coordinator.appliance_type in DOOR_TYPES,
        "icon": coordinator.icon,
        "color": coordinator.icon_color,
        "image": image_url(images.images.get(entry.entry_id) if images else None),
        "image_id": images.images.get(entry.entry_id) if images else None,
        "link": coordinator.tap_path(),
        "device_id": own.id if own else None,
        "appliance_device_id": appliance_device_id(hass, coordinator),
        "entities": entities,
        "temperatures": (
            [
                {"zone": zone, "entity_id": entity_id, "limit": limit}
                for zone, (entity_id, limit) in fridge.zones.items()
            ]
            if fridge is not None
            else []
        ),
        "alerts": alerts,
        # Newest first: when each cycle finished and how long it ran.
        "recent_cycles": [
            {
                "finished": dt_util.utc_from_timestamp(finished).isoformat(),
                "minutes": minutes,
            }
            for finished, minutes in reversed(history)
        ],
    }


def dashboard_appliances(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Every appliance that is set up, for the dashboard.

    The sidebar page is registered once for the whole run, so this is every
    loaded config entry — whichever entry was set up first does not own the
    list. An entry that failed setup has no coordinator and is left out. One
    appliance whose summary raises is skipped so the others still show.
    """
    summaries: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is not ConfigEntryState.LOADED:
            continue
        try:
            summaries.append(appliance_summary(hass, entry))
        except Exception:
            _LOGGER.exception(
                "Couldn't describe %s for the Appliances dashboard",
                getattr(entry, "title", None) or entry.entry_id,
            )
    return summaries


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/appliances"})
@callback
def websocket_appliances(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Every set-up appliance, for the dashboard."""
    connection.send_result(
        msg["id"],
        {
            "appliances": dashboard_appliances(hass),
            "is_admin": connection.user.is_admin if connection.user else False,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/image",
        vol.Required("entry_id"): str,
        vol.Optional("image_id"): vol.Any(str, None),
    }
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_set_image(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Set or clear an appliance's picture (an uploaded image's id)."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "No such appliance")
        return
    images: ImageStore = hass.data[DATA_IMAGES]
    previous = images.images.get(entry.entry_id)
    await images.async_set(entry.entry_id, msg.get("image_id"))
    connection.send_result(
        msg["id"],
        {"image": image_url(msg.get("image_id")), "previous_image_id": previous},
    )
