"""Moving from Appliance Live Activity (``appliance_live_activity``) in 2.0.0.

The integration's domain changed with the repository's name. Home Assistant
keeps config entries, entities, devices and storage under the domain, so on
the first start of 2.0.0 everything the old domain had is moved across:

1. ``async_setup`` (``async_start``) finds the old domain's config entries.
   If the old integration's folder is still installed, nothing is moved: its
   code would load the same appliances again. A repair asks to remove the
   folder (its fix does it) and restart.
2. Otherwise each old entry is re-created through the ``import`` step of the
   config flow, with the same title, unique id, data and options, plus
   ``migrated_from`` (the old entry id).
3. That entry's setup (``async_before_setup``, before the coordinator loads
   its storage) copies the old entry's stored cycle state and picture.
4. After our device exists (``async_after_link``), every entity of the old
   entry moves to this entry with ``async_update_entity_platform``. Entity
   ids stay, and with them history, statistics, dashboards and automations
   that use them. Unique ids (``<entry id>_<key>``) get the new entry id. The
   name and area set on the old device are copied to the new one. The old
   entry is then removed, which removes its leftover device.

Automations that call ``appliance_live_activity.update`` need the new action
name, ``appliance_mgmt.update``; the release notes say so.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

OLD_DOMAIN = "appliance_live_activity"
MIGRATED_FROM = "migrated_from"
ISSUE_OLD_FOLDER = "old_folder"


def old_folder(hass: HomeAssistant) -> Path:
    return Path(hass.config.path("custom_components", OLD_DOMAIN))


def old_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    return hass.config_entries.async_entries(OLD_DOMAIN)


async def async_start(hass: HomeAssistant) -> None:
    """Move the old domain's appliances across, or ask for the old folder to go."""
    folder_there = await hass.async_add_executor_job(old_folder(hass).is_dir)
    if folder_there:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_OLD_FOLDER,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_OLD_FOLDER,
            translation_placeholders={"folder": f"custom_components/{OLD_DOMAIN}"},
        )
        return
    ir.async_delete_issue(hass, DOMAIN, ISSUE_OLD_FOLDER)
    moved = {
        entry.data.get(MIGRATED_FROM)
        for entry in hass.config_entries.async_entries(DOMAIN)
    }
    for old in old_entries(hass):
        if old.entry_id in moved:
            continue  # created already; its setup finishes the move
        # Not awaited: the new entry sets up as part of this integration,
        # which is still in async_setup.
        hass.async_create_background_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data={MIGRATED_FROM: old.entry_id},
            ),
            f"{DOMAIN} move {old.entry_id}",
        )


def import_entry(hass: HomeAssistant, old_entry_id: str) -> ConfigEntry | None:
    """The old entry an import flow re-creates."""
    entry = hass.config_entries.async_get_entry(old_entry_id)
    return entry if entry is not None and entry.domain == OLD_DOMAIN else None


async def async_before_setup(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Copy the old entry's stored state before the coordinator loads it."""
    old_id = entry.data.get(MIGRATED_FROM)
    if not old_id or import_entry(hass, old_id) is None:
        return
    old_store: Store[dict[str, Any]] = Store(
        hass, STORAGE_VERSION, f"{OLD_DOMAIN}_{old_id}"
    )
    new_store: Store[dict[str, Any]] = Store(
        hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}"
    )
    if (data := await old_store.async_load()) is not None and (
        await new_store.async_load()
    ) is None:
        await new_store.async_save(data)
    old_images: Store[dict[str, Any]] = Store(hass, 1, f"{OLD_DOMAIN}.images")
    image = ((await old_images.async_load() or {}).get("images") or {}).get(old_id)
    if image:
        from .panel import DATA_IMAGES  # noqa: PLC0415

        images = hass.data.get(DATA_IMAGES)
        if images is not None and entry.entry_id not in images.images:
            await images.async_set(entry.entry_id, image)


async def async_after_link(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move the old entry's entities and device settings, then remove it."""
    old_id = entry.data.get(MIGRATED_FROM)
    if not old_id:
        return
    old = import_entry(hass, old_id)
    if old is not None:
        _move_entities(hass, entry, old_id)
        await hass.config_entries.async_remove(old_id)
        _LOGGER.info("Moved %s from Appliance Live Activity", entry.title)
    data = {k: v for k, v in entry.data.items() if k != MIGRATED_FROM}
    hass.config_entries.async_update_entry(entry, data=data)


def _move_entities(hass: HomeAssistant, entry: ConfigEntry, old_id: str) -> None:
    from .device import own_device  # noqa: PLC0415

    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    old_device = dev_reg.async_get_device_by_identifier((OLD_DOMAIN, old_id), old_id)
    new_device = own_device(hass, entry)
    if old_device is not None and new_device is not None:
        changes: dict[str, Any] = {}
        if old_device.name_by_user:
            changes["name_by_user"] = old_device.name_by_user
        if old_device.area_id:
            changes["area_id"] = old_device.area_id
        if changes:
            dev_reg.async_update_device(new_device.id, **changes)
    for old_entity in er.async_entries_for_config_entry(ent_reg, old_id):
        unique_id = old_entity.unique_id
        if unique_id.startswith(f"{old_id}_"):
            unique_id = f"{entry.entry_id}_{unique_id[len(old_id) + 1 :]}"
        device_id = old_entity.device_id
        if old_device is not None and device_id == old_device.id:
            device_id = new_device.id if new_device is not None else None
        try:
            ent_reg.async_update_entity_platform(
                old_entity.entity_id,
                DOMAIN,
                new_config_entry_id=entry.entry_id,
                new_unique_id=unique_id,
                new_device_id=device_id,
            )
        except ValueError:
            _LOGGER.warning("Couldn't move %s", old_entity.entity_id, exc_info=True)


async def async_remove_old_folder(hass: HomeAssistant) -> None:
    """The repair's fix: delete the old integration's folder."""
    folder = old_folder(hass)
    await hass.async_add_executor_job(
        lambda: shutil.rmtree(folder) if folder.is_dir() else None
    )
