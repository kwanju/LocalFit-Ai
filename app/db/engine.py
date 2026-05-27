from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None:
        from app.config import load_config

        config = load_config()
        db_path = Path(config.db.path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        _session_factory = async_sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _engine


async def init_db(engine: AsyncEngine | None = None) -> None:
    """Create all tables and seed initial data.

    Accepts an optional engine for test isolation (bypasses config.yaml loading).
    """
    import app.db.models  # noqa: F401 — registers all SQLModel metadata

    if engine is None:
        engine = _get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA synchronous=NORMAL"))

    await _seed_exercises(engine)


async def _seed_exercises(engine: AsyncEngine) -> None:
    from sqlmodel import select

    from app.db.models import EXERCISE_SEED, Exercise

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        result = await session.exec(select(Exercise))
        if result.first() is not None:
            return
        for data in EXERCISE_SEED:
            session.add(Exercise(**data))
        await session.commit()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends-compatible async session generator."""
    _get_engine()
    async with _session_factory() as session:  # type: ignore[misc]
        yield session
