import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    language: str
    default_check_interval_days: int
    credits_remaining: int
    created_at: datetime

    model_config = {"from_attributes": True}


class UserSettingsUpdate(BaseModel):
    language: str | None = None
    default_check_interval_days: int | None = None


class CreditsResponse(BaseModel):
    credits_remaining: int
