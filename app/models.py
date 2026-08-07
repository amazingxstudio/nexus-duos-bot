import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, ForeignKey, Enum, func
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
    CYBER_DUEL = "CYBER_DUEL"
    NEON_CHESS = "NEON_CHESS"
    CODE_BREAKER = "CODE_BREAKER"
    ARENA_CARDS = "ARENA_CARDS"
    MEMORY_WARFARE = "MEMORY_WARFARE"
    SPEED_TYPING = "SPEED_TYPING"
    TOWER_CONTROL = "TOWER_CONTROL"
    PUZZLE_ARENA = "PUZZLE_ARENA"


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

    status: Mapped[RoomStatus] = mapped_column(Enum(RoomStatus), default=RoomStatus.WAITING_FOR_PLAYER)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
