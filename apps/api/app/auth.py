from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_operator(email: str, password: str) -> bool:
    """Verify operator credentials. Prefer bcrypt hash when configured."""
    settings = get_settings()
    if email.strip().lower() != settings.operator_email.strip().lower():
        return False
    if settings.operator_password_hash:
        try:
            return verify_password(password, settings.operator_password_hash)
        except Exception:
            return False
    # Plaintext fallback for local demo only
    return password == settings.operator_password


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": subject, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def require_operator(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    """Require JWT in production. Local/dev allows open access (no login)."""
    settings = get_settings()
    env = (settings.clipops_env or "development").lower()
    if env != "production":
        if credentials is None:
            return settings.operator_email
        # Still accept a valid token if provided; ignore bad ones locally
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
            return str(payload.get("sub") or settings.operator_email)
        except JWTError:
            return settings.operator_email

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        sub = payload.get("sub")
        if not sub:
            raise HTTPException(status_code=401, detail="Invalid token")
        return str(sub)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
