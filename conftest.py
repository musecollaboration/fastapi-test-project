import os

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database import Base, get_session
from main import app


# Меняем scope с "session" на "function", чтобы engine создавался внутри того же event loop, что и тест
@pytest.fixture(scope="function")
async def engine():
    db_url = os.environ["DATABASE_URL"]
    test_engine = create_async_engine(db_url, echo=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
