from abc import ABC, abstractmethod

from app.models import GameKey


class BaseGameEngine(ABC):
    game_key: GameKey
    duration_ms: int

    @abstractmethod
    def create_initial_payload(self) -> dict:
        """Builds the initial per-game payload (targets, sentence, board, etc)."""

    @abstractmethod
    def apply_action(self, state: dict, user_id: str, action_type: str, data: dict) -> dict:
        """
        Validates and applies a player action server-side. Must recompute
        scores itself — never trust client-reported values. Raise ValueError
        to reject an invalid/cheating action (the caller drops it silently).
        """

    def sanitize_payload_for_client(self, payload: dict) -> dict:
        """Strips server-only secrets (e.g. Code Breaker's answer) before broadcast."""
        return payload

    def on_match_start(self, state: dict) -> None:
        """Optional setup hook run once, right before the first broadcast."""

    def should_finish_early(self, state: dict) -> bool:
        return all(p["finished"] for p in state["players"].values())

    def compute_result(self, state: dict) -> dict:
        players = list(state["players"].values())
        winner_id = None
        if len(players) == 2:
            a, b = players
            if a["score"] > b["score"]:
                winner_id = a["user_id"]
            elif b["score"] > a["score"]:
                winner_id = b["user_id"]
        return {
            "match_id": state["match_id"],
            "scores": {p["user_id"]: p["score"] for p in players},
            "winner_id": winner_id,
        }
