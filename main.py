import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

import sentry_sdk
import structlog
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sqlalchemy import select

from auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    User,
    UserCreate,
    authenticate_user,
    create_access_token,
    get_current_active_user,
    get_password_hash,
)
from cache import init_cache
from database import SessionDep
from logger import setup_logging
from middleware import LimitRequestBodyMiddleware, RequestIDMiddleware
from models import Item as ItemModel
from models import UserModel

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
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


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
