"""
Authentication service for user registration, login, and token validation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, DuplicateError, NotFoundError, ValidationError
from app.models.user_model import User
from app.schemas.auth_schemas import UserRegister

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service class for user authentication workflows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _normalize_email(value: str) -> str:
        return (value or "").strip().lower()

    @staticmethod
    def _hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def _verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def _commit_or_raise(self) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            logger.exception("Integrity error during auth DB commit")
            raise ValidationError(
                "Database integrity error.",
                details={"error": str(exc.orig) if exc.orig else str(exc)},
            )
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.exception("SQLAlchemy error during auth DB commit")
            raise ValidationError("Database operation failed.", details={"error": str(exc)})

    def _commit_refresh_or_raise(self, user: User) -> User:
        self._commit_or_raise()
        try:
            self.db.refresh(user)
        except SQLAlchemyError as exc:
            self.db.rollback()
            logger.exception("Failed to refresh user id=%s", user.id)
            raise ValidationError("Failed to refresh user.", details={"error": str(exc)})
        return user

    def get_user_by_email(self, email: str) -> Optional[User]:
        normalized = self._normalize_email(email)
        if not normalized:
            return None
        return self.db.query(User).filter(User.email == normalized).first()

    def get_user_by_id(self, user_id: int) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise NotFoundError("User", user_id)
        return user

    def register_user(self, payload: UserRegister) -> User:
        email = self._normalize_email(payload.email)
        if not email:
            raise ValidationError("Email cannot be empty.")

        if len(payload.password) < 8:
            raise ValidationError("Password must be at least 8 characters long.")

        existing = self.get_user_by_email(email)
        if existing:
            raise DuplicateError("User", "email", email)

        user = User(
            email=email,
            full_name=payload.full_name.strip() if payload.full_name else None,
            hashed_password=self._hash_password(payload.password),
            is_active=True,
        )
        self.db.add(user)
        self._commit_refresh_or_raise(user)
        logger.info("Registered user id=%s email=%s", user.id, user.email)
        return user

    def authenticate_user(self, email: str, password: str) -> User:
        normalized = self._normalize_email(email)
        if not normalized:
            raise AuthenticationError("Invalid credentials.")

        user = self.get_user_by_email(normalized)
        if user is None:
            raise AuthenticationError("Invalid credentials.")

        if not user.is_active:
            raise AuthenticationError("User account is inactive.")

        if not self._verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid credentials.")

        return user

    @staticmethod
    def _validate_token_config() -> None:
        if not settings.SECRET_KEY or settings.SECRET_KEY == "change-me-in-production":
            logger.warning("Using default SECRET_KEY. Set a secure SECRET_KEY in environment.")

    def create_access_token(
        self,
        *,
        subject: str,
        user_id: int,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        self._validate_token_config()

        expire_at = datetime.now(timezone.utc) + (
            expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        payload: Dict[str, Any] = {
            "sub": subject,
            "uid": user_id,
            "exp": expire_at,
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        user = self.authenticate_user(email=email, password=password)
        token = self.create_access_token(subject=user.email, user_id=user.id)
        return {
            "token": {"access_token": token, "token_type": "bearer"},
            "user": user,
        }

    def get_current_user_from_token(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
            )
        except JWTError as exc:
            raise AuthenticationError("Could not validate authentication token.") from exc

        user_id_raw = payload.get("uid")
        if user_id_raw is None:
            raise AuthenticationError("Token is missing required user identifier.")

        try:
            user_id = int(user_id_raw)
        except (TypeError, ValueError) as exc:
            raise AuthenticationError("Token contains invalid user identifier.") from exc

        user = self.db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise AuthenticationError("Token subject no longer exists.")
        if not user.is_active:
            raise AuthenticationError("User account is inactive.")
        return user
