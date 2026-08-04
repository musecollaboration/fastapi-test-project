import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_permissions_endpoint(client: AsyncClient):
    """Проверка эндпоинта /admin/permissions для обычного пользователя."""
    # Регистрируем пользователя
    await client.post(
        "/register",
        json={
            "username": "rbac_user",
            "password": "testpass123",
            "email": "rbac@example.com",
            "full_name": "RBAC User",
        },
    )

    # Получаем токен
    token_resp = await client.post(
        "/token",
        data={"username": "rbac_user", "password": "testpass123"},
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]

    # Проверяем permissions
    auth_headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/admin/permissions", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["role"] == "user"
    assert "items:read" in data["permissions"]
    assert data["permissions_count"] > 0


@pytest.mark.asyncio
async def test_admin_users_requires_admin(client: AsyncClient):
    """Проверка что /admin/users доступен только для администраторов."""
    # Регистрируем обычного пользователя
    await client.post(
        "/register",
        json={
            "username": "rbac_test_user",
            "password": "testpass123",
            "email": "rbac_test@example.com",
            "full_name": "RBAC Test",
        },
    )

    # Получаем токен
    token_resp = await client.post(
        "/token",
        data={"username": "rbac_test_user", "password": "testpass123"},
    )
    assert token_resp.status_code == 200
    token = token_resp.json()["access_token"]

    # Пытаемся получить список пользователей (должно быть 403)
    auth_headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/admin/users", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_role_permissions_mapping():
    """Проверка маппинга ролей и permissions."""
    from auth import get_user_permissions

    user_perms = get_user_permissions("user")
    assert "items:read" in user_perms
    assert "items:create" in user_perms
    assert "items:delete:any" not in user_perms  # user не может удалять любые

    moderator_perms = get_user_permissions("moderator")
    assert "items:delete:any" in moderator_perms
    assert "users:read" in moderator_perms

    admin_perms = get_user_permissions("admin")
    assert "users:delete" in admin_perms
    assert "system:config" in admin_perms
    assert len(admin_perms) >= len(moderator_perms)
    assert len(moderator_perms) >= len(user_perms)
