"""Scrub secrets from span payloads before they are stored or streamed."""

import re
from collections.abc import Iterable
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEYS = {
    "authorization",
    "proxy_authorization",
    "api_key",
    "apikey",
    "x_api_key",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "client_secret",
    "password",
    "cookie",
    "set_cookie",
}

_SECRET_PATTERNS = [
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
]


def _is_sensitive(key: str) -> bool:
    return key.lower().replace("-", "_") in _SENSITIVE_KEYS


def redact(value: Any, secrets: Iterable[str] = ()) -> Any:
    """Return a copy of `value` with sensitive keys, token patterns and known secrets replaced."""
    known = [s for s in secrets if s]
    return _redact(value, known)


def _redact(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, dict):
        return {
            k: REDACTED if isinstance(k, str) and _is_sensitive(k) else _redact(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, REDACTED)
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub(REDACTED, value)
        return value
    return value
