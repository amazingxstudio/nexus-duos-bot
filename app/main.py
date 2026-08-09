import logging
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, AsyncSessionLocal
from app.cache import ping_redis
from app.bot import build_bot_application
from app.seed import seed_games
from app.routes import auth, games, rooms
from app.socketio_app import sio
import app.sockets  # noqa: F401 — imported for its side effect of registering @sio.on handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus_duos")

bot_app = build_bot_application()


@asynccontextmanager
async def lifespan(_fastapi_app: FastAPI):
    await init_db()
    logger.info("Database ready")

    async with AsyncSessionLocal() as db:
        await seed_games(db)
    logger.info("Games catalog seeded")

    redis_ok = await ping_redis()
    logger.info("🔴 Redis connected" if redis_ok else "⚠️ Redis connection FAILED — check REDIS_URL")

    # Run the Telegram bot's polling loop alongside the API server.
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("🤖 Telegram bot started (polling mode)")

    yield

    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


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

# Routers still to come in later batches:
# from app.routes import profile, history, settings as settings_route, match

# Wrap the FastAPI app with the Socket.IO ASGI app. Everything that isn't a
# /socket.io/ request passes straight through to FastAPI unchanged — so
# /health, /docs, /auth, /games, /rooms all keep working exactly as before.
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="socket.io")
