# rbac.py - Role-Based Access Control

from enum import Enum
from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel

from auth import get_current_user_stateless

# ---------- Перечисление ролей ----------


class UserRole(str, Enum):
    """Допустимые роли в системе."""
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"

    def __str__(self) -> str:
        return self.value


# ---------- Зависимости для проверки ролей ----------

def require_role(allowed_roles: list[UserRole]):
    """
    Создать зависимость для проверки роли пользователя.

    Usage:
        @app.get("/admin")
        async def admin_endpoint(
            current_user: Annotated[dict, Depends(require_role([UserRole.ADMIN]))]
        ):
            ...
    """
    async def checker(user_data: Annotated[dict, Depends(get_current_user_stateless)]):
        user_role = UserRole(user_data.get("role", "user"))
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Требуется одна из ролей: {[r.value for r in allowed_roles]}",
            )
        return user_data
    return checker


def require_admin(
    user_data: Annotated[dict, Depends(require_role([UserRole.ADMIN]))]
):
    """Зависимость для проверки роли администратора."""
    return user_data


def require_moderator_or_admin(
    user_data: Annotated[dict, Depends(require_role([UserRole.MODERATOR, UserRole.ADMIN]))]
):
    """Зависимость для проверки роли модератора или администратора."""
    return user_data


# ---------- Зависимости для проверки прав ----------

def require_permission(permission: str):
    """
    Создать зависимость для проверки разрешения (permission).

    Usage:
        @app.delete("/items/{item_id}")
        async def delete_item(
            item_id: UUID,
            current_user: Annotated[dict, Depends(require_permission("items:delete"))]
        ):
            ...
    """
    async def checker(user_data: Annotated[dict, Depends(get_current_user_stateless)]):
        permissions = user_data.get("permissions", [])
        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Требуется разрешение: {permission}",
            )
        return user_data
    return checker


# ---------- Pydantic-модели ----------

class UserRBAC(BaseModel):
    """Данные пользователя для RBAC."""
    sub: str
    user_id: str | None = None
    role: str = "user"
    email: str | None = None
    permissions: list[str] = []

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN.value

    @property
    def is_moderator(self) -> bool:
        return self.role == UserRole.MODERATOR.value

    @property
    def is_user(self) -> bool:
        return self.role == UserRole.USER.value


# ---------- Предустановленные permissions для ролей ----------

ROLE_PERMISSIONS = {
    UserRole.USER.value: [
        "items:read",
        "items:create",
        "items:update:own",
        "items:delete:own",
        "profile:read",
        "profile:update",
    ],
    UserRole.MODERATOR.value: [
        "items:read",
        "items:create",
        "items:update:any",
        "items:delete:any",
        "profile:read",
        "profile:update",
        "users:read",
        "users:update",
    ],
    UserRole.ADMIN.value: [
        "items:read",
        "items:create",
        "items:update:any",
        "items:delete:any",
        "profile:read",
        "profile:update",
        "users:read",
        "users:create",
        "users:update",
        "users:delete",
        "users:role",
        "system:config",
    ],
}


def get_role_permissions(role: str) -> list[str]:
    """Получить список разрешений для роли."""
    return ROLE_PERMISSIONS.get(role, [])
