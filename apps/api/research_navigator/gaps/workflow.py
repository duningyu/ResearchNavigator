"""Gap workflow state rules."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def assert_confirmable(status: str, challenge_completed_at: datetime | None) -> None:
    if status != "pending_confirmation" or challenge_completed_at is None:
        raise ValueError("Challenge search must complete before human confirmation")
