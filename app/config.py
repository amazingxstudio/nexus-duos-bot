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

    @property
    def cors_origins(self) -> list[str]:
        if self.CORS_ORIGINS:
            return [o.strip() for o in self.CORS_ORIGINS.split(",")]
        return [self.CLIENT_URL]


settings = Settings()  # fails fast at import time if required vars are missing
