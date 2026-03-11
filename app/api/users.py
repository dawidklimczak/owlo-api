from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user import CreditsResponse, UserResponse, UserSettingsUpdate


router = APIRouter()


@router.get("/settings", response_model=UserResponse)
async def get_settings(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/settings", response_model=UserResponse)
async def update_settings(
    body: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.language is not None:
        current_user.language = body.language
    if body.default_check_interval_days is not None:
        current_user.default_check_interval_days = body.default_check_interval_days

    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(current_user: User = Depends(get_current_user)):
    return CreditsResponse(credits_remaining=current_user.credits_remaining)
