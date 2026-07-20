import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.mark.asyncio
async def test_root():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "API is running"}


@pytest.mark.asyncio
async def test_create_item():
    payload = {"name": "Test item", "description": "Test description"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/items", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test item"
    assert data["description"] == "Test description"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_get_items():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Создадим элемент, чтобы список не был пустым
        await ac.post("/items", json={"name": "Item for list"})
        response = await ac.get("/items")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio
async def test_get_item_not_found():
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/items/{fake_uuid}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}


@pytest.mark.asyncio
async def test_delete_item():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Создаём элемент
        create_resp = await ac.post("/items", json={"name": "To be deleted"})
        assert create_resp.status_code == 201
        item_id = create_resp.json()["id"]
        # Удаляем его
        delete_resp = await ac.delete(f"/items/{item_id}")
        assert delete_resp.status_code == 200
        assert delete_resp.json() == {"message": f"Item {item_id} deleted"}
        # Проверяем, что его больше нет
        get_resp = await ac.get(f"/items/{item_id}")
        assert get_resp.status_code == 404
