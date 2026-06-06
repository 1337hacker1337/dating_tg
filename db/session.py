from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings

_dsn = settings.db_dsn.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(_dsn, echo=False, pool_size=10, max_overflow=5)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


async def get_session() -> AsyncSession:
    """Dependency для FastAPI."""
    async with AsyncSessionFactory() as session:
        yield session
