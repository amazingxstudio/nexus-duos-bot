from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import require_auth
from app.models import Match, Profile, UserSettings, Game
from app.history_cleanup import HISTORY_LIMIT

router = APIRouter()


@router.get("/me")
async def get_my_history(auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    matches = await _fetch_matches(db, auth["user_id"])
    return {"matches": [await _serialize_match(db, m, auth["user_id"]) for m in matches]}


@router.get("/{player_id}")
async def get_player_history(player_id: str, auth=Depends(require_auth), db: AsyncSession = Depends(get_db)):
    profile = (await db.execute(select(Profile).where(Profile.player_id == player_id))).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="PROFILE_NOT_FOUND")
    target_user_id = profile.user_id
    settings = (await db.execute(select(UserSettings).where(UserSettings.user_id == target_user_id))).scalar_one_or_none()
    show_all = settings.show_history_to_all if settings else True
    if not show_all:
        # Private means private — no partial/shared-match exception.
        return {"matches": [], "hidden": True}
    matches = await _fetch_matches(db, target_user_id)
    return {"matches": [await _serialize_match(db, m, target_user_id) for m in matches], "hidden": False}


async def _fetch_matches(db, user_id, limit: int = HISTORY_LIMIT):
    result = await db.execute(
        select(Match).where(Match.finished_at.is_not(None))
        .where(or_(Match.player1_id == user_id, Match.player2_id == user_id))
        .order_by(Match.finished_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def _serialize_match(db, m, perspective_user_id):
    is_p1 = m.player1_id == perspective_user_id
    self_id = m.player1_id if is_p1 else m.player2_id
    opponent_id = m.player2_id if is_p1 else m.player1_id
    self_score = m.player1_score if is_p1 else m.player2_score
    opponent_score = m.player2_score if is_p1 else m.player1_score
    result = m.player1_result if is_p1 else m.player2_result
    game = await db.get(Game, m.game_id)
    self_profile = (await db.execute(select(Profile).where(Profile.user_id == self_id))).scalar_one_or_none() if self_id else None
    opponent_out = {"nickname": "AI", "score": opponent_score}
    if opponent_id:
        opp_profile = (await db.execute(select(Profile).where(Profile.user_id == opponent_id))).scalar_one_or_none()
        if opp_profile:
            # This is the opponent's OWN privacy choice, not the viewer's —
            # if they've turned off "show history to all", their identity
            # is masked here too, not just on their own profile page. No
            # player_id means the frontend has nothing to link to.
            opp_settings = (await db.execute(select(UserSettings).where(UserSettings.user_id == opponent_id))).scalar_one_or_none()
            opponent_visible = opp_settings.show_history_to_all if opp_settings else True
            if opponent_visible:
                opponent_out = {"nickname": opp_profile.nickname, "player_id": opp_profile.player_id, "score": opponent_score}
            else:
                opponent_out = {"nickname": "Anonymous", "score": opponent_score}
    return {
        "id": m.id, "game": game.name if game else "Unknown",
        "game_key": game.key.value if game else None, "mode": m.mode.value,
        "date": m.finished_at.isoformat() if m.finished_at else None,
        "self": {"nickname": self_profile.nickname if self_profile else "You", "score": self_score},
        "opponent": opponent_out, "result": result.value if result else None,
    }
