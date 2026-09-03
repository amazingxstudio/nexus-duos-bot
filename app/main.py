import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app.cache import ping_redis
from app.bot import bot_application
from app.seed import seed_games
from app.games.ai.seed import seed_ai_bots
from app.routes import auth, games, rooms, profile, history, settings as settings_route, players, messages
from app.socketio_app import sio
from app.background_tasks import start_cleanup_task
import app.sockets  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus_duos")


@asynccontextmanager
async def lifespan(_fastapi_app: FastAPI):
    await init_db()
    logger.info("Database ready")

    async with AsyncSessionLocal() as db:
        await seed_games(db)
        await seed_ai_bots(db)
    logger.info("Games catalog + Practice-vs-AI bot accounts seeded")

    redis_ok = await ping_redis()
    logger.info("🔴 Redis connected" if redis_ok else "⚠️ Redis connection FAILED — check REDIS_URL")

    await bot_application.initialize()
    await bot_application.start()
    await bot_application.updater.start_polling()
    logger.info("🤖 Telegram bot started (polling mode)")

    # Additive: periodic capacity/storage cleanup — see app/cleanup.py.
    # Started as its own background task (like the bot's own polling loop
    # above) so a slow first pass never delays the app becoming ready.
    cleanup_task = start_cleanup_task()
    logger.info("🧹 Background cleanup loop started (every %sm)", settings.CLEANUP_INTERVAL_MINUTES)

    yield

    cleanup_task.cancel()
    await bot_application.updater.stop()
    await bot_application.stop()
    await bot_application.shutdown()


fastapi_app = FastAPI(title="Nexus Duos API", lifespan=lifespan)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapi_app.get("/health")
async def health():
    redis_ok = await ping_redis()
    return {"status": "ok", "redis": "connected" if redis_ok else "disconnected"}


fastapi_app.include_router(auth.router, prefix="/auth", tags=["auth"])
fastapi_app.include_router(games.router, prefix="/games", tags=["games"])
fastapi_app.include_router(rooms.router, prefix="/rooms", tags=["rooms"])
fastapi_app.include_router(profile.router, prefix="/profile", tags=["profile"])
fastapi_app.include_router(history.router, prefix="/history", tags=["history"])
fastapi_app.include_router(settings_route.router, prefix="/settings", tags=["settings"])
fastapi_app.include_router(players.router, prefix="/players", tags=["players"])
fastapi_app.include_router(messages.router, prefix="/messages", tags=["messages"])

app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="socket.io")
