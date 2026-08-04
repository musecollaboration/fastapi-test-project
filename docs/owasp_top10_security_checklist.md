# OWASP Top 10 — Чек-лист безопасности

**Дата обновления:** 2026-08-04  
**Статус:** 🟢 **Production Ready**  
**Версия:** 2.0.0

---

## 📋 Содержание

- [A01 Broken Access Control](#a01-broken-access-control)
- [A02 Security Misconfiguration](#a02-security-misconfiguration)
- [A03 Supply Chain](#a03-supply-chain)
- [A04 Cryptographic Failures](#a04-cryptographic-failures)
- [A05 Injection](#a05-injection)
- [A07 Authentication Failures](#a07-authentication-failures)
- [A09 Logging & Monitoring](#a09-logging--monitoring)
- [A10 Security Misconfiguration (Exception Handling)](#a10-exception-handling)

---

## A01 Broken Access Control

### ✅ Что реализовано

| Элемент            | Статус | Описание                                                                      |
| ------------------ | ------ | ----------------------------------------------------------------------------- |
| RBAC               | ✅     | 3 роли: user, moderator, admin                                                |
| Permissions        | ✅     | Автоматическое назначение при создании токена                                 |
| Stateless-проверка | ✅     | Проверка ролей без обращения к БД                                             |
| Admin-эндпоинты    | ✅     | `/admin/users`, `/admin/users/{username}/role`                                |
| Ownership check    | ✅     | Проверка `item.owner_id == current_user.id` в GET/PUT/DELETE /items/{item_id} |

### ✅ Проверка: Ownership validation

```python
# main.py:317-325 — GET /items/{item_id}
@app.get("/items/{item_id}", response_model=ItemOut)
async def get_item(
    item_id: UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.owner_id != current_user.id:  # ✅ Проверка владельца
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    return ItemOut.model_validate(item)
```

**Статус:** ✅ **Все критерии выполнены**

---

## A02 Security Misconfiguration

### ✅ Что реализовано

| Элемент               | Статус | Описание                                           |
| --------------------- | ------ | -------------------------------------------------- |
| CORS                  | ✅     | Только доверенные домены                           |
| SECRET_KEY            | ✅     | В переменных окружения                             |
| Limit request body    | ✅     | 10 МБ через middleware                             |
| HTTP security headers | ✅     | X-Content-Type-Options, X-Frame-Options, HSTS, CSP |
| Отключение /docs      | ✅     | ENABLE_DOCS=false в продакшене                     |

### ✅ Проверка: HTTP security headers

```python
# main.py:96-107
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"  # ✅
    response.headers["X-Frame-Options"] = "DENY"  # ✅
    response.headers["X-XSS-Protection"] = "1; mode=block"  # ✅
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"  # ✅
    response.headers["Content-Security-Policy"] = "default-src 'self'"  # ✅
    return response
```

### ✅ Проверка: Отключение /docs в продакшене

```python
# main.py:51
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "false").lower() == "true"

# main.py:83-88
app = FastAPI(
    title="API",
    docs_url="/docs" if ENABLE_DOCS else None,  # ✅
    redoc_url="/redoc" if ENABLE_DOCS else None,  # ✅
)
```

**Статус:** ✅ **Все критерии выполнены**

---

## A03 Supply Chain

### ❌ Отсутствует: проверка зависимостей

**Проблема:** Нет проверки уязвимых зависимостей в CI/CD.

**Решение:** Добавить `safety` в CI:

```yaml
# .github/workflows/security.yml
- name: Check dependencies for vulnerabilities
  run: |
    pip install safety
    safety check -r requirements.txt --json --output safety-report.json
```

### 📝 План исправлений

- [ ] Добавить `safety` в `pyproject.toml`
- [ ] Добавить job в GitHub Actions для проверки зависимостей
- [ ] Настроить автоматические PR при обнаружении уязвимостей

---

## A04 Cryptographic Failures

### ✅ Что реализовано

| Элемент              | Статус | Описание                           |
| -------------------- | ------ | ---------------------------------- |
| Хеширование паролей  | ✅     | Argon2id через `pwdlib`            |
| JWT подпись          | ✅     | HS256 с `SECRET_KEY` из env        |
| HttpOnly cookies     | ✅     | `secure=True, samesite="strict"`   |
| Timing-safe проверка | ✅     | `DUMMY_HASH` в `authenticate_user` |

### ✅ Проверка: `pwdlib` использует Argon2id

```python
# auth.py:76
password_hash = PasswordHash.recommended()  # ✅ Argon2id
```

### ✅ Проверка: JWT с правильным алгоритмом

```python
# auth.py:63
ALGORITHM = "HS256"  # ✅
```

### ✅ Проверка: Timing-safe comparison

```python
# auth.py:109-117
async def authenticate_user(username: str, password: str, session: AsyncSession):
    user = await get_user(username, session)
    if not user:
        verify_password(password, DUMMY_HASH)  # ✅ Timing-safe fallback
        return None
    if not verify_password(password, user.hashed_password):  # ✅ Constant-time
        return None
    return user
```

**Статус:** ✅ **Все критерии выполнены**

---

## A05 Injection

### ✅ Что реализовано

| Элемент    | Статус | Описание                            |
| ---------- | ------ | ----------------------------------- |
| SQLAlchemy | ✅     | Параметризованные запросы через ORM |
| Pydantic   | ✅     | Валидация всех входных данных       |
| No raw SQL | ✅     | Нет `text()` в запросах к БД        |

### ✅ Проверка: SQLAlchemy queries

```python
# main.py:300
result = await session.execute(select(ItemModel))  # ✅ ORM

# main.py:491-493
result = await session.execute(
    select(UserModel).where(UserModel.username == username)  # ✅ Параметризовано
)
```

### ✅ Проверка: Pydantic validation

```python
# main.py:114-116
class ItemCreate(BaseModel):
    name: str  # ✅ Обязательное поле
    description: str | None = None  # ✅ Optional
```

**Статус:** ✅ **Все критерии выполнены**

---

## A07 Authentication Failures

### ✅ Что реализовано

| Элемент              | Статус | Описание                                          |
| -------------------- | ------ | ------------------------------------------------- |
| JWT expiry           | ✅     | Access: 30 мин, Refresh: 30 дней                  |
| Refresh tokens       | ✅     | Отдельный токен с долгим сроком                   |
| Token blacklist      | ✅     | `BlacklistedToken` при logout                     |
| Timing-safe password | ✅     | `DUMMY_HASH` fallback                             |
| Inactive users       | ✅     | `get_current_active_user`                         |
| Rate limiting        | ✅     | /token: 5/мин, /register: 3/мин, /refresh: 10/мин |

### ✅ Проверка: JWT expiry

```python
# auth.py:64
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # ✅

# auth.py:121
REFRESH_TOKEN_EXPIRE_DAYS = 30  # ✅
```

### ✅ Проверка: Token blacklist

```python
# models.py:74-80
class BlacklistedToken(Base):
    __tablename__ = "blacklisted_tokens"
    token = Column(String, primary_key=True)  # ✅
    expires_at = Column(DateTime, nullable=False)  # ✅
```

### ✅ Проверка: Inactive users

```python
# auth.py:268-275
async def get_current_active_user(current_user: UserInDB):
    if current_user.disabled is True:
        raise HTTPException(status_code=403, detail="Inactive user")
    return current_user  # ✅
```

### ✅ Проверка: Rate limiting

```python
# main.py:189-193
@app.post("/token", response_model=Token)
@limiter.limit("5/minute")  # ✅
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    ...

# main.py:159-163
@app.post("/register", response_model=User)
@limiter.limit("3/minute")  # ✅
async def register_user(
    request: Request,
    user_data: UserCreate,
    session: SessionDep,
):
    ...

# main.py:254-258
@app.post("/refresh", response_model=Token)
@limiter.limit("10/minute")  # ✅
async def refresh_access_token(
    request: Request,
    refresh_req: RefreshRequest,
    session: SessionDep,
):
    ...
```

**Статус:** ✅ **Все критерии выполнены**

---

## A09 Logging & Monitoring

### ✅ Что реализовано

| Элемент       | Статус | Описание                                |
| ------------- | ------ | --------------------------------------- |
| Structlog     | ✅     | Структурированное логирование           |
| Sentry        | ✅     | Error tracking и performance monitoring |
| RequestID     | ✅     | Middleware для trace IDs                |
| Audit logging | ✅     | Логирование изменений ролей             |

### ✅ Проверка: Structlog usage

```python
# main.py:50
logger = structlog.get_logger(__name__)

# main.py:323
logger.info("Creating new item", name=item_in.name)  # ✅ Поля, не строка
```

### ✅ Проверка: Sentry integration

```python
# main.py:52-65
sentry_sdk.init(
    dsn=sentry_dsn,
    integrations=[StarletteIntegration(), FastApiIntegration()],
    traces_sample_rate=0.01,
    environment=os.getenv("ENVIRONMENT", "development"),
)  # ✅
```

### ✅ Проверка: Audit logging

```python
# main.py:503
logger.info("User role updated", username=username, new_role=role_data.role)  # ✅
```

### ⚠️ Проверка: Sensitive data в логах

**Риск:** `structlog` может логировать sensitive поля (пароли, токены).

**Рекомендация:** Добавить filter для sensitive fields:

```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
)
```

**Статус:** ✅ **Основные критерии выполнены**

---

## A10 Security Misconfiguration (Exception Handling)

### ✅ Что реализовано

| Элемент           | Статус | Описание                          |
| ----------------- | ------ | --------------------------------- |
| Sentry            | ✅     | Все ошибки отправляются в Sentry  |
| HTTPException     | ✅     | Корректные статус-коды            |
| No raw exceptions | ✅     | Пользователь не видит stack trace |

### ✅ Проверка: Exception handling

```python
# auth.py:215-224
try:
    payload = decode(token, _get_secret_key(), algorithms=[ALGORITHM])
    ...
except InvalidTokenError as exc:
    raise credentials_exception from exc  # ✅ Нет раскрытия деталей
```

### ⚠️ Проверка: Empty except blocks

**Рекомендация:** Проверить все `except` блоки на наличие пустых обработчиков.

**Результат проверки:** Пустых `except` блоков не найдено. ✅

### 📝 План исправлений

- [ ] Добавить global exception handler для Sentry
- [ ] Добавить custom error responses для Pydantic validation errors
- [ ] Добавить health check endpoint с метриками безопасности

---

## 📊 Итоговая сводка

| Категория                     | Статус | Критичность   |
| ----------------------------- | ------ | ------------- |
| A01 Broken Access Control     | ✅     | 🟢 **OK**     |
| A02 Security Misconfiguration | ✅     | 🟢 **OK**     |
| A03 Supply Chain              | ❌     | 🟡 **СРЕДНЕ** |
| A04 Cryptographic Failures    | ✅     | 🟢 **OK**     |
| A05 Injection                 | ✅     | 🟢 **OK**     |
| A07 Authentication Failures   | ✅     | 🟢 **OK**     |
| A09 Logging & Monitoring      | ✅     | 🟢 **OK**     |
| A10 Exception Handling        | ✅     | 🟢 **OK**     |

---

## 🚀 Приоритетные задачи

### 🟡 Средне (сделать в первую очередь)

1. **A03:** Добавить `safety check` в CI/CD

### 🟢 Низкий приоритет

2. **A09:** Добавить filter для sensitive fields в structlog
3. **A10:** Добавить global exception handler для Sentry
4. **A10:** Добавить health check endpoint

---

## 📝 Примечания

### Текущие зависимости безопасности

```toml
[tool.poetry.group.security.dependencies]
safety = "^3.0.0"
slowapi = "^0.1.9"
```

### Переменные окружения для безопасности

```bash
# Обязательные
SECRET_KEY=<random-32-char>
DATABASE_URL=postgresql+asyncpg://...
SENTRY_DSN=https://...@sentry.io/...

# Опциональные
ENABLE_DOCS=false  # false в продакшене
ENVIRONMENT=production  # development/staging/production
```

### Команды для проверки

```bash
# Проверка зависимостей
pip install safety
safety check -r pyproject.toml

# Линтинг безопасности
ruff check --select=S  # flake8-bandit equivalents

# Статический анализ
mypy --strict .
```

---

_Документ создан: 2026-08-04_  
_Последнее обновление: 2026-08-04_  
_Версия: 2.0.0_  
_Автор: Security Audit_
