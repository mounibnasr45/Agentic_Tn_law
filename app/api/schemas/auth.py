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
    id: str
    email: EmailStr

    model_config = {"from_attributes": True}
