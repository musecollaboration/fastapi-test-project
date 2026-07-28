import os
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

import sentry_sdk
import structlog
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sqlalchemy import select

from cache import init_cache
from database import SessionDep
from logger import setup_logging
from middleware import LimitRequestBodyMiddleware, RequestIDMiddleware
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


class ItemCreate(BaseModel):
    name: str
    description: str | None = None


class ItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@app.get("/")
async def root():
    return {"message": "DEV. Deployed via CI/CD!"}


@app.get("/items", response_model=list[ItemOut])
@cache(expire=60)   # кэшировать на 60 секунд
async def get_items(session: SessionDep):
    logger.info("Fetching all items")
    result = await session.execute(select(ItemModel))
    return result.scalars().all()


@app.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: UUID, session: SessionDep):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(item_in: ItemCreate, session: SessionDep):
    logger.info("Creating new item", name=item_in.name)
    new_item = ItemModel(name=item_in.name, description=item_in.description)
    session.add(new_item)
    await session.commit()
    await session.refresh(new_item)
    await FastAPICache.clear()  # сбросить кэш списка items
    logger.info("Item created", item_id=str(new_item.id))
    return new_item


@app.put("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: UUID, item_in: ItemUpdate, session: SessionDep):
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
    return item


@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: UUID, session: SessionDep):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await session.delete(item)
    await session.commit()
    await FastAPICache.clear()  # сбросить кэш списка items
    return None
