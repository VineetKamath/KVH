"""Opaque prefixed identifiers (rule R2): never integers, never parsed for meaning."""
from __future__ import annotations

import re
import secrets

ID_RE = re.compile(r"^[a-z]{2,5}_[0-9a-z]{4,32}$")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def is_valid_id(value: str, prefix: str | None = None) -> bool:
    if not isinstance(value, str) or not ID_RE.match(value):
        return False
    return prefix is None or value.startswith(prefix + "_")
