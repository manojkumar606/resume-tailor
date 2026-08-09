from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.token import AuthResponse
from app.schemas.user import UserCreate, UserLogin, UserRead, VerifyRequest
from app.services.email import EmailError, EmailProvider, get_email_provider
from app.services.verification import (
    ResendTooSoon,
    VerificationError,
    issue_token,
    redeem_token,
    seconds_until_resend_allowed,
    send_verification_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])

Mailer = Annotated[EmailProvider, Depends(get_email_provider)]


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        access_token=create_access_token(user.id),
        user=UserRead.model_validate(user),
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: DbSession, mailer: Mailer) -> AuthResponse:
    email = _normalize_email(payload.email)

    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.flush()  # assigns user.id without committing

    token = issue_token(db, user)

    # Send before committing. Verification is mandatory, so an account whose
    # email never arrived is unusable — better to persist nothing and let the
    # user retry than to leave them permanently locked out.
    try:
        send_verification_email(mailer, user, token)
    except EmailError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send the verification email. Please try again.",
        ) from exc

    db.commit()
    db.refresh(user)
    return _auth_response(user)


@router.post("/login", response_model=AuthResponse)
def login(payload: UserLogin, db: DbSession) -> AuthResponse:
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))

    # Same error for "no such user" and "wrong password" — do not leak which
    # emails are registered.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
    )
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise invalid
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )

    # Unverified users are allowed to log in. They get a token that only works
    # on /auth routes, which is what lets the client show a "confirm your email"
    # screen with a working resend button.
    return _auth_response(user)


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/verify", response_model=AuthResponse)
def verify_email(payload: VerifyRequest, db: DbSession) -> AuthResponse:
    """Redeem a verification token.

    Deliberately unauthenticated: the link is opened from an email client, which
    may not be on the device holding the session.
    """
    try:
        user = redeem_token(db, payload.token)
    except VerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(user)
    # A fresh token so the client can proceed straight into the app.
    return _auth_response(user)


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    current_user: CurrentUser, db: DbSession, mailer: Mailer
) -> dict:
    if current_user.is_verified:
        return {"detail": "This address is already confirmed."}

    wait = seconds_until_resend_allowed(db, current_user)
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(ResendTooSoon(wait)),
            headers={"Retry-After": str(wait)},
        )

    token = issue_token(db, current_user)
    try:
        send_verification_email(mailer, current_user, token)
    except EmailError as exc:
        # Drop the token row: keeping it would start a cooldown for an email
        # that was never delivered.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send the verification email. Please try again.",
        ) from exc

    db.commit()
    return {"detail": "Verification email sent."}
