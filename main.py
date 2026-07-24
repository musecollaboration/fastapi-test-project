from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

import models  # noqa: F401  # нужно для регистрации модели в Base
from database import Base, SessionDep, engine
from models import Item as ItemModel

# ---------- Lifespan для создания таблиц ----------


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)

# ---------- Pydantic-схемы ----------


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

# ---------- CRUD эндпоинты ----------


@app.get("/")
async def root():
    return {"message": "DEV. Deployed via CI/CD!"}

# 1. Получить все элементы


@app.get("/items", response_model=list[ItemOut])
async def get_items(session: SessionDep):
    result = await session.execute(select(ItemModel))
    items = result.scalars().all()
    return items

# 2. Получить один элемент по ID


@app.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: UUID, session: SessionDep):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

# 3. Создать новый элемент


@app.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(item_in: ItemCreate, session: SessionDep):
    new_item = ItemModel(name=item_in.name, description=item_in.description)
    session.add(new_item)
    await session.commit()
    await session.refresh(new_item)
    return new_item

# 4. Обновить элемент (полное или частичное обновление)


@app.put("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: UUID, item_in: ItemUpdate, session: SessionDep):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    # Обновляем только переданные поля
    if item_in.name is not None:
        item.name = item_in.name
    if item_in.description is not None:
        item.description = item_in.description
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item

# 5. Удалить элемент


@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: UUID, session: SessionDep):
    item = await session.get(ItemModel, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await session.delete(item)
    await session.commit()
    return None  # 204 No Content
