from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError

from app.config import settings

ALGORITHM = "HS256"


def issue_session_token(user_id: str, telegram_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRES_MINUTES)
    payload = {"userId": user_id, "telegramId": telegram_id, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def verify_session_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None
