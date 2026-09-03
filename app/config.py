from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    NODE_ENV: str = "development"
    PORT: int = 4000
    CLIENT_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str | None = None

    DATABASE_URL: str
    REDIS_URL: str

    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBAPP_URL: str

    JWT_SECRET: str
    JWT_EXPIRES_MINUTES: int = 60 * 24 * 7  # 7 days
    TELEGRAM_AUTH_MAX_AGE: int = 86400  # seconds

    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_MAX: int = 120

    # If set, this numeric Telegram user id is auto-recognized as the
    # creator/admin on every login or /start — checked by id, never
    # username, since usernames can change or be removed.
    CREATOR_TELEGRAM_ID: int | None = None

    # ---- Free-tier capacity gate (app/capacity.py) ----
    # Render's free tier (0.1 CPU / 512MB) plus Neon (100 CU-hr/month) and
    # Upstash (500K commands/month) can only sustain a small, fixed number
    # of concurrent matches before Redis/DB load or the dyno's own memory
    # starts tipping over. This caps how many rooms may be "in flight"
    # (created but not yet FINISHED/ABANDONED) at once. Raise it only
    # after actually checking Render memory and Neon compute-hour usage
    # under load — this is a guess-and-adjust knob, not a measured limit.
    MAX_CONCURRENT_MATCHES: int = 40

    # ---- Background cleanup (app/cleanup.py, app/background_tasks.py) ----
    # How often (minutes) the periodic cleanup loop runs — sweeps
    # long-abandoned rooms and expired direct messages so Neon storage
    # doesn't grow unbounded.
    CLEANUP_INTERVAL_MINUTES: int = 30
    # A room stuck in WAITING_FOR_PLAYER / VOTING / READY_CHECK longer
    # than this (nobody ever joined, voting never finished, a player
    # closed the app mid-flow) is swept up as ABANDONED so it stops
    # counting against MAX_CONCURRENT_MATCHES forever. IN_PROGRESS rooms
    # are never touched by this — a live match ending is match_runner.py's
    # job, not the cleanup sweep's.
    STALE_ROOM_HOURS: int = 6

    # ---- Creator /stats bot command (app/bot.py) ----
    # Neon's free-tier storage cap in MB, used only to compute the "DB
    # storage usage %" the creator's /stats command reports — never
    # enforced, only reported. Update this if the Neon plan changes.
    NEON_STORAGE_LIMIT_MB: int = 512

    @property
    def cors_origins(self) -> list[str]:
        if self.CORS_ORIGINS:
            return [o.strip() for o in self.CORS_ORIGINS.split(",")]
        return [self.CLIENT_URL]


settings = Settings()  # fails fast at import time if required vars are missing
