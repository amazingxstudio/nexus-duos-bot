from pydantic import BaseModel, Field


# ---- Auth ----

class TelegramLoginRequest(BaseModel):
    init_data: str = Field(..., min_length=1)


class ProfileOut(BaseModel):
    id: str
    nickname: str
    player_id: str
    total_matches: int
    wins: int
    losses: int
    draws: int
    total_score: int

    class Config:
        from_attributes = True


class SettingsOut(BaseModel):
    show_history_to_all: bool
    sound_enabled: bool
    haptics_enabled: bool

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    id: str
    telegram_id: str
    first_name: str
    username: str | None
    photo_url: str | None
    profile: ProfileOut | None = None
    settings: SettingsOut | None = None


class AuthResponse(BaseModel):
    token: str
    user: UserOut


# ---- Profile ----

class UpdateNicknameRequest(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=20)


class PublicProfileOut(BaseModel):
    nickname: str
    player_id: str
    photo_url: str | None
    total_matches: int
    wins: int
    losses: int
    draws: int
    win_rate: int
    total_score: int
    history_visible: bool


# ---- Games ----

class GameOut(BaseModel):
    key: str
    name: str
    description: str

    class Config:
        from_attributes = True


# ---- Rooms ----

class SubmitPicksRequest(BaseModel):
    picks: list[str] = Field(..., min_length=3, max_length=3)


class SubmitTieBreakRequest(BaseModel):
    game_key: str


class RoomPlayerOut(BaseModel):
    id: str
    photo_url: str | None
    nickname: str | None = None
    player_id: str | None = None


class RoomOut(BaseModel):
    id: str
    code: str
    status: str
    player1: RoomPlayerOut
    player2: RoomPlayerOut | None = None
    game_key: str | None = None


class JoinRoomRequest(BaseModel):
    code: str = Field(..., min_length=1)
