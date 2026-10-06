"""Small shared helpers (pure functions, easy to unit test)."""
from __future__ import annotations

import re
from collections.abc import Iterable

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
