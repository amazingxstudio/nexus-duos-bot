import json

import redis.asyncio as redis

from app.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

USER_CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h
MATCH_STATE_TTL_SECONDS = 60 * 30  # 30 min safety net


async def ping_redis() -> bool:
    try:
        return await redis_client.ping()
    except Exception:
        return False


# ---- User profile cache ------------------------------------------------

def _user_cache_key(telegram_id: str) -> str:
    return f"user:{telegram_id}:cache"


async def cache_user_profile(telegram_id: str, data: dict) -> None:
    await redis_client.set(_user_cache_key(telegram_id), json.dumps(data), ex=USER_CACHE_TTL_SECONDS)


async def get_cached_user_profile(telegram_id: str) -> dict | None:
    raw = await redis_client.get(_user_cache_key(telegram_id))
    return json.loads(raw) if raw else None


async def invalidate_user_cache(telegram_id: str) -> None:
    await redis_client.delete(_user_cache_key(telegram_id))


# ---- Live match state (used by the game engine, Batch 3) ---------------

def _match_state_key(match_id: str) -> str:
    return f"match:{match_id}:state"


async def save_match_state(match_id: str, state: dict) -> None:
    await redis_client.set(_match_state_key(match_id), json.dumps(state), ex=MATCH_STATE_TTL_SECONDS)


async def load_match_state(match_id: str) -> dict | None:
    raw = await redis_client.get(_match_state_key(match_id))
    return json.loads(raw) if raw else None


async def delete_match_state(match_id: str) -> None:
    await redis_client.delete(_match_state_key(match_id))


# ---- Presence -----------------------------------------------------------

def _presence_key(user_id: str) -> str:
    return f"presence:{user_id}"


async def set_user_online(user_id: str, session_id: str) -> None:
    await redis_client.set(_presence_key(user_id), session_id, ex=600)


async def set_user_offline(user_id: str) -> None:
    await redis_client.delete(_presence_key(user_id))


async def is_user_online(user_id: str) -> bool:
    return await redis_client.exists(_presence_key(user_id)) == 1
