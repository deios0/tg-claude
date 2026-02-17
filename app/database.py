from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import load_config
from app.models import Base

engine = None
SessionLocal = None


async def init_db():
    global engine, SessionLocal
    config = load_config()
    engine = create_async_engine(config.database_url, echo=False)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_session() -> AsyncSession:
    return SessionLocal()
