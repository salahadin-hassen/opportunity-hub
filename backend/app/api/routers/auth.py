"""Registration and login HTTP endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import unauthorized
from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas import TokenResponse, UserCreate, UserLogin, UserRead
from app.services.users import (
    EmailAlreadyRegisteredError,
    authenticate_user,
    create_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    """Create one account, or report the email conflict as a 409."""
    try:
        user = create_user(db, payload)
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from error
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange valid credentials for a short-lived bearer access token."""
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise unauthorized()
    return TokenResponse(access_token=create_access_token(user.id))
