from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models import Item as ItemModel


@pytest.fixture(scope="function")
async def auth_client(client: AsyncClient) -> AsyncClient:
    """Создаёт авторизованного клиента для тестов."""
    # 1. Регистрируем тестового пользователя
    register_resp = await client.post(
        "/register",
        json={
            "username": "testuser",
            "password": "testpass123",
            "email": "test@example.com",
            "full_name": "Test User",
        },
    )
    assert register_resp.status_code == 200

    # 2. Получаем JWT-токен
    token_resp = await client.post(
        "/token",
        data={"username": "testuser", "password": "testpass123"},
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]

    # 3. Создаём клиент с заголовком авторизации
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert isinstance(data["message"], str)


@pytest.mark.asyncio
async def test_create_item(auth_client: AsyncClient, session: AsyncSession):
    payload = {"name": "Test item", "description": "Test description"}
    response = await auth_client.post("/items", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test item"
    assert data["description"] == "Test description"
    assert "id" in data
    assert "created_at" in data
    item = await session.get(ItemModel, UUID(data["id"]))
    assert item is not None
    assert item.name == "Test item"


@pytest.mark.asyncio
async def test_get_items(auth_client: AsyncClient):
    create_resp = await auth_client.post("/items", json={"name": "Item for list"})
    assert create_resp.status_code == 201
    response = await auth_client.get("/items")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    found = any(item["name"] == "Item for list" for item in data)
    assert found


@pytest.mark.asyncio
async def test_get_item_not_found(auth_client: AsyncClient):
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    response = await auth_client.get(f"/items/{fake_uuid}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}


@pytest.mark.asyncio
async def test_get_item_by_id(auth_client: AsyncClient):
    create_resp = await auth_client.post("/items", json={"name": "Get by id"})
    assert create_resp.status_code == 201
    item_id = create_resp.json()["id"]
    response = await auth_client.get(f"/items/{item_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == item_id
    assert data["name"] == "Get by id"


@pytest.mark.asyncio
async def test_update_item(auth_client: AsyncClient, session: AsyncSession):
    create_resp = await auth_client.post("/items", json={"name": "Old name"})
    assert create_resp.status_code == 201
    item_id = create_resp.json()["id"]
    payload = {"name": "New name", "description": "Updated desc"}
    update_resp = await auth_client.put(f"/items/{item_id}", json=payload)
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["name"] == "New name"
    assert data["description"] == "Updated desc"
    item = await session.get(ItemModel, UUID(item_id))
    assert item is not None
    assert item.name == "New name"


@pytest.mark.asyncio
async def test_delete_item(auth_client: AsyncClient, session: AsyncSession):
    create_resp = await auth_client.post("/items", json={"name": "To delete"})
    assert create_resp.status_code == 201
    item_id = create_resp.json()["id"]
    delete_resp = await auth_client.delete(f"/items/{item_id}")
    assert delete_resp.status_code == 204
    item = await session.get(ItemModel, UUID(item_id))
    assert item is None


@pytest.mark.asyncio
async def test_stateless_me(client: AsyncClient):
    """Проверяет, что stateless-маршрут возвращает данные из JWT-токена."""
    from main import app

    # Регистрируем пользователя
    await client.post(
        "/register",
        json={
            "username": "statelesstest",
            "password": "testpass123",
            "email": "stateless@example.com",
            "full_name": "Stateless Test",
        },
    )
    # Получаем токен
    token_resp = await client.post(
        "/token",
        data={"username": "statelesstest", "password": "testpass123"},
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]

    # Создаём новый клиент с заголовком авторизации
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        test_client.headers["Authorization"] = f"Bearer {token}"
        response = await test_client.get("/me/stateless")
        assert response.status_code == 200
        data = response.json()
        assert data["sub"] == "statelesstest"
        assert data["role"] == "user"
        assert "user_id" in data
        assert data["email"] == "stateless@example.com"


@pytest.mark.asyncio
async def test_token_contains_user_data(client: AsyncClient):
    """Проверяет, что access-токен содержит user_id, role, email."""
    # Регистрируем пользователя
    await client.post(
        "/register",
        json={
            "username": "tokentest",
            "password": "testpass123",
            "email": "token@example.com",
            "full_name": "Token Test",
        },
    )
    # Получаем токен
    token_resp = await client.post(
        "/token",
        data={"username": "tokentest", "password": "testpass123"},
    )
    assert token_resp.status_code == 200
    access_token = token_resp.json()["access_token"]
    refresh_token = token_resp.json()["refresh_token"]

    # Декодируем и проверяем payload
    from jwt import decode

    from auth import ALGORITHM, _get_secret_key

    access_payload = decode(access_token, _get_secret_key(), algorithms=[ALGORITHM])
    assert access_payload["sub"] == "tokentest"
    assert "user_id" in access_payload
    assert access_payload["role"] == "user"
    assert access_payload["email"] == "token@example.com"

    refresh_payload = decode(refresh_token, _get_secret_key(), algorithms=[ALGORITHM])
    assert refresh_payload["sub"] == "tokentest"
    assert "user_id" in refresh_payload
    assert refresh_payload["role"] == "user"
    assert refresh_payload["email"] == "token@example.com"
