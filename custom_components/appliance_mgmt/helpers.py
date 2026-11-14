"""Small shared helpers.

The state-classification functions are pure and unit tested. The two
schedulers at the bottom tie one-shot timers and background work to a
config entry so a reload cannot leave them running.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Iterable
from datetime import time, timedelta
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_call_later

from .const import (
    STATUS_COMPLETE,
    STATUS_IDLE,
    STATUS_PAUSED,
    STATUS_RUNNING,
    UNAVAILABLE_STATES,
)

# Values that mean "no meaningful text" for phase / cycle sensors
BLANK_TEXT = {"", "---", "n/a", "na", "none", "unknown", "unavailable", "off"}


def slugify_tag(value: str) -> str:
    """Turn a display name into a safe notification tag suffix."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _lower(values: Iterable[str]) -> list[str]:
    return [str(v).strip().lower() for v in values if str(v).strip()]


def classify_state(
    state: str,
    *,
    active: Iterable[str],
    paused: Iterable[str],
    complete: Iterable[str],
    idle: Iterable[str],
    unknown_is_running: bool = True,
    done_signal: bool = False,
) -> str:
    """Map a raw appliance state to idle / running / paused / complete.

    Order matters: an explicit end-of-cycle signal wins, then complete and
    pause keywords (substring match), then the exact active / idle lists.
    """
    low = (state or "").strip().lower()
    if done_signal:
        return STATUS_COMPLETE
    if low in UNAVAILABLE_STATES:
        return STATUS_IDLE
    complete_l = _lower(complete)
    if low in complete_l or any(k in low for k in complete_l):
        return STATUS_COMPLETE
    paused_l = _lower(paused)
    if low in paused_l or any(k in low for k in paused_l):
        return STATUS_PAUSED
    if low in _lower(active):
        return STATUS_RUNNING
    if low in _lower(idle):
        return STATUS_IDLE
    return STATUS_RUNNING if unknown_is_running else STATUS_IDLE


def to_minutes(value: str | None, unit: str | None) -> float:
    """Convert a remaining-time sensor value to minutes.

    Handles numeric values in h / min / s (GE Home reports hours for
    dishwashers and ovens, minutes for laundry) and "H:MM[:SS]" strings.
    """
    if value is None:
        return 0.0
    text = str(value).strip()
    if ":" in text:
        try:
            parts = [float(p) for p in text.split(":")]
        except ValueError:
            return 0.0
        while len(parts) < 3:
            parts.append(0.0)
        hours, minutes, seconds = parts[:3]
        return max(0.0, hours * 60 + minutes + seconds / 60)
    try:
        number = float(text)
    except ValueError:
        return 0.0
    unit = (unit or "min").strip().lower()
    if unit in ("h", "hr", "hrs", "hour", "hours"):
        number *= 60
    elif unit in ("s", "sec", "secs", "second", "seconds"):
        number /= 60
    elif unit in ("d", "day", "days"):
        number *= 1440
    return max(0.0, number)


def meaningful(text: str | None) -> str:
    """Return text unless it's a placeholder like '---' or 'N/A'."""
    if text is None:
        return ""
    stripped = str(text).strip()
    return "" if stripped.lower() in BLANK_TEXT else stripped


def hex_to_rgb(value: str) -> list[int]:
    """'#00BCD4' -> [0, 188, 212] (invalid input -> Home Assistant blue)."""
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    try:
        return [int(text[i : i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return [3, 169, 244]


def color_to_hex(value, default: str = "#03A9F4") -> str:
    """Accept an [r, g, b] list (color picker) or a hex string (older entries)."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            r, g, b = (max(0, min(255, int(c))) for c in value)
        except TypeError, ValueError:
            return default
        return f"#{r:02X}{g:02X}{b:02X}"
    if isinstance(value, str) and value.strip():
        text = value.strip()
        return text if text.startswith("#") else f"#{text}"
    return default


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        parts = [int(p) for p in str(value).split(":")]
    except ValueError:
        return None
    while len(parts) < 3:
        parts.append(0)
    try:
        return time(*parts[:3])
    except ValueError:
        return None


def in_quiet_hours(now: time, start: str | None, end: str | None) -> bool:
    """True if ``now`` is inside quiet hours (which may span midnight)."""
    begin, finish = _parse_time(start), _parse_time(end)
    if begin is None or finish is None or begin == finish:
        return False
    if begin < finish:
        return begin <= now < finish
    return now >= begin or now < finish


def async_track_later(
    hass: HomeAssistant,
    entry: ConfigEntry,
    delay: float | timedelta,
    action: Callable[..., Any],
) -> CALLBACK_TYPE:
    """Schedule ``action`` and cancel it when ``entry`` unloads.

    ``async_call_later`` on its own survives a reload: the test harness then
    fails the run ("Lingering timer"), and a real restart can call into a
    coordinator that has already been torn down. ``entry.async_on_unload``
    is invoked by Home Assistant itself after ``async_unload_entry``, so the
    timer is cancelled even if the caller also keeps its own handle.

    The returned cancel callback is safe to call twice (once early, again
    from the unload hook).
    """
    cancel = async_call_later(hass, delay, action)
    entry.async_on_unload(cancel)
    return cancel


def async_entry_background_task(
    hass: HomeAssistant,
    entry: ConfigEntry,
    target: Coroutine[Any, Any, Any],
    name: str,
) -> Any:
    """Run ``target`` as a background task of ``entry``.

    A bare ``hass.async_create_task`` is not cancelled when the appliance is
    removed, so a state change that arrives during unload keeps running
    against a dead coordinator. ``ConfigEntry.async_create_background_task``
    is cancelled as the entry unloads.

    ``async_block_till_done`` does not wait for background tasks. The test
    suite opts in (see ``tests/conftest.py``) because these tasks are the
    short event handlers the tests assert on.
    """
    return entry.async_create_background_task(hass, target, name)
