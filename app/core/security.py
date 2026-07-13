"""Password hashing and JWT.

Library choices, because an interviewer will ask:

  - argon2-cffi, not passlib+bcrypt. Argon2id won the Password Hashing Competition and
    is memory-hard, so a GPU cannot parallelise an attack the way it can against bcrypt.
    passlib's last release was 2020 and it warns on Python 3.13.
  - PyJWT, not python-jose. python-jose is effectively unmaintained and has had
    algorithm-confusion CVEs. PyJWT is what FastAPI's own security docs use.

The previous hashing in this portfolio was `sha256(password + salt)` — a single fast
hash, which is exactly what a GPU cracks at billions of guesses per second. Password
hashing must be SLOW on purpose.
"""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """A token was missing, malformed, expired, or of the wrong type."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    return True


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with weaker parameters than we now use.

    Argon2's cost parameters should rise as hardware gets faster. Rehashing on successful
    login is the only moment we hold the plaintext, so it is the only chance to upgrade.
    """
    return _hasher.check_needs_rehash(password_hash)


def create_access_token(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)

    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.access_token_minutes),
            "jti": secrets.token_urlsafe(16),
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )


def decode_access_token(token: str) -> uuid.UUID:
    settings = get_settings()

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("invalid token") from exc

    # Without this check a REFRESH token would be accepted as an ACCESS token. Refresh
    # tokens are long-lived by design, so confusing the two hands an attacker a 14-day
    # access token and quietly defeats the entire point of short access expiry.
    if payload.get("type") != "access":
        raise TokenError("wrong token type")

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise TokenError("malformed subject") from exc


def create_refresh_token() -> tuple[str, str]:
    """Return (raw_token, token_hash).

    A refresh token is an opaque random string, not a JWT. It has to be revocable, and a
    JWT cannot be revoked without server-side state anyway — so the state is the point,
    and the JWT would be pure ceremony.

    Only the HASH is stored. The database is the thing most likely to leak, and a leaked
    table of raw refresh tokens is a leaked table of live sessions. sha256 (not argon2) is
    correct here: the token is 256 bits of entropy we generated, so there is no weak
    password to brute-force and no reason to pay argon2's cost on every refresh.
    """
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
