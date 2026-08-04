import os

import pytest
from fastapi_cache import FastAPICache
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "test-secret-key-for-dev"

from database import Base, get_session
from main import app

# Отключаем rate limiting в тестах
app.state.limiter.enabled = False


# Меняем scope "session" на "function", чтобы engine создавался внутри того же event loop, что и тест
@pytest.fixture(scope="function")
async def engine():
    db_url = os.environ["DATABASE_URL"]
    test_engine = create_async_engine(db_url, echo=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # Расширение для GIN-индексов по тексту
        await conn.execute(sa_text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)

    yield test_engine

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture(scope="function")
async def session(engine):
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as sess:
        yield sess
        await sess.rollback()


@pytest.fixture(scope="function")
async def client(session: AsyncSession):
    async def _override_get_session():
        yield session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def setup_cache():
    """Инициализация in-memory кэша для тестов."""
    from fastapi_cache.backends.inmemory import InMemoryBackend

    FastAPICache.reset()
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache-test")
    yield
    FastAPICache.reset()
