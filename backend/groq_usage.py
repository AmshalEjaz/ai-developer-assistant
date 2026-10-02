from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Mapping

_DURATION_RE = re.compile(
    r"^(?:(?P<days>\d+(?:\.\d+)?)d)?"
    r"(?:(?P<hours>\d+(?:\.\d+)?)h)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)m)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)s)?$",
    re.IGNORECASE,
)

_lock = Lock()
_latest_snapshot: dict = {
    "available": False,
    "status": "waiting",
    "message": "Usage available after the first Groq response.",
    "model": "openai/gpt-oss-120b",
    "updated_at": None,
    "requests": None,
    "tokens": None,
    "retry_after_seconds": None,
}


def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
    if not headers:
        return None

    if hasattr(headers, "get"):
        value = headers.get(name)
        if value is None:
            value = headers.get(name.lower())
        if value is None:
            value = headers.get(name.upper())
        return str(value) if value is not None else None

    return None


def _number(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_reset_duration(value: str | None) -> float | None:
    if not value:
        return None

    text = value.strip()
    if not text:
        return None

    try:
        return float(text)
    except ValueError:
        pass

    match = _DURATION_RE.fullmatch(text)
    if not match:
        return None

    parts = {
        key: float(raw) if raw else 0.0
        for key, raw in match.groupdict().items()
    }

    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def _reset_at(raw: str | None, now: datetime) -> str | None:
    seconds = parse_reset_duration(raw)
    if seconds is None:
        return None
    return (now + timedelta(seconds=seconds)).isoformat()


def _bucket(
    limit_raw: str | None,
    remaining_raw: str | None,
    reset_raw: str | None,
    now: datetime,
) -> dict | None:
    limit = _number(limit_raw)
    remaining = _number(remaining_raw)

    if limit is None and remaining is None and not reset_raw:
        return None

    used = None
    if limit is not None and remaining is not None:
        used = max(limit - remaining, 0)

    return {
        "limit": limit,
        "remaining": remaining,
        "used": used,
        "reset_in": reset_raw,
        "reset_at": _reset_at(reset_raw, now),
    }


def build_usage_snapshot(
    headers: Mapping[str, str] | None,
    *,
    model: str,
    now: datetime | None = None,
    rate_limited: bool = False,
) -> dict:
    now = now or datetime.now(timezone.utc)

    request_bucket = _bucket(
        _header(headers, "x-ratelimit-limit-requests"),
        _header(headers, "x-ratelimit-remaining-requests"),
        _header(headers, "x-ratelimit-reset-requests"),
        now,
    )

    token_bucket = _bucket(
        _header(headers, "x-ratelimit-limit-tokens"),
        _header(headers, "x-ratelimit-remaining-tokens"),
        _header(headers, "x-ratelimit-reset-tokens"),
        now,
    )

    has_rate_data = bool(request_bucket or token_bucket)

    return {
        "available": has_rate_data or rate_limited,
        "status": "rate_limited" if rate_limited else ("available" if has_rate_data else "waiting"),
        "message": (
            "Rate limit reached."
            if rate_limited
            else (
                None
                if has_rate_data
                else "Usage available after the first Groq response."
            )
        ),
        "model": model,
        "updated_at": now.isoformat(),
        "requests": request_bucket,
        "tokens": token_bucket,
        "retry_after_seconds": _float(_header(headers, "retry-after")),
    }


def capture_groq_usage(
    headers: Mapping[str, str] | None,
    *,
    model: str,
    rate_limited: bool = False,
) -> dict:
    snapshot = build_usage_snapshot(
        headers,
        model=model,
        rate_limited=rate_limited,
    )

    with _lock:
        _latest_snapshot.clear()
        _latest_snapshot.update(snapshot)
        return dict(_latest_snapshot)


def get_groq_usage_snapshot() -> dict:
    with _lock:
        snapshot = dict(_latest_snapshot)
        if isinstance(snapshot.get("requests"), dict):
            snapshot["requests"] = dict(snapshot["requests"])
        if isinstance(snapshot.get("tokens"), dict):
            snapshot["tokens"] = dict(snapshot["tokens"])
        return snapshot
