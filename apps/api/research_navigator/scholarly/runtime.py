"""Persistent scholarly-source runtime health and cooldown state."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.models import SourceRuntimeState
from research_navigator.scholarly.base import SourceStatus

_MAX_COOLDOWN_SECONDS = 60 * 60


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _int_metadata(metadata: dict[str, Any], key: str) -> int | None:
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_reset(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return _utc(datetime.fromisoformat(normalized))
    except ValueError:
        return None


class SourceRuntimeRepository:
    """Read and update global source runtime state without storing credentials."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, source: str) -> SourceRuntimeState | None:
        return self.session.scalar(
            select(SourceRuntimeState).where(SourceRuntimeState.source == source)
        )

    def before_call(
        self, source: str, *, now: datetime | None = None
    ) -> SourceStatus | None:
        current = _utc(now or datetime.now(UTC))
        row = self.get(source)
        if row is None or row.cooldown_until is None:
            return None
        cooldown_until = _utc(row.cooldown_until)
        if cooldown_until <= current:
            return None
        try:
            metadata = json.loads(row.metadata_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        metadata["cooldown_until"] = cooldown_until.isoformat()
        metadata["consecutive_failures"] = row.consecutive_failures
        return SourceStatus(
            status="rate_limited",
            detail=row.last_error_code or f"{source} is in persisted cooldown",
            metadata=metadata,
            checked_at=current,
        )

    def after_call(
        self,
        source: str,
        status: SourceStatus,
        *,
        now: datetime | None = None,
    ) -> SourceRuntimeState:
        current = _utc(now or datetime.now(UTC))
        row = self.get(source)
        if row is None:
            row = SourceRuntimeState(source=source)
            self.session.add(row)
            self.session.flush()

        metadata: dict[str, Any] = dict(status.metadata)
        row.operational_status = status.status
        row.last_http_status = _int_metadata(metadata, "http_status")
        row.rate_limit_limit = _int_metadata(metadata, "rate_limit_limit")
        row.rate_limit_remaining = _int_metadata(metadata, "rate_limit_remaining")
        row.rate_limit_reset_at = _parse_reset(metadata.get("rate_limit_reset"))
        row.last_error_code = status.detail if status.status not in {"ok", "disabled"} else None

        if status.status == "rate_limited":
            row.consecutive_failures += 1
            retry_after = _int_metadata(metadata, "retry_after_seconds")
            exponential = min(_MAX_COOLDOWN_SECONDS, 2 ** min(row.consecutive_failures, 10))
            cooldown_seconds = max(1, retry_after or exponential)
            row.cooldown_until = current + timedelta(
                seconds=min(cooldown_seconds, _MAX_COOLDOWN_SECONDS)
            )
        elif status.status == "ok":
            row.consecutive_failures = 0
            row.cooldown_until = None
            row.last_error_code = None
        elif status.status == "error":
            row.consecutive_failures += 1

        persisted_metadata = dict(metadata)
        if row.cooldown_until is not None:
            persisted_metadata["cooldown_until"] = _utc(row.cooldown_until).isoformat()
        persisted_metadata["consecutive_failures"] = row.consecutive_failures
        row.metadata_json = json.dumps(persisted_metadata, ensure_ascii=False, sort_keys=True)
        self.session.add(row)
        return row
