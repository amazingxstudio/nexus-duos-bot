from fastapi import Header, HTTPException, status

from app.security import verify_session_token


async def require_auth(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session token")

    token = authorization[len("Bearer "):]
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    return {"user_id": payload["userId"], "telegram_id": payload["telegramId"]}
