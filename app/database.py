import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.schema import CreateColumn

from app.config import settings

logger = logging.getLogger("nexus_duos.db")

# Neon's connection string looks like:
#   postgresql://user:pass@ep-xxx.neon.tech/db?sslmode=require&channel_binding=require
# asyncpg (unlike psycopg2) does NOT accept "sslmode" or "channel_binding" as
# connect kwargs — passing them through raises
# `TypeError: connect() got an unexpected keyword argument 'sslmode'` at the
# very first query. So instead of a plain string-replace, this parses the
# URL, strips every query param (whatever the provider put there), and
# swaps the driver to asyncpg — then SSL is requested the way asyncpg
# actually understands it, via connect_args below. This still works
# unchanged for a plain Render/local Postgres URL with no query params.
_url = make_url(settings.DATABASE_URL).set(drivername="postgresql+asyncpg", query={})
_is_neon = "neon.tech" in settings.DATABASE_URL

# Neon's "-pooler" endpoint (the one their dashboard hands you by default)
# routes through PgBouncer in transaction-pooling mode, which does not
# support server-side prepared statements — asyncpg uses those by default
# for every query, so without this you'd hit
# `DuplicatePreparedStatementError: prepared statement "__asyncpg_stmt_1__"
# already exists` the moment two requests overlap. statement_cache_size=0
# tells asyncpg to never prepare-and-cache, which is required behind a
# transaction-mode pooler (and harmless — just a little slower per query —
# against a direct, non-pooled connection).
_connect_args = {"ssl": "require", "statement_cache_size": 0} if _is_neon else {}

engine = create_async_engine(
    _url,
    echo=False,
    pool_pre_ping=True,  # Neon can idle its compute down; this discards a
                         # stale connection and reconnects instead of erroring.
    pool_recycle=300,
    connect_args=_connect_args,
)
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


def _fix_game_vote_constraint(sync_conn) -> None:
    """One-off, idempotent repair for a wrong UNIQUE constraint.

    game_votes originally had UNIQUE(room_id, user_id, round) — but each
    round is 3 rows per user (one per pick), so that constraint rejected
    every real submission on its 2nd row with an IntegrityError. The route
    swallowed that as "ALREADY_VOTED", and the frontend had no error
    handling on that call, so players just saw "Waiting for opponent..."
    forever. The model now declares the correct
    UNIQUE(room_id, user_id, round, game_id); this brings an existing
    database's constraint in line with it. Safe to run on every boot —
    it's a no-op once the correct constraint is in place.
    """
    inspector = inspect(sync_conn)
    if "game_votes" not in inspector.get_table_names():
        return

    constraints = inspector.get_unique_constraints("game_votes")
    wanted = {"room_id", "user_id", "round", "game_id"}

    if any(set(c.get("column_names") or []) == wanted for c in constraints):
        return  # already correct

    for c in constraints:
        if set(c.get("column_names") or []) == {"room_id", "user_id", "round"}:
            try:
                sync_conn.execute(text(f'ALTER TABLE "game_votes" DROP CONSTRAINT "{c["name"]}"'))
                logger.warning("Schema fix: dropped incorrect constraint %s on game_votes", c["name"])
            except Exception:
                logger.exception("Schema fix: failed to drop constraint %s", c["name"])

    try:
        sync_conn.execute(text(
            'ALTER TABLE "game_votes" ADD CONSTRAINT "uq_game_vote_room_user_round_game" '
            'UNIQUE (room_id, user_id, round, game_id)'
        ))
        logger.warning("Schema fix: added corrected unique constraint on game_votes")
    except Exception:
        logger.exception("Schema fix: failed to add corrected constraint on game_votes")


def _rename_enum_values(sync_conn) -> None:
    """One-off, idempotent renames for all 8 gamekey enum values — the
    entire original mini-game lineup is being swapped out for a new one,
    in batches, but the *rename list* is final and complete from day one so
    this function never needs editing again. Safe to run on every boot: a
    pair is only renamed if the old label is still present in the live type
    and the new one isn't yet — a no-op on a fresh database (create_all()
    already makes the type with only the new names) and a no-op again on
    every boot after it's applied once. ALTER TYPE ... RENAME VALUE is
    transaction-safe in Postgres, so this runs inside the same transaction
    as everything else here.
    """
    renames = [
        ("ARENA_CARDS", "CONNECT_FOUR"),
        ("CYBER_DUEL", "DOTS_AND_BOXES"),
        ("TOWER_CONTROL", "QUICK_MATH"),
        ("SPEED_TYPING", "TYPING_RACE"),
        ("CODE_BREAKER", "GUESS_THE_WORD"),
        ("MEMORY_WARFARE", "MEMORY_RACE"),
        ("NEON_CHESS", "FIND_THE_DIFFERENT"),
        ("PUZZLE_ARENA", "WORD_CHAIN"),
    ]
    for old, new_name in renames:
        try:
            old_exists = sync_conn.execute(text(
                "SELECT 1 FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid "
                "WHERE t.typname = 'gamekey' AND e.enumlabel = :old"
            ), {"old": old}).first()
            if not old_exists:
                continue
            new_exists = sync_conn.execute(text(
                "SELECT 1 FROM pg_enum e JOIN pg_type t ON e.enumtypid = t.oid "
                "WHERE t.typname = 'gamekey' AND e.enumlabel = :new"
            ), {"new": new_name}).first()
            if new_exists:
                continue
            sync_conn.execute(text(f"ALTER TYPE gamekey RENAME VALUE '{old}' TO '{new_name}'"))
            logger.warning("Schema fix: renamed gamekey enum value %s -> %s", old, new_name)
        except Exception:
            logger.exception("Schema fix: failed to rename gamekey enum value %s -> %s", old, new_name)


async def init_db():
    """Creates any tables that don't exist yet, then additively syncs any
    columns a model declares that the live table is missing, then applies
    the one-off game_votes constraint repair and any pending gamekey enum
    renames. Switch to Alembic migrations once the schema stabilizes."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        try:
            await conn.run_sync(_sync_missing_columns)
        except Exception:
            logger.exception("Schema sync failed — continuing with existing schema")
        try:
            await conn.run_sync(_fix_game_vote_constraint)
        except Exception:
            logger.exception("game_votes constraint fix failed — continuing with existing schema")
        try:
            await conn.run_sync(_rename_enum_values)
        except Exception:
            logger.exception("gamekey enum rename failed — continuing with existing schema")
