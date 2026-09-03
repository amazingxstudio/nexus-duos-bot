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


# ---- Public profile card cache (avatar + nickname + stats) -------------
#
# Batch: profile visitors (spec D.13/9) turned "view a profile" into a
# recursive, click-through action (a visitor card links to ITS OWN
# profile, which lists its own visitors, and so on) — so the same public
# profile can now get looked up repeatedly in a short span without the
# viewer's own data ever changing. This is a short-TTL read-through cache
# for that response, keyed by player_id so it never needs the viewer's
# identity. NOT used for a player's own /profile/me (that always reads
# fresh — see routes/profile.py — since a player just finishing a match
# expects to see their updated stats immediately, not up to
# PUBLIC_PROFILE_CACHE_TTL_SECONDS later).

PUBLIC_PROFILE_CACHE_TTL_SECONDS = 60 * 5  # 5 min — short enough that stale stats on someone ELSE's profile are a non-issue


def _public_profile_cache_key(player_id: str) -> str:
    return f"profile:{player_id}:public_cache"


async def cache_public_profile(player_id: str, data: dict) -> None:
    await redis_client.set(_public_profile_cache_key(player_id), json.dumps(data), ex=PUBLIC_PROFILE_CACHE_TTL_SECONDS)


async def get_cached_public_profile(player_id: str) -> dict | None:
    raw = await redis_client.get(_public_profile_cache_key(player_id))
    return json.loads(raw) if raw else None


async def invalidate_public_profile_cache(player_id: str) -> None:
    await redis_client.delete(_public_profile_cache_key(player_id))


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


# ---- Invite decline spam-guard (spec D.16b) -----------------------------
#
# Tracks how many times, IN A ROW (no acceptance in between), `decliner_id`
# has declined an invite from `inviter_id`. Hitting DECLINE_STREAK_LIMIT
# blocks `inviter_id` from reaching `decliner_id` with a new invite for
# INVITE_BLOCK_TTL_SECONDS — see sockets.py's invite_send / invite_decline
# / invite_accept handlers, the only callers. Lives in Redis (not an
# in-process dict) so it survives a reconnect and stays correct even if
# Render ever runs more than one worker.

DECLINE_STREAK_LIMIT = 3
DECLINE_STREAK_TTL_SECONDS = 60 * 60  # abandon an old streak after an hour of silence
INVITE_BLOCK_TTL_SECONDS = 60


def _decline_streak_key(inviter_id: str, decliner_id: str) -> str:
    return f"invite_decline_streak:{inviter_id}:{decliner_id}"


def _invite_block_key(inviter_id: str, decliner_id: str) -> str:
    return f"invite_block:{inviter_id}:{decliner_id}"


async def register_invite_decline(inviter_id: str, decliner_id: str) -> bool:
    """Call when `decliner_id` declines an invite from `inviter_id`.
    Returns True the moment this decline is the Nth in a row that trips
    the block — the caller doesn't need to do anything else, the block key
    is already set by the time this returns."""
    key = _decline_streak_key(inviter_id, decliner_id)
    count = await redis_client.incr(key)
    await redis_client.expire(key, DECLINE_STREAK_TTL_SECONDS)
    if count >= DECLINE_STREAK_LIMIT:
        await redis_client.set(_invite_block_key(inviter_id, decliner_id), "1", ex=INVITE_BLOCK_TTL_SECONDS)
        await redis_client.delete(key)
        return True
    return False


async def clear_invite_decline_streak(inviter_id: str, decliner_id: str) -> None:
    """Call when `decliner_id` accepts an invite from `inviter_id` — an
    acceptance breaks the "in a row" streak."""
    await redis_client.delete(_decline_streak_key(inviter_id, decliner_id))


async def is_invite_blocked(inviter_id: str, decliner_id: str) -> bool:
    return await redis_client.exists(_invite_block_key(inviter_id, decliner_id)) == 1
