"""Authentication endpoints: register, login, refresh, logout."""

from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, CurrentUser
from app.api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserResponse,
)
from app.core.config import get_settings
from app.core.errors import DomainError, to_http_exception

router = APIRouter(prefix="/auth", tags=["auth"])


def _pair(access: str, refresh: str) -> TokenPair:
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=get_settings().access_token_minutes * 60,
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, auth: AuthServiceDep) -> TokenPair:
    try:
        user = await auth.register(payload.email, payload.password)
        access, refresh = await auth.issue_tokens(user)
    except DomainError as exc:
        raise to_http_exception(exc) from exc

    return _pair(access, refresh)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, auth: AuthServiceDep) -> TokenPair:
    try:
        user = await auth.authenticate(payload.email, payload.password)
        access, refresh = await auth.issue_tokens(user)
    except DomainError as exc:
        raise to_http_exception(exc) from exc

    return _pair(access, refresh)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, auth: AuthServiceDep) -> TokenPair:
    """Exchange a refresh token for a NEW pair. The presented token is revoked.

    Presenting an already-revoked token revokes the user's entire chain: we cannot tell a
    client retrying an old request from an attacker replaying a stolen token, so we assume
    the worse case.
    """
    try:
        access, new_refresh = await auth.rotate(payload.refresh_token)
    except DomainError as exc:
        raise to_http_exception(exc) from exc

    return _pair(access, new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, auth: AuthServiceDep) -> None:
    # Idempotent: an unknown or already-revoked token is not an error. A logout that can
    # fail is a logout users will skip.
    await auth.revoke(payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    """The caller's own profile.

    model_validate(), NOT UserResponse(id=..., email=...). The field-by-field form silently
    drops any field the schema gains later: `is_admin` was added to UserResponse and every
    response kept reporting the DEFAULT False, so a genuine admin was told they were not
    one and the corpus navigation never appeared. Nothing failed — the schema was right, the
    database was right, and the endpoint quietly lied.
    """
    return UserResponse.model_validate(user)
