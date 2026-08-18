import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateColumn

from app.config import settings

logger = logging.getLogger("nexus_duos.db")

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


def _sync_missing_columns(sync_conn) -> None:
    """Best-effort, additive-only schema sync.

    `Base.metadata.create_all()` only creates tables that don't exist yet —
    it silently does nothing if a table already exists but a model gained a
    new column since (exactly what happened with rooms.preset_game_key,
    which crashed every room creation with UndefinedColumnError). This walks
    every model table that already exists in the live database and adds any
    column present on the model but missing from the table.

    This is NOT a replacement for real migrations — it never drops, renames,
    or alters an existing column, only adds ones that are missing. Switch to
    Alembic once the schema needs anything beyond that.
    """
    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # brand-new table — create_all() already handled it

        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            try:
                ddl = CreateColumn(column).compile(dialect=sync_conn.dialect)
                sync_conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}'))
                logger.warning("Schema sync: added missing column %s.%s", table.name, column.name)
            except Exception:
                logger.exception("Schema sync: failed to add column %s.%s", table.name, column.name)


async def init_db():
    """Creates any tables that don't exist yet, then additively syncs any
    columns a model declares that the live table is missing (see
    _sync_missing_columns). Switch to Alembic migrations once the schema
    stabilizes."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.run_sync(_sync_missing_columns)
        except Exception:
            # Never let a schema-sync hiccup take the whole API down — the
            # tables from create_all() above are still usable.
            logger.exception("Schema sync failed — continuing with existing schema")
