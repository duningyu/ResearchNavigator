"""FastAPI dependencies for sessions and authentication."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from research_navigator.models import SessionToken, User
from research_navigator.security import hash_token

_bearer = HTTPBearer(auto_error=False)


def ensure_public_demo_operation_allowed(request: Request) -> None:
    if request.app.state.settings.public_demo_mode:
        raise HTTPException(status_code=403, detail="DEMO_MODE_RESTRICTED")


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.database.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    token_record = session.scalar(
        select(SessionToken).where(SessionToken.token_hash == hash_token(credentials.credentials))
    )
    now = datetime.now(UTC)
    if token_record is None or token_record.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    expires_at = token_record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = session.get(User, token_record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_db),
) -> SessionToken:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    record = session.scalar(
        select(SessionToken).where(SessionToken.token_hash == hash_token(credentials.credentials))
    )
    if record is None or record.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return record
