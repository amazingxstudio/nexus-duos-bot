import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Room, RoomStatus, GameVote, Game, Match, MatchMode, GameKey
from app.room_code import generate_room_code
from app.games.ai.difficulty import AIDifficulty
from app.games.ai.bots import get_bot_user_id
from app.games.ai.registry import is_practice_ai_game


async def create_room(db: AsyncSession, player1_id: str, preset_game_key: str | None = None) -> Room:
    room = Room(
        code=generate_room_code(),
        player1_id=player1_id,
        status=RoomStatus.WAITING_FOR_PLAYER,
        preset_game_key=GameKey(preset_game_key) if preset_game_key else None,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


async def join_room(db: AsyncSession, code: str, player2_id: str):
    """Joins a room. If the room has a preset game (quick duel), the voting
    phase is skipped entirely and a Match is created immediately. Returns
    (room, match_or_none)."""
    result = await db.execute(select(Room).where(Room.code == code))
    room = result.scalar_one_or_none()

    if not room:
        raise ValueError("ROOM_NOT_FOUND")
    if room.status != RoomStatus.WAITING_FOR_PLAYER:
        raise ValueError("ROOM_NOT_JOINABLE")
    if room.player1_id == player2_id:
        raise ValueError("CANNOT_JOIN_OWN_ROOM")

    room.player2_id = player2_id

    if room.preset_game_key:
        game_result = await db.execute(select(Game).where(Game.key == room.preset_game_key))
        game = game_result.scalar_one_or_none()
        if not game:
            raise ValueError("GAME_NOT_FOUND")

        room.game_id = game.id
        room.status = RoomStatus.READY_CHECK
        match = Match(room_id=room.id, game_id=game.id, mode=MatchMode.RANKED, player1_id=room.player1_id, player2_id=room.player2_id)
        db.add(match)
        await db.commit()
        await db.refresh(room)
        await db.refresh(match)
        return room, match

    room.status = RoomStatus.VOTING
    await db.commit()
    await db.refresh(room)
    return room, None


async def create_practice_room(db: AsyncSession, user_id: str, game_key: str, difficulty: str):
    """Practice vs AI: unlike create_room()/join_room(), this returns a
    room that's already fully paired and past voting — the 'opponent' is
    one of the 3 seeded bot accounts (app/games/ai/bots.py), joined and
    READY_CHECK'd in the same call, since there's no second human to wait
    on or vote against. The bot's own ready-tap is simulated shortly after
    the human's (see sockets.py's player_ready handler) rather than here,
    so the ready-check screen still gets a beat to render.

    Only games with a real AI policy wired up (currently Connect Four and
    Dots and Boxes — see app/games/ai/registry.py) are offered here.
    """
    try:
        key_enum = GameKey(game_key)
    except ValueError:
        raise ValueError("UNKNOWN_GAME")
    if not is_practice_ai_game(key_enum):
        raise ValueError("GAME_NOT_AVAILABLE_FOR_PRACTICE")

    try:
        difficulty_enum = AIDifficulty(difficulty)
    except ValueError:
        raise ValueError("UNKNOWN_DIFFICULTY")

    bot_user_id = get_bot_user_id(difficulty_enum)
    if not bot_user_id:
        raise ValueError("AI_NOT_READY")

    game_result = await db.execute(select(Game).where(Game.key == key_enum))
    game = game_result.scalar_one_or_none()
    if not game:
        raise ValueError("GAME_NOT_FOUND")

    room = Room(
        code=generate_room_code(),
        player1_id=user_id,
        player2_id=bot_user_id,
        game_id=game.id,
        preset_game_key=key_enum,
        status=RoomStatus.READY_CHECK,
    )
    db.add(room)
    await db.flush()

    match = Match(room_id=room.id, game_id=game.id, mode=MatchMode.PRACTICE_AI, player1_id=user_id, player2_id=bot_user_id)
    db.add(match)

    await db.commit()
    await db.refresh(room)
    await db.refresh(match)
    return room, match


def resolve_game_selection(player1_picks: list[str], player2_picks: list[str]) -> dict:
    common = [g for g in player1_picks if g in player2_picks]
    if len(common) == 1:
        return {"resolved": True, "game_key": common[0]}
    if len(common) > 1:
        return {"resolved": True, "game_key": random.choice(common)}
    candidates = list(dict.fromkeys(player1_picks + player2_picks))
    return {"resolved": False, "needs_tie_break": True, "candidates": candidates}


def resolve_tie_break_votes(votes: list[str]) -> str:
    counts: dict[str, int] = {}
    for v in votes:
        counts[v] = counts.get(v, 0) + 1
    max_count = max(counts.values())
    winners = [k for k, c in counts.items() if c == max_count]
    return random.choice(winners)


async def submit_vote_picks(db: AsyncSession, room_id: str, user_id: str, picks: list[str]) -> dict:
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room or not room.player2_id:
        raise ValueError("ROOM_NOT_FULL")

    games_result = await db.execute(select(Game))
    game_by_key = {g.key.value: g for g in games_result.scalars().all()}

    for pick in picks:
        if pick not in game_by_key:
            raise ValueError(f"UNKNOWN_GAME:{pick}")
        db.add(GameVote(room_id=room_id, user_id=user_id, game_id=game_by_key[pick].id, round=1))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise ValueError("ALREADY_VOTED")

    votes_result = await db.execute(select(GameVote).where(GameVote.room_id == room_id, GameVote.round == 1))
    all_votes = votes_result.scalars().all()
    game_id_to_key = {g.id: g.key.value for g in game_by_key.values()}
    votes_by_user: dict[str, list[str]] = {}
    for v in all_votes:
        votes_by_user.setdefault(v.user_id, []).append(game_id_to_key[v.game_id])

    if len(votes_by_user) < 2:
        return {"waiting": True}

    p1_picks = votes_by_user.get(room.player1_id, [])
    p2_picks = votes_by_user.get(room.player2_id, [])
    outcome = resolve_game_selection(p1_picks, p2_picks)

    if outcome["resolved"]:
        match, game = await finalize_room_with_game(db, room, outcome["game_key"], MatchMode.RANKED, game_by_key)
        return {"waiting": False, "resolved": True, "game_key": outcome["game_key"], "match_id": match.id, "game_name": game.name}
    return {"waiting": False, "resolved": False, "candidates": outcome["candidates"]}


async def submit_tie_break_vote(db: AsyncSession, room_id: str, user_id: str, game_key: str) -> dict:
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room or not room.player2_id:
        raise ValueError("ROOM_NOT_FULL")

    games_result = await db.execute(select(Game))
    game_by_key = {g.key.value: g for g in games_result.scalars().all()}
    if game_key not in game_by_key:
        raise ValueError("UNKNOWN_GAME")

    db.add(GameVote(room_id=room_id, user_id=user_id, game_id=game_by_key[game_key].id, round=2))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise ValueError("ALREADY_VOTED")

    votes_result = await db.execute(select(GameVote).where(GameVote.room_id == room_id, GameVote.round == 2))
    all_votes = votes_result.scalars().all()
    if len(all_votes) < 2:
        return {"waiting": True}

    game_id_to_key = {g.id: g.key.value for g in game_by_key.values()}
    winner_key = resolve_tie_break_votes([game_id_to_key[v.game_id] for v in all_votes])
    match, game = await finalize_room_with_game(db, room, winner_key, MatchMode.RANKED, game_by_key)
    return {"waiting": False, "game_key": winner_key, "match_id": match.id, "game_name": game.name}


async def finalize_room_with_game(db: AsyncSession, room: Room, game_key: str, mode: MatchMode, game_by_key: dict):
    game = game_by_key[game_key]
    room.game_id = game.id
    room.status = RoomStatus.READY_CHECK
    match = Match(room_id=room.id, game_id=game.id, mode=mode, player1_id=room.player1_id, player2_id=room.player2_id)
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match, game
