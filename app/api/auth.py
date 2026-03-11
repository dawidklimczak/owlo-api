from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import GoogleCallbackRequest, MagicLinkRequest, MagicLinkVerifyRequest
from app.schemas.user import UserResponse
from app.services import auth as auth_service
from app.services.notification import send_magic_link


router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

COOKIE_OPTS = {
    "httponly": True,
    "secure": True,
    "samesite": "lax",
    "domain": settings.COOKIE_DOMAIN,
    "max_age": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
}


@router.post("/google")
@limiter.limit("10/minute")
async def google_auth(
    request: Request,
    body: GoogleCallbackRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        userinfo = await auth_service.exchange_google_code(body.code, body.redirect_uri)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to authenticate with Google")

    email = userinfo.get("email")
    google_id = userinfo.get("id")
    if not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No email in Google profile")

    user = auth_service.get_or_create_user_by_email(email, db, google_id=google_id)
    token = auth_service.create_access_token(user.id)

    response.set_cookie("access_token", token, **COOKIE_OPTS)
    return {"message": "Authenticated successfully"}


@router.post("/magic-link")
@limiter.limit("5/minute")
async def send_magic_link_endpoint(
    request: Request,
    body: MagicLinkRequest,
    db: Session = Depends(get_db),
):
    token = auth_service.create_magic_link_token(body.email)
    try:
        await send_magic_link(email=body.email, token=token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send email",
        )
    return {"message": "Magic link sent"}


@router.post("/verify")
@limiter.limit("10/minute")
async def verify_magic_link(
    request: Request,
    body: MagicLinkVerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    email = auth_service.verify_magic_link_token(body.token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired magic link",
            headers={"X-Error-Code": "INVALID_TOKEN"},
        )

    user = auth_service.get_or_create_user_by_email(email, db)
    token = auth_service.create_access_token(user.id)

    response.set_cookie("access_token", token, **COOKIE_OPTS)
    return {"message": "Authenticated successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/logout")
async def logout(response: Response, current_user: User = Depends(get_current_user)):
    response.delete_cookie("access_token", domain=settings.COOKIE_DOMAIN)
    return {"message": "Logged out"}
