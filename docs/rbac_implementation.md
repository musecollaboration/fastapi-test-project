# RBAC (Role-Based Access Control) - Внедрение ролевой модели

**Дата:** 2026-08-03  
**Статус:** ✅ **Реализовано**

---

## 📋 Содержание

- [Обзор](#обзор)
- [Архитектура RBAC](#архитектура-rbac)
- [Роли и разрешения](#роли-и-разрешения)
- [API Reference](#api-reference)
- [Использование в коде](#использование-в-коде)
- [Тесты](#тесты)
- [Безопасность](#безопасность)

---

## Обзор

RBAC (Role-Based Access Control) — модель контроля доступа, при которой права определяются ролью пользователя.

### Что реализовано:

✅ **3 роли:** `user`, `moderator`, `admin`  
✅ **Автоматическое назначение permissions** при создании токена  
✅ **Stateless-проверка ролей** без обращения к БД  
✅ **Admin-эндпоинты** для управления пользователями  
✅ **Проверка прав** на уровне эндпоинтов  
✅ **Тесты** для всех сценариев

---

## Архитектура RBAC

### Схема работы:

```
┌─────────────────────────────────────────────────────────────┐
│                      Регистрация                              │
│                                                              │
│  1. Пользователь создаётся с role="user" по умолчанию        │
│  2. get_user_permissions(role) → список permissions         │
│  3. Permissions сохраняются в JWT-токене                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Авторизация                              │
│                                                              │
│  1. JWT декодируется → извлекаются role + permissions       │
│  2. Зависимость проверяет роль (без БД!)                    │
│  3. Если роль подходит → доступ разрешён                    │
│  4. Если роль не подходит → 403 Forbidden                   │
└─────────────────────────────────────────────────────────────┘
```

### Компоненты:

```
├── auth.py
│   ├── get_user_permissions(role)  →获取权限列表
│   └── 创建token时包含permissions
│
├── rbac.py                         (новая)
│   ├── UserRole enum
│   ├── require_role()              → проверка роли
│   ├── require_admin()             → проверка админа
│   └── ROLE_PERMISSIONS            → маппинг ролей
│
└── main.py
    ├── /admin/users                → admin only
    ├── /admin/users/{username}     → admin only
    ├── /admin/users/{username}/role → admin only
    └── /admin/permissions          → all users
```

---

## Роли и разрешения

### Таблица прав:

| Permission | User | Moderator | Admin |
|------------|------|-----------|-------|
| `items:read` | ✅ | ✅ | ✅ |
| `items:create` | ✅ | ✅ | ✅ |
| `items:update:own` | ✅ | - | - |
| `items:update:any` | ❌ | ✅ | ✅ |
| `items:delete:own` | ✅ | - | - |
| `items:delete:any` | ❌ | ✅ | ✅ |
| `profile:read` | ✅ | ✅ | ✅ |
| `profile:update` | ✅ | ✅ | ✅ |
| `users:read` | ❌ | ✅ | ✅ |
| `users:create` | ❌ | ❌ | ✅ |
| `users:update` | ❌ | ✅ | ✅ |
| `users:delete` | ❌ | ❌ | ✅ |
| `users:role` | ❌ | ❌ | ✅ |
| `system:config` | ❌ | ❌ | ✅ |

### Иерархия ролей:

```
user (6 permissions)
  ↓
moderator (8 permissions)
  ↓
admin (12 permissions)
```

---

## API Reference

### 1. Получить свои права

```http
GET /admin/permissions
Authorization: Bearer <token>

Response 200:
{
  "role": "user",
  "permissions": [
    "items:read",
    "items:create",
    "items:update:own",
    "items:delete:own",
    "profile:read",
    "profile:update"
  ],
  "permissions_count": 6
}
```

### 2. Список пользователей (только admin)

```http
GET /admin/users
Authorization: Bearer <admin_token>

Response 200:
[
  {
    "id": "uuid",
    "username": "john",
    "email": "john@example.com",
    "role": "user",
    "disabled": false,
    "created_at": "2026-08-03T16:00:00"
  }
]

Response 403 (если не admin):
{
  "detail": "Доступно только для администраторов"
}
```

### 3. Получить пользователя по username

```http
GET /admin/users/{username}
Authorization: Bearer <admin_token>

Response 200:
{
  "id": "uuid",
  "username": "john",
  "email": "john@example.com",
  "role": "user"
}
```

### 4. Обновить роль пользователя

```http
PUT /admin/users/{username}/role
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "username": "john",
  "role": "moderator"
}

Response 200:
{
  "id": "uuid",
  "username": "john",
  "role": "moderator"
}

Response 400 (невалидная роль):
{
  "detail": "Недопустимая роль. Допустимые: ['user', 'moderator', 'admin']"
}
```

### 5. Удалить пользователя

```http
DELETE /admin/users/{username}
Authorization: Bearer <admin_token>

Response 204 (No Content)
```

---

## Использование в коде

### 1. Зависимость для проверки роли

```python
from rbac import UserRole
from fastapi import Depends

@app.get("/protected")
async def protected_endpoint(
    user_data: Annotated[dict, Depends(require_role([UserRole.ADMIN]))]
):
    # user_data содержит: sub, user_id, role, email, permissions
    return {"message": f"Hello admin {user_data['sub']}"}
```

### 2. Быстрая проверка админа

```python
from rbac import require_admin

@app.get("/admin/dashboard")
async def admin_dashboard(
    user_data: Annotated[dict, Depends(require_admin)]
):
    return {"admin": user_data["sub"]}
```

### 3. Проверка модератора или админа

```python
from rbac import require_moderator_or_admin

@app.delete("/items/{item_id}")
async def delete_item(
    item_id: UUID,
    user_data: Annotated[dict, Depends(require_moderator_or_admin)]
):
    # Только moderator или admin могут удалять
    return {"deleted": item_id}
```

### 4. Проверка permissions

```python
from rbac import require_permission

@app.put("/items/{item_id}")
async def update_item(
    item_id: UUID,
    user_data: Annotated[dict, Depends(require_permission("items:update:any"))]
):
    # Только с permission items:update:any
    return {"updated": item_id}
```

---

## Тесты

### Структура тестов:

**Файл:** `tests/test_rbac.py`

| Тест | Что проверяет |
|------|---------------|
| `test_admin_permissions_endpoint` | Пользователь может получить свои права |
| `test_admin_users_requires_admin` | `/admin/users` доступен только админам |
| `test_role_permissions_mapping` | Маппинг ролей и permissions корректен |

### Запуск тестов:

```bash
source .venv/bin/activate
python -m pytest tests/test_rbac.py -v
```

**Результат:** 3 passed

---

## Безопасность

### ✅ Что защищено:

1. **Stateless-проверка** — не требует обращения к БД
2. **JWT-подпись** — токены невозможно подделать
3. **Role validation** — только валидные роли допускаются
4. **403 Forbidden** — чёткий ответ при отсутствии прав
5. **Logging** — все изменения ролей логируются

### ⚠️ Рекомендации на будущее:

1. **Permission-based access** — для критичных операций проверять permissions, а не role
2. **Ownership check** — проверять что пользователь владеет ресурсом
3. **Rate limiting** — на admin-эндпоинтах
4. **Audit log** — логировать все изменения прав
5. **Session management** — инвалидация токенов при смене роли

---

## Примеры использования

### Сценарий 1: Обычный пользователь

```python
# Пользователь входит
POST /token
→ access_token (role: "user", permissions: [...])

# Получает свои права
GET /admin/permissions
→ {"role": "user", "permissions_count": 6}

# Не может получить список пользователей
GET /admin/users
→ 403 Forbidden
```

### Сценарий 2: Администратор

```python
# Админ входит
POST /token
→ access_token (role: "admin", permissions: [...])

# Получает список пользователей
GET /admin/users
→ [user1, user2, ...]

# Меняет роль пользователя
PUT /admin/users/john/role
→ {"username": "john", "role": "moderator"}

# Проверяет свои права
GET /admin/permissions
→ {"role": "admin", "permissions_count": 12}
```

---

## Файлы

| Файл | Назначение |
|------|------------|
| `rbac.py` | RBAC-зависимости, UserRole, ROLE_PERMISSIONS |
| `auth.py` | get_user_permissions(), добавление permissions в token |
| `main.py` | Admin-эндпоинты с проверкой ролей |
| `tests/test_rbac.py` | Тесты для RBAC |

---

*Документ создан: 2026-08-03*  
*Версия: 1.0.0*
