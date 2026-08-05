"""FastAPI dependency providers: the database session, the current user, the
embedder, and the admin-only guard."""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotAnAdministrator, NotAuthenticated, to_http_exception
from app.core.logging import get_logger
from app.core.security import TokenError, decode_access_token
from app.domain.ports import Embedder
from app.infra.db.models import User
from app.infra.db.session import get_session
from app.services.auth_service import AuthService

log = get_logger(__name__)

# auto_error=False so a missing header raises OUR 401 (with a French detail and the
# WWW-Authenticate header) rather than FastAPI's default.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_embedder(request: Request) -> Embedder:
    """The single embedder, loaded once in the lifespan and held on app.state."""
    return request.app.state.embedder


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(session)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    session: SessionDep,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    if not token:
        raise to_http_exception(NotAuthenticated())

    try:
        user_id = decode_access_token(token)
    except TokenError as exc:
        raise to_http_exception(NotAuthenticated()) from exc

    user = await session.get(User, user_id)

    # A token can outlive the user it names: the account may have been deleted or
    # disabled after the token was minted. Trusting the signature alone would keep a
    # disabled account working for the full access-token lifetime.
    if user is None or not user.is_active:
        raise to_http_exception(NotAuthenticated())

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUser) -> User:
    """Layered on get_current_user, not a parallel path.

    Chaining means an admin route cannot accidentally skip the checks the normal user
    dependency already performs — token signature, account still exists, account still
    active. A separate "admin token" path would be a second place for those to be
    forgotten, and the one that gets forgotten is always the one guarding the
    corpus-replacing endpoint.
    """
    if not user.is_admin:
        # Logged: a non-admin reaching an admin route is either a bug in the UI's guard or
        # someone probing, and both are worth being able to see in the logs.
        log.info("admin_access_denied", user_id=str(user.id))
        raise to_http_exception(NotAnAdministrator())

    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]
