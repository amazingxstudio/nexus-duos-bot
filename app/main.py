import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.bot import build_bot_application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus_duos")

bot_app = build_bot_application()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logger.info("Database ready")

    # Run the Telegram bot's polling loop alongside the API server.
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("🤖 Telegram bot started (polling mode)")

    yield

    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


app = FastAPI(title="Nexus Duos API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Routers are added here as each batch is built:
# from app.routes import auth, profile, rooms, games, history, settings as settings_route, match
# app.include_router(auth.router, prefix="/auth", tags=["auth"])
# app.include_router(profile.router, prefix="/profile", tags=["profile"])
# ... etc
