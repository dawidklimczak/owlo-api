import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User


ALGORITHM = "HS256"

# In-memory store for magic link tokens (replace with Redis in production)
_magic_link_tokens: dict[str, dict[str, Any]] = {}


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return uuid.UUID(user_id)
    except (JWTError, ValueError):
        return None


def get_user_from_token(token: str, db: Session) -> User | None:
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def get_or_create_user_by_email(email: str, db: Session, google_id: str | None = None) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        if google_id and not user.google_id:
            user.google_id = google_id
            db.commit()
            db.refresh(user)
        return user

    user = User(
        email=email,
        google_id=google_id,
        default_check_interval_days=settings.DEFAULT_CHECK_INTERVAL_DAYS,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_magic_link_token(email: str) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.MAGIC_LINK_EXPIRE_MINUTES)
    _magic_link_tokens[token] = {"email": email, "expires_at": expires_at}
    return token


def verify_magic_link_token(token: str) -> str | None:
    """Returns email if token is valid, None otherwise."""
    data = _magic_link_tokens.get(token)
    if not data:
        return None
    if datetime.now(timezone.utc) > data["expires_at"]:
        del _magic_link_tokens[token]
        return None
    del _magic_link_tokens[token]
    return data["email"]


async def exchange_google_code(code: str, redirect_uri: str) -> dict[str, Any]:
    """Exchange Google authorization code for user info."""
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_response.raise_for_status()
        tokens = token_response.json()

        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        userinfo_response.raise_for_status()
        return userinfo_response.json()
