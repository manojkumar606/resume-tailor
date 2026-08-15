import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, Mailer
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.models.verification import CodePurpose
from app.schemas.token import AuthResponse
from app.schemas.user import (
    CodeResendRequest,
    CodeSent,
    CodeSubmission,
    UnsubscribeRequest,
    UserCreate,
    UserLogin,
    UserRead,
)
from app.services.email import EmailError
from app.services.unsubscribe import InvalidUnsubscribeToken, read_token
from app.services.email_codes import (
    CodeError,
    consume_code,
    issue_code,
    seconds_until_resend_allowed,
    send_code,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _code_sent(user: User, purpose: CodePurpose) -> CodeSent:
    return CodeSent(
        email=user.email,
        expires_in_minutes=settings.LOGIN_CODE_TTL_MINUTES,
        detail=(
            "We emailed you a 6-digit code. Enter it to "
            + ("finish signing up." if purpose is CodePurpose.SIGNUP else "sign in.")
        ),
    )


def _issue_and_send(db: DbSession, mailer: Mailer, user: User, purpose: CodePurpose) -> None:
    """Create a code and email it, or leave nothing behind.

    Rolls back on a delivery failure: a stored code nobody received would start
    the resend cooldown and block the retry that might have worked.
    """
    code = issue_code(db, user, purpose)
    try:
        send_code(mailer, user, code, purpose)
    except EmailError as exc:
        db.rollback()
        logger.error("Could not email a %s code: %s", purpose.value, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send the code. Please try again in a moment.",
        ) from exc
    db.commit()


@router.post("/signup", response_model=CodeSent, status_code=status.HTTP_202_ACCEPTED)
def signup(payload: UserCreate, db: DbSession, mailer: Mailer) -> CodeSent:
    """Create the account, then require the emailed code before issuing a session."""
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

    _issue_and_send(db, mailer, user, CodePurpose.SIGNUP)
    return _code_sent(user, CodePurpose.SIGNUP)


@router.post("/login", response_model=CodeSent, status_code=status.HTTP_202_ACCEPTED)
def login(payload: UserLogin, db: DbSession, mailer: Mailer) -> CodeSent:
    """Check the password, then email a code. No token is issued at this step.

    A correct password alone is never enough — every sign-in requires access to
    the mailbox as well.
    """
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))

    # Same error for "no such user" and "wrong password", so the form cannot be
    # used to discover who has an account here.
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

    _issue_and_send(db, mailer, user, CodePurpose.LOGIN)
    return _code_sent(user, CodePurpose.LOGIN)


@router.post("/verify-code", response_model=AuthResponse)
def verify_code(payload: CodeSubmission, db: DbSession) -> AuthResponse:
    """Exchange a valid code for a session.

    This is the only endpoint that mints a token.
    """
    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))

    # Identical error whether the address is unknown or the digits are wrong.
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="That code is invalid or has expired. Request a new one.",
    )
    if user is None:
        raise invalid

    try:
        purpose = consume_code(db, user, payload.code)
    except CodeError as exc:
        # Attempt counters were incremented, so the failure must be persisted.
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if purpose is CodePurpose.SIGNUP:
        # First successful code proves the address is real.
        user.is_verified = True

    db.commit()
    db.refresh(user)

    return AuthResponse(
        access_token=create_access_token(user.id),
        user=UserRead.model_validate(user),
    )


@router.post("/resend-code", status_code=status.HTTP_202_ACCEPTED)
def resend_code(payload: CodeResendRequest, db: DbSession, mailer: Mailer) -> dict:
    """Send a fresh code, replacing any outstanding one.

    Unauthenticated, because the caller has no session yet. The response is the
    same whether or not the address exists, so this cannot be used to enumerate
    accounts.
    """
    generic = {"detail": "If that address has an account, a new code is on its way."}

    email = _normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return generic

    wait = seconds_until_resend_allowed(db, user)
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Please wait {wait}s before asking for another code.",
            headers={"Retry-After": str(wait)},
        )

    purpose = CodePurpose.SIGNUP if not user.is_verified else CodePurpose.LOGIN
    _issue_and_send(db, mailer, user, purpose)
    return generic


@router.post("/unsubscribe")
def unsubscribe(payload: UnsubscribeRequest, db: DbSession) -> dict:
    """Turn reminders off from a link in an email, with no session.

    Unauthenticated on purpose: somebody annoyed at 7am will not log in to find
    a toggle, they will press "mark as spam" — and that harms delivery of the
    login codes, which go out from the same sender.

    A POST rather than a GET on the link itself, because mail clients and
    security scanners prefetch links and would otherwise unsubscribe people who
    never clicked anything.
    """
    try:
        user_id = read_token(payload.token)
    except InvalidUnsubscribeToken as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    user = db.get(User, user_id)
    # Same response whether or not the account exists, so the endpoint cannot be
    # used to check which ids are real.
    if user is not None:
        user.reminders_enabled = False
        db.commit()

    return {"detail": "Reminder emails are off. Sign-in codes are unaffected."}


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)
