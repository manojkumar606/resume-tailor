"""Shared FastAPI dependencies.

`get_current_user` is the single place that turns a bearer token into a User.
Every protected route depends on it, and every query filters by the returned
user's id — that is what makes the app multi-tenant.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise unauthorized

    try:
        user_id = uuid.UUID(subject)
    except ValueError:
        raise unauthorized from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_verified_user(current_user: CurrentUser) -> User:
    """Like get_current_user, but rejects accounts that have not confirmed
    their email address.

    Every route outside /auth depends on this. 403 rather than 401: the token is
    valid and the caller is authenticated, they simply lack permission — a 401
    would make the client discard a perfectly good token and log the user out.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please confirm your email address before using the app.",
        )
    return current_user


VerifiedUser = Annotated[User, Depends(get_verified_user)]
