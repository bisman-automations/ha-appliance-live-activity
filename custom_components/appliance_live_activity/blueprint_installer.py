"""Install / update the bundled blueprints.

Blueprints shipped in ``custom_components/appliance_live_activity/blueprints``
are copied to ``<config>/blueprints/automation/appliance_live_activity/`` so
people who install the integration also get the GE blueprint.

A copy is only (re)written when it is missing, or when it is still exactly
the version this integration installed last time. If the user edited it,
it is left alone.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

BUNDLED_DIR = Path(__file__).parent / "blueprints"
STORE_KEY = f"{DOMAIN}_blueprints"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sync(target_dir: Path, installed: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Copy bundled blueprints; return (new installed hashes, changed files)."""
    changed: list[str] = []
    result = dict(installed)
    if not BUNDLED_DIR.is_dir():
        return result, changed
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(BUNDLED_DIR.glob("*.yaml")):
        target = target_dir / source.name
        bundled_hash = _sha(source)
        if target.exists():
            current_hash = _sha(target)
            if current_hash == bundled_hash:
                result[source.name] = bundled_hash
                continue
            if installed.get(source.name) != current_hash:
                _LOGGER.info(
                    "Not updating %s: it was modified after installation", target
                )
                continue
        shutil.copyfile(source, target)
        result[source.name] = bundled_hash
        changed.append(source.name)
    return result, changed


async def async_install_blueprints(hass: HomeAssistant) -> None:
    """Install or update bundled blueprints (never overwrites user edits)."""
    store: Store[dict[str, str]] = Store(hass, 1, STORE_KEY)
    installed = await store.async_load() or {}
    target_dir = Path(hass.config.path("blueprints", "automation", DOMAIN))
    try:
        new_installed, changed = await hass.async_add_executor_job(_sync, target_dir, installed)
    except OSError as err:
        _LOGGER.warning("Could not install bundled blueprints: %s", err)
        return
    if new_installed != installed:
        await store.async_save(new_installed)
    if changed:
        _LOGGER.info("Installed/updated blueprints: %s", ", ".join(changed))
        if hass.services.has_service("automation", "reload"):
            # Lets existing automations pick up an updated blueprint
            await hass.services.async_call("automation", "reload", blocking=False)
