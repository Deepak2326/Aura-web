"""FastAPI dependencies: DB sessions and admin authentication / authorization."""
from __future__ import annotations

from typing import Generator

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from . import crud
from .models import AdminUser
from .security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Generator[Session, None, None]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_current_admin(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AdminUser:
    settings = request.app.state.settings
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_REQUIRED", "message": "Authentication required."},
        )
    try:
        payload = decode_access_token(
            secret=settings.jwt_secret, algorithm=settings.jwt_algorithm, token=credentials.credentials
        )
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_INVALID", "message": "Invalid or expired session. Please sign in again."},
        )
    user = crud.get_admin_by_email(db, payload.get("sub", ""))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail={"code": "AUTH_INVALID", "message": "Invalid or expired session. Please sign in again."},
        )
    return user


def require_admin(current: AdminUser = Depends(get_current_admin)) -> AdminUser:
    """Role guard: only the 'admin' role may perform mutating actions."""
    if current.role != "admin":
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "You do not have permission to perform this action."},
        )
    return current
