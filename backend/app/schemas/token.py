from pydantic import BaseModel

from app.schemas.user import UserRead


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthResponse(Token):
    """Token plus the user record, so the client avoids a second round trip."""

    user: UserRead
