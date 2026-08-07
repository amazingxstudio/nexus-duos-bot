"""
In-memory replacement for Redis. Works because Render's free web service
runs a single instance — all state lives safely in this process's RAM.

Trade-off: state resets on deploy/restart (e.g. an in-progress match would
be lost). Acceptable for now; swap this module's internals for real Redis
(e.g. Upstash's free tier) later without touching call sites, since the
function signatures below are what the rest of the app calls.
"""

# userId -> cached profile dict (nickname, playerId, photoUrl, ...)
_user_cache: dict[str, dict] = {}

# matchId -> live match state dict (see app/games/engine/types.py in Batch 3)
_match_state: dict[str, dict] = {}

# userId -> connected socket/session id, for presence
_presence: dict[str, str] = {}


def cache_user_profile(telegram_id: str, data: dict) -> None:
    _user_cache[telegram_id] = data


def get_cached_user_profile(telegram_id: str) -> dict | None:
    return _user_cache.get(telegram_id)


def invalidate_user_cache(telegram_id: str) -> None:
    _user_cache.pop(telegram_id, None)


def save_match_state(match_id: str, state: dict) -> None:
    _match_state[match_id] = state


def load_match_state(match_id: str) -> dict | None:
    return _match_state.get(match_id)


def delete_match_state(match_id: str) -> None:
    _match_state.pop(match_id, None)


def set_user_online(user_id: str, session_id: str) -> None:
    _presence[user_id] = session_id


def set_user_offline(user_id: str) -> None:
    _presence.pop(user_id, None)


def is_user_online(user_id: str) -> bool:
    return user_id in _presence
