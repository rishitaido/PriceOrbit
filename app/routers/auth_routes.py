"""Authentication REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user_model import User
from app.schemas.auth_schemas import AuthSuccessResponse, UserRegister, UserResponse
from app.services.auth_service import AuthService

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """Dependency injection factory for AuthService."""
    return AuthService(db)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    service: AuthService = Depends(get_auth_service),
) -> User:
    """Resolve current user from bearer token."""
    return service.get_current_user_from_token(token)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: UserRegister,
    service: AuthService = Depends(get_auth_service),
):
    return service.register_user(payload)


@router.post("/login", response_model=AuthSuccessResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
):
    return service.login(email=form_data.username, password=form_data.password)


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    """Return profile for authenticated user."""
    return current_user
