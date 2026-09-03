from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_auth
from app.models import User
from app.messaging import get_conversation, are_friends, send_message as persist_message

router = APIRouter()


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)


def _serialize(m, me_id: str) -> dict:
    return {
        "id": m.id,
        "sender_id": m.sender_id,
        "content": m.content,
        "mine": m.sender_id == me_id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/{user_id}")
async def get_messages_route(user_id: str, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """History fetch — used on mount when the quick-message panel opens
    (see app/friends/page.tsx). Friends-only: messaging is reached from the
    friend list, so there's never a legitimate case where the two aren't
    already friends."""
    if not await are_friends(db, auth["user_id"], user_id):
        raise HTTPException(status_code=403, detail="NOT_FRIENDS")
    messages = await get_conversation(db, auth["user_id"], user_id)
    return {"messages": [_serialize(m, auth["user_id"]) for m in messages]}


@router.post("/{user_id}")
async def send_message_route(user_id: str, body: SendMessageRequest, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    """REST fallback for sending a direct message. The primary path is the
    "dm:send" socket event (see sockets.py) for realtime delivery to the
    recipient — this route exists so a message still saves (just without
    the instant push) if the socket happens to be reconnecting."""
    if not await are_friends(db, auth["user_id"], user_id):
        raise HTTPException(status_code=403, detail="NOT_FRIENDS")
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="USER_NOT_FOUND")
    message = await persist_message(db, auth["user_id"], user_id, body.content.strip())
    return {"message": _serialize(message, auth["user_id"])}
