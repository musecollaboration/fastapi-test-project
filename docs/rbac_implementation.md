# RBAC (Role-Based Access Control) - Внедрение ролевой модели

**Дата обновления:** 2026-08-04  
**Статус:** ✅ **Production Ready**  
**Версия:** 2.0.0

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

## 🚨 Критические исправления архитектуры (2026-08-04)

### 1. Строгая типизация `created_at`

`created_at` всегда есть в БД (`server_default=text("now()")`) и всегда передаётся из ORM в Pydantic-модели. Клиент всегда получает дату, никогда `null`.

**Правило:** Строгая типизация отражает реальное состояние данных.

```python
class UserInDB(User):
    created_at: datetime  # ← всегда заполняется из БД

class UserOut(BaseModel):
    created_at: datetime  # ← клиент всегда получает дату
```

### 2. Исправление `UnmappedInstanceError` в админ-эндпоинтах

В эндпоинтах `update_user_role` и `delete_user` используется прямой ORM-запрос к `UserModel`, а не функция `get_user()`, которая возвращает Pydantic-схему.

**Правило:** SQLAlchemy-модели (`UserModel`) для работы с БД, Pydantic-схемы (`UserInDB`, `UserOut`) для передачи данных между слоями и валидации. Никогда не смешивать их.

```python
# ✅ update_user_role — ORM-запрос
result = await session.execute(
    select(UserModel).where(UserModel.username == username)
)
user = result.scalar_one_or_none()
if user is None:
    raise HTTPException(status_code=404, detail="User not found")

user.role = role_data.role
session.add(user)
await session.commit()
await session.refresh(user)
return UserOut.model_validate(user)

# ✅ delete_user — ORM-запрос
result = await session.execute(
    select(UserModel).where(UserModel.username == username)
)
user = result.scalar_one_or_none()
if user is None:
    raise HTTPException(status_code=404, detail="User not found")

await session.delete(user)
await session.commit()
```

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
│   ├── get_user_permissions(role)  → маппинг ролей в permissions
│   ├── create_access_token()       → добавление permissions в JWT
│   ├── create_refresh_token()      → добавление permissions в JWT
│   ├── UserInDB                    → created_at: datetime (строгий тип)
│   └── get_user()                  → всегда заполняет created_at из ORM
│
├── rbac.py                         (новая)
│   ├── UserRole enum
│   ├── require_role()              → проверка роли из JWT payload
│   ├── require_admin()             → проверка админа
│   ├── require_moderator_or_admin() → проверка модератора или админа
│   ├── require_permission()        → проверка конкретного permission
│   └── ROLE_PERMISSIONS            → маппинг ролей в permissions
│
└── main.py
    ├── /admin/users                → admin only (ORM-запрос)
    ├── /admin/users/{username}     → admin only
    ├── /admin/users/{username}/role → admin only (ORM-запрос)
    ├── /admin/permissions          → all users (из JWT)
    └── UserOut                     → created_at: datetime (строгий тип)
```

---

## Роли и разрешения

### Таблица прав:

| Permission         | User | Moderator | Admin |
| ------------------ | ---- | --------- | ----- |
| `items:read`       | ✅   | ✅        | ✅    |
| `items:create`     | ✅   | ✅        | ✅    |
| `items:update:own` | ✅   | -         | -     |
| `items:update:any` | ❌   | ✅        | ✅    |
| `items:delete:own` | ✅   | -         | -     |
| `items:delete:any` | ❌   | ✅        | ✅    |
| `profile:read`     | ✅   | ✅        | ✅    |
| `profile:update`   | ✅   | ✅        | ✅    |
| `users:read`       | ❌   | ✅        | ✅    |
| `users:create`     | ❌   | ❌        | ✅    |
| `users:update`     | ❌   | ✅        | ✅    |
| `users:delete`     | ❌   | ❌        | ✅    |
| `users:role`       | ❌   | ❌        | ✅    |
| `system:config`    | ❌   | ❌        | ✅    |

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

### 1. Добавление permissions в JWT-токен

При создании access и refresh токенов автоматически добавляется список permissions на основе роли:

```python
# В эндпоинтах /token и /refresh
access_token = create_access_token(
    data={
        "sub": user.username,
        "user_id": str(user.id),
        "role": user.role,
        "email": user.email,
        "permissions": get_user_permissions(user.role),  # ← автоматически
    },
    expires_delta=access_token_expires,
)
```

### 2. Зависимость для проверки роли

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

### 3. Быстрая проверка админа

```python
from rbac import require_admin

@app.get("/admin/dashboard")
async def admin_dashboard(
    user_data: Annotated[dict, Depends(require_admin)]
):
    return {"admin": user_data["sub"]}
```

### 4. Проверка модератора или админа

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

### 5. Проверка permissions

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

| Тест                              | Что проверяет                          |
| --------------------------------- | -------------------------------------- |
| `test_admin_permissions_endpoint` | Пользователь может получить свои права |
| `test_admin_users_requires_admin` | `/admin/users` доступен только админам |
| `test_role_permissions_mapping`   | Маппинг ролей и permissions корректен  |

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
6. **Strict typing** — `created_at` всегда `datetime`, никогда `None`
7. **ORM separation** — SQLAlchemy-модели для БД, Pydantic-схемы для API

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

| Файл                 | Назначение                                              |
| -------------------- | ------------------------------------------------------- |
| `rbac.py`            | RBAC-зависимости, UserRole, ROLE_PERMISSIONS            |
| `auth.py`            | `get_user_permissions()`, JWT с permissions, `UserInDB` |
| `main.py`            | Admin-эндпоинты с ORM-запросами, `UserOut`              |
| `tests/test_rbac.py` | Тесты для RBAC                                          |

---

_Документ создан: 2026-08-03_  
_Последнее обновление: 2026-08-04_  
_Версия: 2.0.0_
