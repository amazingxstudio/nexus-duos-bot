"""Drives an AI bot's moves for one active match. start_ai_loop() is
called from match_runner.start_match() exactly like _run_timer() is —
same fire-and-forget asyncio.create_task pattern, same
match_id-keyed task registry, so it cancels the same way too (see
cancel_ai_task(), called from finish_match() and leave_match()).
"""

import asyncio
import logging

from app.cache import load_match_state
from app.games.ai.registry import get_ai_policy

logger = logging.getLogger("nexus_duos.ai")

POLL_INTERVAL_SECONDS = 0.25

_active_ai_tasks: dict[str, asyncio.Task] = {}


def start_ai_loop(engine, match_id: str, ai_user_id: str, difficulty) -> None:
    policy = get_ai_policy(engine.game_key, difficulty)
    if policy is None:
        return  # no AI wired up for this game — nothing to do
    task = asyncio.create_task(_run_ai_loop(engine, match_id, ai_user_id, policy))
    _active_ai_tasks[match_id] = task


def cancel_ai_task(match_id: str) -> None:
    task = _active_ai_tasks.pop(match_id, None)
    if task:
        task.cancel()


async def _run_ai_loop(engine, match_id: str, ai_user_id: str, policy) -> None:
    # Deferred import: match_runner.py imports THIS module at the top
    # level (to call start_ai_loop/cancel_ai_task), so importing
    # match_runner back at this module's top level would be a circular
    # import. Doing it here instead — only actually needed once a loop is
    # running — sidesteps that; by the time this coroutine executes,
    # match_runner has long since finished loading.
    from app.games.engine.match_runner import handle_game_action

    memory: dict = {}
    try:
        while True:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

            state = await load_match_state(match_id)
            if not state or state.get("status") != "active":
                break
            me = state.get("players", {}).get(ai_user_id)
            if not me or me.get("finished"):
                break

            try:
                decision = policy.choose(state, ai_user_id, memory)
            except Exception:
                logger.exception("AI policy error for match_id=%s", match_id)
                decision = None
            if not decision:
                continue

            # handle_game_action re-validates against a freshly loaded
            # state itself, so a decision that's gone stale by the time it
            # runs (opponent moved first) is just silently rejected, same
            # as a real player's mistimed action would be — no special
            # handling needed here.
            await handle_game_action(engine, match_id, ai_user_id, decision["action_type"], decision["data"])
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("AI loop crashed for match_id=%s", match_id)
    finally:
        _active_ai_tasks.pop(match_id, None)
