import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import sentry_sdk
import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from jwt import InvalidTokenError, decode
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sqlalchemy import select

from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    Token,
    User,
    UserCreate,
    UserInDB,
    _get_secret_key,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_active_user,
    get_current_user_stateless,
    get_password_hash,
    get_user,
    oauth2_scheme,
)
from cache import init_cache
from database import SessionDep
from logger import setup_logging
from middleware import LimitRequestBodyMiddleware, RequestIDMiddleware
from models import BlacklistedToken, UserModel
from models import Item as ItemModel

# Настраиваем логирование до создания приложения
setup_logging()
logger = structlog.get_logger(__name__)

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        traces_sample_rate=0.01,                 # 1% запросов для трассировки
        environment=os.getenv("ENVIRONMENT", "development"),
        release="1.0.0",                         # можно подставлять из CI/CD
        send_default_pii=True,                   # отправляет IP-адрес клиента
        auto_session_tracking=False,             # GlitchTip не поддерживает сессии
    )
else:
    print("SENTRY_DSN not set, error tracking disabled.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up")
    await init_cache()
    yield
    logger.info("Application shutting down")


app = FastAPI(lifespan=lifespan)

instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app, endpoint="/metrics")

# Разрешённые origins — только наши домены
origins = [
    "https://muse-collaboration.ru",
    "https://dev.muse-collaboration.ru",
    # Для локальной разработки можно добавить:
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,              # список разрешённых доменов
    allow_credentials=True,             # разрешить передачу cookies
    allow_methods=["*"],                # разрешить все методы (GET, POST, PUT, DELETE и т.д.)
    allow_headers=["*"],                # разрешить все заголовки
)

# Добавляем middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LimitRequestBodyMiddleware, max_size=10 * 1024 * 1024)


class ItemOut(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ItemCreate(BaseModel):
    name: str
    description: str | None = None


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@app.post("/register", response_model=User)
async def register_user(user_data: UserCreate, session: SessionDep):
    # Проверяем, существует ли пользователь
    existing = await session.execute(
        select(UserModel).where(UserModel.username == user_data.username)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Username already registered")

    hashed_password = get_password_hash(user_data.password)
    new_user = UserModel(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password,
        disabled=False,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    # Возвращаем Pydantic-схему User (без пароля)
    return User.model_construct(
        id=UUID(str(new_user.id)),
        username=new_user.username,
        email=new_user.email,
        full_name=new_user.full_name,
        disabled=new_user.disabled,
    )


@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep,
):
    user = await authenticate_user(form_data.username, form_data.password, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": str(user.id),
            "role": user.role,
            "email": user.email,
        },
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(
        data={
            "sub": user.username,
            "user_id": str(user.id),
            "role": user.role,
            "email": user.email,
        }
    )

    response = JSONResponse({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    })
    # Устанавливаем cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,           # только по HTTPS
        samesite="strict",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )
    return response


class RefreshRequest(BaseModel):
    refresh_token: str


@app.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_req: RefreshRequest,
    session: SessionDep,
):
    """
    Обновление access-токена через refresh-токен.
    B микросервисной архитектуре можно передать user_id/role из payload
    без обращения к БД.
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
    except InvalidTokenError as exc:
        raise credentials_exception from exc

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


@app.get("/")
async def root():
    return {"message": "DEV. Deployed via CI/CD!"}


@app.get("/items", response_model=list[ItemOut])
@cache(expire=60)   # кэшировать на 60 секунд
async def get_items(
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    logger.info("Fetching all items")
    result = await session.execute(select(ItemModel))
    items = result.scalars().all()
    return [ItemOut.model_validate(item) for item in items]


@app.get("/items/{item_id}", response_model=ItemOut)
async def get_item(
    item_id: UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemOut.model_validate(item)


@app.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_in: ItemCreate,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    logger.info("Creating new item", name=item_in.name)
    new_item = ItemModel(
        name=item_in.name,
        description=item_in.description,
        owner_id=current_user.id,
    )
    session.add(new_item)
    await session.commit()
    await session.refresh(new_item)
    await FastAPICache.clear()  # сбросить кэш списка items
    logger.info("Item created", item_id=str(new_item.id))
    return ItemOut.model_validate(new_item)


@app.put("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: UUID,
    item_in: ItemUpdate,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item_in.name is not None:
        item.name = item_in.name
    if item_in.description is not None:
        item.description = item_in.description
    session.add(item)
    await session.commit()
    await session.refresh(item)
    await FastAPICache.clear()  # сбросить кэш списка items
    return ItemOut.model_validate(item)


@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: UUID,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await session.delete(item)
    await session.commit()
    await FastAPICache.clear()  # сбросить кэш списка items
    return None


# ---------- Stateless-маршруты для микросервисов ----------

class StateUser(BaseModel):
    """Данные пользователя из JWT-токена (stateless)."""
    sub: str
    user_id: UUID | None = None
    role: str = "user"
    email: str | None = None


@app.get("/me/stateless", response_model=StateUser)
async def get_current_user_stateless_route(
    user_data: Annotated[dict, Depends(get_current_user_stateless)],
):
    """
    Stateless-маршрут: данные пользователя извлекаются из JWT-токена
    без обращения к БД. Подходит для микросервисной архитектуры.

    Для монолита, где данные могут меняться (например, роль),
    используйте обычный /me s get_current_user.
    """
    return StateUser(
        sub=user_data["sub"],
        user_id=user_data.get("user_id"),
        role=user_data["role"],
        email=user_data.get("email"),
    )
