"""Registry for the 3 fixed "AI opponent" accounts (one per difficulty)
used by Practice vs AI. Each is a real row in `users` / `profiles` /
`settings` — the exact same tables every real player uses — instead of a
synthetic non-DB id. That's what lets the entire existing room/match/
history pipeline (PlayerCard, GameDispatcher, history.py's opponent
lookup, profile stats skip-on-non-RANKED, all of it) display and score a
practice match with zero special-casing anywhere else in the app.

seed_ai_bots() (app/games/ai/seed.py) ensures the 3 rows exist on every
boot and registers each one's real `user.id` here — this module then
answers "is this user_id an AI bot, and if so which difficulty" from
memory for the rest of the process's life, avoiding a DB round trip on
every practice-room creation and every single AI move.
"""

from app.games.ai.difficulty import AIDifficulty

# Negative, out-of-range Telegram ids — real Telegram user ids are always
# positive, so these can never collide with an actual account. Fixed
# across restarts so seed_ai_bots() finds (and reuses) the same row every
# time instead of creating a duplicate bot account on every boot.
AI_BOT_TELEGRAM_IDS: dict[AIDifficulty, int] = {
    AIDifficulty.EASY: -101,
    AIDifficulty.NORMAL: -102,
    AIDifficulty.PRO: -103,
}

AI_BOT_DISPLAY: dict[AIDifficulty, dict] = {
    AIDifficulty.EASY: {"nickname": "AI · Easy", "player_id": "NDUO-BOT-EASY"},
    AIDifficulty.NORMAL: {"nickname": "AI · Normal", "player_id": "NDUO-BOT-NORM"},
    AIDifficulty.PRO: {"nickname": "AI · Pro", "player_id": "NDUO-BOT-PRO1"},
}

_user_id_by_difficulty: dict[AIDifficulty, str] = {}
_difficulty_by_user_id: dict[str, AIDifficulty] = {}


def register_bot(difficulty: AIDifficulty, user_id: str) -> None:
    _user_id_by_difficulty[difficulty] = user_id
    _difficulty_by_user_id[user_id] = difficulty


def get_bot_user_id(difficulty: AIDifficulty) -> str | None:
    return _user_id_by_difficulty.get(difficulty)


def get_difficulty_for_user(user_id: str | None) -> AIDifficulty | None:
    if not user_id:
        return None
    return _difficulty_by_user_id.get(user_id)


def is_ai_bot(user_id: str | None) -> bool:
    return bool(user_id) and user_id in _difficulty_by_user_id
