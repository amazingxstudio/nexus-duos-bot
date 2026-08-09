import random

from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.engine.utils import elapsed_ms

TARGET_LIFETIME_MS = 1200
MATCH_DURATION_MS = 30_000


class CyberDuelEngine(BaseGameEngine):
    game_key = GameKey.CYBER_DUEL
    duration_ms = MATCH_DURATION_MS

    def create_initial_payload(self) -> dict:
        targets = []
        t = 500
        while t < MATCH_DURATION_MS - 500:
            targets.append(
                {
                    "id": f"t{len(targets)}",
                    "x": round(random.random() * 100),
                    "y": round(random.random() * 100),
                    "spawned_at": t,
                    "expires_at": t + TARGET_LIFETIME_MS,
                }
            )
            t += 350 + random.random() * 400
        return {"targets": targets, "claimed": {}}

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        if action_type != "target_hit":
            return state

        target_id = data.get("target_id")
        targets = state["payload"]["targets"]
        claimed = state["payload"]["claimed"]

        target = next((t for t in targets if t["id"] == target_id), None)
        if not target:
            raise ValueError("UNKNOWN_TARGET")
        if target_id in claimed:
            return state  # already claimed — ignore silently

        elapsed = elapsed_ms(state)
        if not (target["spawned_at"] <= elapsed <= target["expires_at"] + 150):
            raise ValueError("TARGET_EXPIRED_OR_NOT_SPAWNED")

        claimed[target_id] = user_id
        reaction_ms = max(elapsed - target["spawned_at"], 0)
        speed_bonus = max(0, 100 - int(reaction_ms / 10))
        state["players"][user_id]["score"] += 50 + speed_bonus

        return state
