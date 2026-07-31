"""Small shared helpers."""
from __future__ import annotations

import re


def slugify_tag(value: str) -> str:
    """Turn a display name into a safe notification tag suffix."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")
