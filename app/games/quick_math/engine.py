from app.models import GameKey
from app.games.engine.base import BaseGameEngine


class QuickMathEngine(BaseGameEngine):
    """Placeholder for Quick Math — reserved slot (GameKey, registry
    entry, seed row) so every shared file is already final, but the real
    rules aren't implemented yet. The frontend doesn't offer this game for
    selection (see lib/games.ts's comingSoon flag), so a real match should
    never actually reach this engine — but if one somehow does, it resolves
    immediately as a draw instead of hanging.

    To implement this game for real: replace the body of this class (keep
    the class name and game_key so registry.py never needs to change), then
    flip comingSoon to false for QUICK_MATH in the frontend's lib/games.ts.
    """

    game_key = GameKey.QUICK_MATH
    duration_ms = 1000

    def create_initial_payload(self) -> dict:
        return {"coming_soon": True}

    def on_match_start(self, state: dict) -> None:
        for p in state["players"].values():
            p["finished"] = True

    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        return state
