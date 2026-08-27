"""Authentication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from research_navigator.deps import get_current_token, get_current_user, get_db
from research_navigator.models import SessionToken, User
from research_navigator.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserRead
from research_navigator.security import hash_password, hash_token, issue_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _create_session(request: Request, session: Session, user: User) -> TokenResponse:
    raw_token = issue_token()
    session.add(
        SessionToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC)
            + timedelta(hours=request.app.state.settings.session_ttl_hours),
        )
    )
    session.commit()
    return TokenResponse(access_token=raw_token, user=UserRead.model_validate(user))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, request: Request, session: Session = Depends(get_db)
) -> TokenResponse:
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    return _create_session(request, session, user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest, request: Request, session: Session = Depends(get_db)
) -> TokenResponse:
    user = session.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _create_session(request, session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: SessionToken = Depends(get_current_token),
    session: Session = Depends(get_db),
) -> Response:
    token.revoked_at = datetime.now(UTC)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user
