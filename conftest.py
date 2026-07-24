import os
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text
from database import Base

# Устанавливаем DATABASE_URL для тестов, если не задан
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://fastapi_user:fastapi_pass@127.0.0.1:5432/fastapi_db")


@pytest.fixture(scope="session")
async def engine():
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def session(engine):
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as sess:
        yield sess
        await sess.rollback()
    # Очистка таблиц после теста
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE items RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="function")
async def client():
    from httpx import AsyncClient, ASGITransport
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
