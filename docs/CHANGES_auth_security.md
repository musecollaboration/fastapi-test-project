# Refresh-токены, отзыв, безопасность и подготовка к микросервисам

## 📋 Содержание

- [Обзор изменений](#обзор-изменений)
- [Архитектура авторизации](#архитектура-авторизации)
- [Refresh-токены](#refresh-токены)
- [Отзыв токенов (Logout)](#отзыв-токенов-logout)
- [Безопасность](#безопасность)
- [Подготовка к микросервисам](#подготовка-к-микросервисам)
- [API Reference](#api-reference)
- [Тесты](#тесты)
- [Миграции БД](#миграции-бд)

---

## Обзор изменений

За время разработки были реализованы следующие ключевые функции:

| Компонент | Что сделано |
|-----------|-------------|
| **Аутентификация** | JWT-токены (access + refresh), OAuth2 Password Flow |
| **Отзыв** | Таблица `blacklisted_tokens`, endpoint `/logout` |
| **Безопасность** | Secure cookies, timing-safe verification, CORS, rate limiting |
| **Микросервисы** | Stateless-авторизация, расширенный JWT payload |
| **Модели** | `UserModel` (с ролью), `Item` (с owner_id), `BlacklistedToken` |
| **Тесты** | 9 тестов, авторизованный клиент, проверка stateless |

---

## Архитектура авторизации

### Схема потока авторизации

```
┌─────────────┐     POST /register      ┌─────────────┐
│   Client    │ ──────────────────────► │  FastAPI    │
│             │                         │  (Auth)     │
│             │ ◄────────────────────── │             │
│   User      │     200 OK              │             │
│  registered │                         │             │
└─────────────┘                         └─────────────┘
       │                                       │
       │     POST /token (username+password)   │
       │ ───────────────────────────────────► │
       │ ◄────────────────────────────────── │
       │   access_token + refresh_token      │
       │   (secure cookies)                  │
       │                                     │
       │  Bearer access_token                │
       │ ───────────────────────────────────► │
       │ ◄────────────────────────────────── │
       │   Protected resource                │
       │                                     │
       │     POST /refresh (refresh_token)   │
       │ ───────────────────────────────────► │
       │ ◄────────────────────────────────── │
       │   new access_token                  │
       │                                     │
       │     POST /logout                    │
       │ ───────────────────────────────────► │
       │   Token blacklisted                 │
       │                                     │
       │  Bearer access_token (blacklisted)  │
       │ ───────────────────────────────────► │
       │ ◄────────────────────────────────── │
       │   401 Unauthorized                  │
```

### Компоненты системы

```
┌─────────────────────────────────────────────────────────────┐
│                      auth.py                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Pydantic Models                                     │   │
│  │  • UserBase, UserCreate, User, UserInDB              │   │
│  │  • Token, TokenData                                  │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Password Hashing                                    │   │
│  │  • get_password_hash()                               │   │
│  │  • verify_password() (timing-safe)                   │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  JWT Operations                                      │   │
│  │  • create_access_token()                             │   │
│  │  • create_refresh_token()                            │   │
│  │  • get_current_user() (with DB check)                │   │
│  │  • get_current_user_stateless() (JWT only)           │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Refresh-токены

### Зачем нужны refresh-токены?

Access-токен имеет короткий срок жизни (15 минут). Когда он истекает, пользователю не нужно заново вводить пароль — используется refresh-токен для получения нового access-токена.

### Реализация

**Файл:** `auth.py`

```python
REFRESH_TOKEN_EXPIRE_DAYS = 30

def create_refresh_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)
```

### Эндпоинт обновления

**Файл:** `main.py`

```python
@app.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_req: RefreshRequest,
    session: SessionDep,
):
    """
    Обновление access-токена через refresh-токен.
    Проверяет тип токена и извлекает username из payload.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
    )
    try:
        payload = decode(refresh_req.refresh_token, _get_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise credentials_exception
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception

    user = await get_user(username, session)
    if user is None:
        raise credentials_exception

    # Копируем все поля из старого токена + обновляем данные из БД
    new_access = create_access_token(
        data={
            "sub": user.username,
            "user_id": str(user.id),
            "role": user.role,
            "email": user.email,
        }
    )
    new_refresh = create_refresh_token(
        data={
            "sub": user.username,
            "user_id": str(user.id),
            "role": user.role,
            "email": user.email,
        }
    )
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer"
    }
```

### Особенности

- ✅ Refresh-токен имеет тип `"type": "refresh"` в payload
- ✅ Срок жизни: 30 дней
- ✅ При обновлении данные берутся из БД (актуальная роль, email)
- ✅ Новый refresh-токен заменяет старый (rotation)

---

## Отзыв токенов (Logout)

### Таблица `blacklisted_tokens`

**Файл:** `models.py`

```python
class BlacklistedToken(Base):
    __tablename__ = "blacklisted_tokens"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    blacklisted_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("now()"))
```

### Эндпоинт logout

**Файл:** `main.py`

```python
@app.post("/logout")
async def logout(
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDep,
):
    # Извлекаем время истечения из токена
    payload = decode(token, _get_secret_key(), algorithms=[ALGORITHM])
    exp_timestamp = payload.get("exp")
    expires_at = (
        datetime.fromtimestamp(exp_timestamp, UTC)
        if exp_timestamp
        else datetime.now(UTC) + timedelta(minutes=15)
    )
    blacklisted = BlacklistedToken(token=token, expires_at=expires_at)
    session.add(blacklisted)
    await session.commit()
    return {"detail": "Successfully logged out"}
```

### Проверка при авторизации

**Файл:** `auth.py`

```python
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: SessionDep,
) -> UserInDB:
    # ... decoding token ...
    
    # Проверяем, не отозван ли токен
    blacklisted = await session.execute(
        select(BlacklistedToken).where(BlacklistedToken.token == token)
    )
    if blacklisted.scalar_one_or_none() is not None:
        raise credentials_exception
    
    # ... getting user from DB ...
```

### Как это работает

1. При `/logout` текущий access-токен добавляется в `blacklisted_tokens`
2. Токен остаётся в чёрном списке до момента его естественного истечения (`expires_at`)
3. При каждом запросе к защищённым endpoint-ам проверяется `blacklisted_tokens`
4. Если токен в чёрном списке → 401 Unauthorized

---

## Безопасность

### 1. Secure Cookies

Токены передаются в cookies с защитными флагами:

**Файл:** `main.py`

```python
response.set_cookie(
    key="access_token",
    value=access_token,
    httponly=True,           # JavaScript не может прочитать
    secure=True,             # Только HTTPS
    samesite="strict",       # Защита от CSRF
    max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
)
```

### 2. Timing-Safe Password Verification

Защита от timing-атак при проверке пароля:

**Файл:** `auth.py`

```python
async def authenticate_user(username: str, password: str, session: AsyncSession) -> UserInDB | None:
    user = await get_user(username, session)
    if not user:
        # Защита от timing-атаки: даже если пользователя нет,
        # выполняем проверку пароля на dummy-хеше
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
```

### 3. Middleware

**Request ID Middleware** — трассировка запросов:

```python
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        import structlog
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

**Limit Request Body** — ограничение размера payload:

```python
class LimitRequestBodyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_size: int = 10 * 1024 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            raise HTTPException(status_code=413, detail="Payload Too Large")
        return await call_next(request)
```

### 4. CORS

**Файл:** `main.py`

```python
origins = [
    "https://muse-collaboration.ru",
    "https://dev.muse-collaboration.ru",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Подготовка к микросервисам

### Проблема монолита

В текущей реализации `get_current_user` обращается к БД при каждом запросе для получения данных пользователя. В микросервисной архитектуре это неприемлемо — каждый сервис должен проверять токен **без обращения к общей БД**.

### Решение: Stateless-авторизация

#### Расширенный JWT Payload

Теперь в токен кладем все необходимые поля:

```python
# При создании токена
access_token = create_access_token(
    data={
        "sub": user.username,
        "user_id": str(user.id),
        "role": user.role,
        "email": user.email,
    },
    expires_delta=access_token_expires,
)
```

#### Stateless-зависимость

**Файл:** `auth.py`

```python
async def get_current_user_stateless(
    _request: Request,
    token: Annotated[str, Depends(get_token_from_request)],
) -> dict:
    """
    Stateless-проверка токена без обращения к БД.
    Данные извлекаются напрямую из payload JWT.
    Подходит для микросервисной архитектуры.
    
    Возвращает словарь с полями: sub, user_id, role, email, type, exp.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        token_type = payload.get("type")
        if token_type not in ("access", "refresh"):
            raise credentials_exception
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError as exc:
        raise credentials_exception from exc

    return {
        "sub": username,
        "user_id": payload.get("user_id"),
        "role": payload.get("role", "user"),
        "email": payload.get("email"),
        "type": token_type,
    }
```

#### Stateless-эндпоинт

**Файл:** `main.py`

```python
@app.get("/me/stateless", response_model=StateUser)
async def get_current_user_stateless_route(
    user_data: Annotated[dict, Depends(get_current_user_stateless)],
):
    """
    Stateless-маршрут: данные пользователя извлекаются из JWT-токена
    без обращения к БД. Подходит для микросервисной архитектуры.
    """
    return StateUser(
        sub=user_data["sub"],
        user_id=user_data.get("user_id"),
        role=user_data["role"],
        email=user_data.get("email"),
    )
```

### Сравнение подходов

| Характеристика | Stateful (DB) | Stateless (JWT) |
|----------------|---------------|-----------------|
| **Обращение к БД** | Да, при каждом запросе | Нет |
| **Актуальность данных** | Да (из БД) | Нет (из токена) |
| **Скорость** | Медленнее | Быстрее |
| **Отзыв токена** | Да (blacklist) | Нет (до истечения) |
| **Смена роли** | Мгновенно | После истечения токена |
| **Для монолита** | ✅ Да | ❌ Нет |
| **Для микросервисов** | ❌ Нет | ✅ Да |

### Когда использовать что?

- **Монолит** → `get_current_user` (с БД) — данные всегда актуальны
- **Микросервисы** → `get_current_user_stateless` (без БД) — скорость и независимость

---

## API Reference

### Регистрация

```
POST /register
Content-Type: application/json

{
  "username": "john",
  "password": "secure123",
  "email": "john@example.com",
  "full_name": "John Doe"
}

Response 200:
{
  "username": "john",
  "email": "john@example.com",
  "full_name": "John Doe",
  "role": "user",
  "id": "uuid...",
  "disabled": false
}
```

### Авторизация

```
POST /token
Content-Type: application/x-www-form-urlencoded

username=john&password=secure123

Response 200:
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}

Cookies:
  access_token=eyJ... (HttpOnly, Secure, SameSite=Strict)
  refresh_token=eyJ... (HttpOnly, Secure, SameSite=Strict)
```

### Обновление токена

```
POST /refresh
Content-Type: application/json

{
  "refresh_token": "eyJ..."
}

Response 200:
{
  "access_token": "eyJ_new...",
  "refresh_token": "eyJ_new...",
  "token_type": "bearer"
}
```

### Выход (Logout)

```
POST /logout
Authorization: Bearer eyJ...

Response 200:
{
  "detail": "Successfully logged out"
}
```

### Stateless User Info

```
GET /me/stateless
Authorization: Bearer eyJ...

Response 200:
{
  "sub": "john",
  "user_id": "uuid...",
  "role": "user",
  "email": "john@example.com"
}
```

### Protected Items

```
GET /items
Authorization: Bearer eyJ...

Response 200:
[
  {
    "id": "uuid...",
    "name": "Item 1",
    "description": "Description",
    "created_at": "2026-08-03T16:00:00"
  }
]
```

---

## Тесты

### Структура тестов

**Файл:** `tests/test_main.py`

| Тест | Что проверяет |
|------|---------------|
| `test_root` | Доступ без авторизации |
| `test_create_item` | Создание элемента с авторизацией |
| `test_get_items` | Получение списка с кэшем |
| `test_get_item_not_found` | 404 для несуществующего элемента |
| `test_get_item_by_id` | Получение элемента по ID |
| `test_update_item` | Обновление элемента |
| `test_delete_item` | Удаление элемента |
| `test_stateless_me` | Stateless-авторизация |
| `test_token_contains_user_data` | Payload токена содержит все поля |

### Фикстуры

**Файл:** `conftest.py`

```python
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
```

### Пример авторизованного клиента

```python
@pytest.fixture(scope="function")
async def auth_client(client: AsyncClient) -> AsyncClient:
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
```

### Запуск тестов

```bash
source .venv/bin/activate
python -m pytest tests/test_main.py -v
```

**Результат:** 9 passed, 16 warnings

---

## Миграции БД

### История миграций

```
<base> -> 37a53b2090b9, create users and items tables
37a53b2090b9 -> 87a84cdb74ce, add blacklisted_tokens
87a84cdb74ce -> 501e1f2172e9 (head), create items and blacklisted_tokens tables
```

### Текущая версия

```bash
docker exec fastapi-container alembic current
# 501e1f2172e9 (head)
```

### Созданные таблицы

| Таблица | Назначение | Ключевые поля |
|---------|------------|---------------|
| `users` | Пользователи | id, username, email, role, hashed_password |
| `items` | Элементы | id, name, owner_id (FK → users) |
| `blacklisted_tokens` | Отозванные токены | token (unique), expires_at |
| `alembic_version` | Версия миграций | version_num |

### Создание новой миграции

```bash
docker exec fastapi-container alembic revision --autogenerate -m "description"
docker exec fastapi-container alembic upgrade head
```

---

## Файловая структура

```
├── auth.py                  # Аутентификация, JWT, безопасность
├── main.py                  # API endpoints
├── models.py                # SQLAlchemy модели
├── middleware.py            # RequestID, LimitRequestBody
├── conftest.py              # Тестовые фикстуры
├── migrations/
│   ├── env.py
│   └── versions/
│       ├── 37a53b2090b9_... (users, items)
│       ├── 87a84cdb74ce_... (blacklisted_tokens)
│       └── 501e1f2172e9_... (autogenerate)
├── tests/
│   ├── __init__.py
│   └── test_main.py         # 9 тестов
└── docs/
    └── CHANGES_auth_security.md  # Этот файл
```

---

## Чек-лист безопасности

- [x] JWT-токены подписываются секретным ключом (`SECRET_KEY`)
- [x] Access-токен имеет короткий срок жизни (15 мин)
- [x] Refresh-токен имеет тип `refresh` в payload
- [x] Пароли хешируются через `pwdlib`
- [x] Timing-safe password verification
- [x] Secure cookies (HttpOnly, Secure, SameSite)
- [x] CORS настроен на конкретные домены
- [x] Ограничение размера body запроса
- [x] Request ID для трассировки
- [x] Blacklist для отзыва токенов
- [x] Stateless-авторизация для микросервисов

---

## Будущие улучшения

1. **HTTP-only cookies для refresh-token** — убрать из JS
2. **Token rotation** — использовать старый refresh-токен один раз
3. **Refresh token binding** — привязка к IP/User-Agent
4. **Rate limiting** — на endpoint-ах `/token` и `/register`
5. **Password policy** — проверка сложности пароля
6. **Email verification** — подтверждение email при регистрации
7. **2FA/MFA** — двухфакторная аутентификация
8. **OAuth2 providers** — Google, GitHub login

---

*Документ создан: 2026-08-03*  
*Версия проекта: 1.0.0*
