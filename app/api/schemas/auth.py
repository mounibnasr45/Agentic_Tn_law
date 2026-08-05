"""Request/response models for registration, login and token refresh."""

import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    # 12, not 8. Length dominates entropy: an 8-character password is brute-forceable
    # regardless of how many symbol classes you demand, and composition rules mostly
    # push users toward "Password1!" — which is in every wordlist.
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the ACCESS token expires


class UserResponse(BaseModel):
    # UUID, not str. User.id is a uuid.UUID and Pydantic v2 does NOT coerce it to str —
    # model_validate(user) raises `string_type` on a `str` field. Declaring the real type
    # lets the ORM object validate directly, and JSON serialisation still emits the plain
    # string the frontend already expects.
    id: uuid.UUID
    email: EmailStr
    # Exposed so the SPA can hide the admin navigation from accounts that cannot use it.
    # A CONVENIENCE, NOT A CONTROL: the privilege boundary is get_current_admin on the
    # server, which re-checks this on every admin request. Hiding a link stops a confusing
    # 403, it does not stop anyone from issuing the request by hand.
    is_admin: bool = False

    model_config = {"from_attributes": True}
