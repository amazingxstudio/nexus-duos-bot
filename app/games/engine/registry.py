from app.models import GameKey
from app.games.engine.base import BaseGameEngine
from app.games.cyber_duel.engine import CyberDuelEngine
from app.games.speed_typing.engine import SpeedTypingEngine
from app.games.code_breaker.engine import CodeBreakerEngine
from app.games.memory_warfare.engine import MemoryWarfareEngine
from app.games.puzzle_arena.engine import PuzzleArenaEngine
from app.games.tower_control.engine import TowerControlEngine
from app.games.neon_chess.engine import NeonChessEngine
from app.games.arena_cards.engine import ArenaCardsEngine

_registry: dict[GameKey, BaseGameEngine] = {
    GameKey.CYBER_DUEL: CyberDuelEngine(),
    GameKey.SPEED_TYPING: SpeedTypingEngine(),
    GameKey.CODE_BREAKER: CodeBreakerEngine(),
    GameKey.MEMORY_WARFARE: MemoryWarfareEngine(),
    GameKey.PUZZLE_ARENA: PuzzleArenaEngine(),
    GameKey.TOWER_CONTROL: TowerControlEngine(),
    GameKey.NEON_CHESS: NeonChessEngine(),
    GameKey.ARENA_CARDS: ArenaCardsEngine(),
}


def get_game_engine(key) -> BaseGameEngine:
    key_enum = key if isinstance(key, GameKey) else GameKey(key)
    engine = _registry.get(key_enum)
    if not engine:
        raise ValueError(f"NO_ENGINE_REGISTERED_FOR_{key}")
    return engine


def is_game_implemented(key) -> bool:
    key_enum = key if isinstance(key, GameKey) else GameKey(key)
    return key_enum in _registry
