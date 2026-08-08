import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Room, RoomStatus, GameVote, Game, Match, MatchMode
from app.room_code import generate_room_code


async def create_room(db: AsyncSession, player1_id: str) -> Room:
    room = Room(code=generate_room_code(), player1_id=player1_id, status=RoomStatus.WAITING_FOR_PLAYER)
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


async def join_room(db: AsyncSession, code: str, player2_id: str) -> Room:
    result = await db.execute(select(Room).where(Room.code == code))
    room = result.scalar_one_or_none()

    if not room:
        raise ValueError("ROOM_NOT_FOUND")
    if room.status != RoomStatus.WAITING_FOR_PLAYER:
        raise ValueError("ROOM_NOT_JOINABLE")
    if room.player1_id == player2_id:
        raise ValueError("CANNOT_JOIN_OWN_ROOM")

    room.player2_id = player2_id
    room.status = RoomStatus.VOTING
    await db.commit()
    await db.refresh(room)
    return room


def resolve_game_selection(player1_picks: list[str], player2_picks: list[str]) -> dict:
    """
    Each player picks exactly 3 games.
    - 1 common game -> auto-select it
    - multiple common games -> pick one at random
    - 0 common games -> caller must run a tie-break vote across the union of all 6
    """
    common = [g for g in player1_picks if g in player2_picks]

    if len(common) == 1:
        return {"resolved": True, "game_key": common[0]}

    if len(common) > 1:
        return {"resolved": True, "game_key": random.choice(common)}

    candidates = list(dict.fromkeys(player1_picks + player2_picks))  # union, order-preserving
    return {"resolved": False, "needs_tie_break": True, "candidates": candidates}


def resolve_tie_break_votes(votes: list[str]) -> str:
    """Tallies tie-break votes; ties among the leaders resolve randomly."""
    counts: dict[str, int] = {}
    for v in votes:
        counts[v] = counts.get(v, 0) + 1
    max_count = max(counts.values())
    winners = [k for k, c in counts.items() if c == max_count]
    return random.choice(winners)


async def submit_vote_picks(db: AsyncSession, room_id: str, user_id: str, picks: list[str]) -> dict:
    """
    Records a player's 3 picks. If both players have voted, resolves the
    game (auto-select, random among commons, or signals a tie-break is
    needed). Returns a status dict the route can turn into a response.
    """
    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room or not room.player2_id:
        raise ValueError("ROOM_NOT_FULL")

    games_result = await db.execute(select(Game))
    game_by_key = {g.key.value: g for g in games_result.scalars().all()}

    for pick in picks:
        if pick not in game_by_key:
            raise ValueError(f"UNKNOWN_GAME:{pick}")
        vote = GameVote(room_id=room_id, user_id=user_id, game_id=game_by_key[pick].id, round=1)
        db.add(vote)
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

    vote = GameVote(room_id=room_id, user_id=user_id, game_id=game_by_key[game_key].id, round=2)
    db.add(vote)
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
