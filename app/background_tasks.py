"""Starts/stops the single periodic cleanup loop — see app/cleanup.py for
what each pass does. Mirrors bot.py's own polling-task lifecycle (create
the task in main.py's lifespan startup, cancel it on shutdown) rather than
pulling in an external scheduler dependency the free tier doesn't need.
"""

import asyncio
import logging

from app.config import settings
from app.database import AsyncSessionLocal
from app.cleanup import run_cleanup_pass

logger = logging.getLogger("nexus_duos.background")


async def _cleanup_loop():
    interval_seconds = max(settings.CLEANUP_INTERVAL_MINUTES, 1) * 60
    while True:
        try:
            await run_cleanup_pass(AsyncSessionLocal)
        except Exception:
            # Belt-and-suspenders — run_cleanup_pass already catches per-step,
            # but an unexpected error here must never kill the loop.
            logger.exception("Cleanup loop iteration failed — will retry next interval")
        await asyncio.sleep(interval_seconds)


def start_cleanup_task() -> asyncio.Task:
    return asyncio.create_task(_cleanup_loop())
