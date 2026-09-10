"""Shared, fail-closed coordination for arXiv request dispatch."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar, cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from research_navigator.db import Database
from research_navigator.models import SourceRuntimeState

T = TypeVar("T")


class CoordinatorUnavailable(RuntimeError):
    """Shared coordination state cannot be safely consulted."""


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class ArxivRequestCoordinator:
    """A database-backed lease and global next-send gate for arXiv."""

    source = "arxiv"

    def __init__(
        self,
        *,
        database: Database,
        owner_id: str | None = None,
        minimum_interval_seconds: float = 3.0,
        lease_ttl_seconds: float = 30.0,
        poll_interval_seconds: float = 0.05,
        acquire_timeout_seconds: float = 60.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.database = database
        self.owner_id = owner_id or f"arxiv-{uuid4().hex}"
        self.minimum_interval_seconds = minimum_interval_seconds
        self.lease_ttl_seconds = lease_ttl_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.acquire_timeout_seconds = acquire_timeout_seconds
        self.clock = clock or (lambda: datetime.now(UTC))
        self._request_started_at: datetime | None = None

    def _ensure_state(self) -> None:
        try:
            with self.database.session() as session:
                row = session.query(SourceRuntimeState.id).filter_by(source=self.source).first()
                if row is None:
                    session.add(SourceRuntimeState(source=self.source))
                    session.commit()
        except IntegrityError:
            # Another process won the unique insert race.  A fresh session
            # verifies the row before proceeding with the lease update.
            try:
                with self.database.session() as session:
                    if session.scalar(
                        select(SourceRuntimeState.id).where(
                            SourceRuntimeState.source == self.source
                        )
                    ) is None:
                        raise CoordinatorUnavailable("arXiv coordination state unavailable")
            except CoordinatorUnavailable:
                raise
            except Exception as exc:
                raise CoordinatorUnavailable("arXiv coordination state unavailable") from exc
        except Exception as exc:
            raise CoordinatorUnavailable("arXiv coordination state unavailable") from exc

    def try_acquire(self) -> bool:
        """Atomically acquire the shared lease when the send gate is open."""
        self._ensure_state()
        now = _utc(self.clock())
        expiry = now + timedelta(seconds=self.lease_ttl_seconds)
        try:
            with self.database.session() as session:
                result = session.execute(
                    update(SourceRuntimeState)
                    .where(SourceRuntimeState.source == self.source)
                    .where(
                        (SourceRuntimeState.lease_owner.is_(None))
                        | (SourceRuntimeState.lease_expires_at <= now)
                    )
                    .where(
                        (SourceRuntimeState.next_allowed_at.is_(None))
                        | (SourceRuntimeState.next_allowed_at <= now)
                    )
                    .values(lease_owner=self.owner_id, lease_expires_at=expiry)
                )
                session.commit()
                acquired = cast(int, getattr(result, "rowcount", 0)) == 1
        except Exception as exc:
            raise CoordinatorUnavailable("arXiv coordination state unavailable") from exc
        if acquired:
            # The dispatch timestamp is captured after the contending update
            # commits; using the pre-transaction timestamp would shorten the
            # global spacing when SQLite waits on another process.
            self._request_started_at = _utc(self.clock())
        return acquired

    def release(self, request_started_at: datetime | None = None) -> bool:
        """Release only this owner and retain the global spacing gate."""
        # Start the cooldown from completion.  This is deliberately more
        # conservative than start+3s: client connection setup can occur after
        # lease acquisition, so completion+3s is the auditable guarantee at
        # the actual HTTP boundary.
        del request_started_at
        next_allowed = _utc(self.clock()) + timedelta(
            seconds=self.minimum_interval_seconds
        )
        try:
            with self.database.session() as session:
                result = session.execute(
                    update(SourceRuntimeState)
                    .where(SourceRuntimeState.source == self.source)
                    .where(SourceRuntimeState.lease_owner == self.owner_id)
                    .values(
                        lease_owner=None,
                        lease_expires_at=None,
                        next_allowed_at=next_allowed,
                    )
                )
                session.commit()
                released = cast(int, getattr(result, "rowcount", 0)) == 1
        except Exception as exc:
            raise CoordinatorUnavailable("arXiv coordination state unavailable") from exc
        if released:
            self._request_started_at = None
        return released

    async def run(self, request_type: str, operation: Callable[[], Awaitable[T]]) -> T:
        """Run one external request; waiting or failure never bypasses the gate."""
        del request_type  # retained for the future observability contract
        deadline = time.monotonic() + self.acquire_timeout_seconds
        while time.monotonic() < deadline:
            if self.try_acquire():
                started = self._request_started_at
                try:
                    return await operation()
                finally:
                    self.release(started)
            await asyncio.sleep(self.poll_interval_seconds)
        raise CoordinatorUnavailable("arXiv coordinator wait timed out")
