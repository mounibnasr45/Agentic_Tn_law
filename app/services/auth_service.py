"""Registration, login, and refresh-token rotation with replay detection."""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import (
    AccountDisabled,
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidRefreshToken,
    TokenReplayDetected,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from app.infra.db.models import RefreshToken, User

log = get_logger(__name__)


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(self, email: str, password: str) -> User:
        settings = get_settings()

        user = User(
            email=email.lower().strip(),
            password_hash=hash_password(password),
        )
        self._session.add(user)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise EmailAlreadyRegistered(email) from exc

        log.info("user_registered", user_id=str(user.id))
        _ = settings  # settings reserved for future policy (e.g. email verification)
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self._session.scalar(
            select(User).where(User.email == email.lower().strip())
        )

        # Verify against a dummy hash even when the user does not exist, so that
        # "unknown email" and "wrong password" take the same time. Returning early on a
        # missing user turns login into a user-enumeration oracle: an attacker can tell
        # which emails are registered purely from response latency.
        if user is None:
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentials()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentials()

        if not user.is_active:
            raise AccountDisabled()

        # Successful login is the only moment we hold the plaintext, so it is the only
        # chance to upgrade a hash made with weaker (older) argon2 parameters.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
            log.info("password_hash_upgraded", user_id=str(user.id))

        return user

    async def issue_tokens(self, user: User) -> tuple[str, str]:
        """Return (access_token, raw_refresh_token). Only the refresh HASH is stored."""
        settings = get_settings()
        raw, token_hash = create_refresh_token()

        self._session.add(
            RefreshToken(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
            )
        )
        await self._session.flush()

        return create_access_token(user.id), raw

    async def rotate(self, raw_refresh_token: str) -> tuple[str, str]:
        """Exchange a refresh token for a new pair, revoking the old one.

        ROTATION is what makes this a refresh token rather than a long-lived access token:
        each use invalidates the token that was used.

        REPLAY DETECTION falls out of the rotation chain. A token that exists but is
        already revoked means one of two things — the legitimate client is retrying an
        old request, or an attacker stole the token and is using it after the client
        already rotated. We cannot distinguish them, so we assume the worse case and
        revoke the user's ENTIRE chain, forcing re-authentication. Without the chain the
        stolen token would simply look "unknown" and the theft would be invisible.
        """
        settings = get_settings()
        token_hash = hash_refresh_token(raw_refresh_token)

        token = await self._session.scalar(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )

        if token is None:
            raise InvalidRefreshToken()

        if token.revoked_at is not None:
            await self._revoke_all_for_user(token.user_id)

            # COMMIT BEFORE RAISING. The request-scoped session dependency rolls back on
            # any exception, and HTTPException is an exception — so without this, the 401
            # we are about to raise would roll back the very revocation that makes the 401
            # meaningful. The replay would be detected, reported, and then undone, leaving
            # the attacker's stolen chain fully alive.
            #
            # A security effect must not depend on the response being a success.
            await self._session.commit()

            log.warning(
                "refresh_token_replay_detected",
                user_id=str(token.user_id),
                action="revoked entire token chain; user must re-authenticate",
            )
            raise TokenReplayDetected()

        if token.expires_at <= datetime.now(UTC):
            raise InvalidRefreshToken()

        user = await self._session.get(User, token.user_id)
        if user is None or not user.is_active:
            raise AccountDisabled()

        raw, new_hash = create_refresh_token()
        successor = RefreshToken(
            user_id=user.id,
            token_hash=new_hash,
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
        self._session.add(successor)
        await self._session.flush()

        token.revoked_at = datetime.now(UTC)
        token.replaced_by = successor.id

        return create_access_token(user.id), raw

    async def revoke(self, raw_refresh_token: str) -> None:
        """Logout. Idempotent — an already-revoked or unknown token is not an error."""
        token = await self._session.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(raw_refresh_token)
            )
        )
        if token is not None and token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)

    async def _revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        tokens = await self._session.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        )
        now = datetime.now(UTC)
        for token in tokens:
            token.revoked_at = now


# A real argon2 hash of a throwaway value, used to keep the timing of a failed login on
# an unknown email indistinguishable from a wrong password. Computed once at import.
_DUMMY_HASH = hash_password("not-a-real-password")
