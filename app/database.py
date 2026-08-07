from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Render/most managed Postgres URLs come as postgresql://... — asyncpg needs postgresql+asyncpg://
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(_db_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    """Creates tables if they don't exist. Fine for getting started —
    switch to Alembic migrations once the schema stabilizes."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
