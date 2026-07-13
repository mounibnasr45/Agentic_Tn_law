"""FastAPI dependencies.

Depends() is how a handler declares what it needs without knowing how to build it. That
matters here for one concrete reason: `get_current_user` can be overridden in a test with
one line, so the auth-protected handlers are testable without minting real JWTs — and,
more importantly, the embedding model is built ONCE in the lifespan rather than per
request. Constructing it per request would load 450MB of weights on every call.
"""
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotAuthenticated, to_http_exception
from app.core.security import TokenError, decode_access_token
from app.domain.ports import Embedder
from app.infra.db.models import User
from app.infra.db.session import get_session
from app.services.auth_service import AuthService

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
