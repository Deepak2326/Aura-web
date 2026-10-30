"""Admin authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import crud
from ..deps import get_current_admin, get_db
from ..models import AdminUser
from ..rate_limit import enforce_rate_limit
from ..schemas import AdminUserOut, LoginRequest, TokenResponse
from ..security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    enforce_rate_limit(request, "login_limiter")
    user = crud.get_admin_by_email(db, payload.email)
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        # Generic message — never reveal whether the account exists.
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."},
        )
    settings = request.app.state.settings
    token = create_access_token(
        secret=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_expire_minutes,
        subject=user.email,
        role=user.role,
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        email=user.email,
        role=user.role,
    )


@router.get("/me", response_model=AdminUserOut)
def me(current: AdminUser = Depends(get_current_admin)) -> AdminUser:
    return current
