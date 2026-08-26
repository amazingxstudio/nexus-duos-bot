import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, ForeignKey, Enum, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


class RoomStatus(str, enum.Enum):
    WAITING_FOR_PLAYER = "WAITING_FOR_PLAYER"
    VOTING = "VOTING"
    READY_CHECK = "READY_CHECK"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"
    ABANDONED = "ABANDONED"


class MatchResult(str, enum.Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    DRAW = "DRAW"


class MatchMode(str, enum.Enum):
    RANKED = "RANKED"
    PRACTICE_AI = "PRACTICE_AI"


class GameKey(str, enum.Enum):
    """The permanent, final key for each of the 8 mini-games. Every shared
    file (this enum, database.py's migration, seed.py, the engine registry,
    the frontend dispatcher) is wired for all 8 of these from day one — a
    game not being built yet just means its engine.py / *Game.tsx is a
    small "coming soon" placeholder for now (see
    app/games/engine/registry.py and the frontend's GameDispatcher.tsx).
    Building a game later only ever means replacing that one game's two
    files — nothing shared changes.
    """
    CONNECT_FOUR = "CONNECT_FOUR"
    DOTS_AND_BOXES = "DOTS_AND_BOXES"
    QUICK_MATH = "QUICK_MATH"
    TYPING_RACE = "TYPING_RACE"
    GUESS_THE_WORD = "GUESS_THE_WORD"
    MEMORY_RACE = "MEMORY_RACE"
    FIND_THE_DIFFERENT = "FIND_THE_DIFFERENT"
    WORD_CHAIN = "WORD_CHAIN"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str] = mapped_column(String)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    language_code: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    profile: Mapped["Profile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    settings: Mapped["UserSettings"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    nickname: Mapped[str] = mapped_column(String)
    player_id: Mapped[str] = mapped_column(String, unique=True, index=True)

    total_matches: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    total_score: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="profile")


class UserSettings(Base):
    __tablename__ = "settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    show_history_to_all: Mapped[bool] = mapped_column(Boolean, default=True)
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    haptics_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="settings")


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    key: Mapped[GameKey] = mapped_column(Enum(GameKey), unique=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)

    player1_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    player2_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    game_id: Mapped[str | None] = mapped_column(String, ForeignKey("games.id"), nullable=True)
    # Set when a room is created via "quick duel" (tap a game on Home) —
    # skips the 3-pick voting flow entirely once player2 joins.
    preset_game_key: Mapped[GameKey | None] = mapped_column(Enum(GameKey), nullable=True)

    status: Mapped[RoomStatus] = mapped_column(Enum(RoomStatus), default=RoomStatus.WAITING_FOR_PLAYER)
    # The message_id of the "🎮 Room created" DM sent to the creator's
    # Telegram chat when this room was made via the REST routes (create /
    # quick-duel). None for invite/rematch-created rooms, which never get a
    # DM in the first place. Used to delete that message the instant the
    # code becomes unusable — see join_room_route in routes/rooms.py.
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GameVote(Base):
    __tablename__ = "game_votes"
    # One row per (room, user, round, game) — each player casts 3 picks per
    # round (one row per game), so the constraint must include game_id.
    # It previously omitted game_id, which meant a player's 2nd and 3rd pick
    # in the same round both collided with their 1st on (room_id, user_id,
    # round) alone — every real 3-pick submission hit this constraint and
    # failed, which the frontend then showed as an endless "Waiting for
    # opponent..." with no visible error. See database.py's schema-sync for
    # the live-database migration that corrects this on existing deployments.
    __table_args__ = (UniqueConstraint("room_id", "user_id", "round", "game_id", name="uq_game_vote_room_user_round_game"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    room_id: Mapped[str] = mapped_column(String, ForeignKey("rooms.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    game_id: Mapped[str] = mapped_column(String, ForeignKey("games.id"))
    round: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Friend(Base):
    __tablename__ = "friends"
    __table_args__ = (UniqueConstraint("user_id", "friend_id", name="uq_friend_pair"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
    friend_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_id)
    room_id: Mapped[str | None] = mapped_column(String, ForeignKey("rooms.id"), unique=True, nullable=True)
    game_id: Mapped[str] = mapped_column(String, ForeignKey("games.id"))
    mode: Mapped[MatchMode] = mapped_column(Enum(MatchMode), default=MatchMode.RANKED)

    player1_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    player1_score: Mapped[int] = mapped_column(Integer, default=0)
    player1_result: Mapped[MatchResult | None] = mapped_column(Enum(MatchResult), nullable=True)

    player2_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), nullable=True)
    player2_score: Mapped[int] = mapped_column(Integer, default=0)
    player2_result: Mapped[MatchResult | None] = mapped_column(Enum(MatchResult), nullable=True)

    winner_id: Mapped[str | None] = mapped_column(String, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
