from pydantic import BaseModel, EmailStr


class GoogleCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkVerifyRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
