from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

app = FastAPI()

# ---------- Модели ----------


class Item(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime


class CreateItem(BaseModel):
    name: str
    description: Optional[str] = None


# ---------- База данных (заглушка) ----------
fake_db = [
    {"id": 1, "name": "First item", "description": "This is the first item", "created_at": datetime.now()},
    {"id": 2, "name": "Second item", "description": "This is the second item", "created_at": datetime.now()},
]

# ---------- Эндпоинты ----------


@app.get("/")
async def root():
    return {"message": "API is running"}


@app.get("/items", response_model=List[Item])
async def get_items():
    """Получить все элементы"""
    return fake_db


@app.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: int):
    """Получить элемент по ID"""
    for item in fake_db:
        if item["id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")


@app.post("/items", response_model=Item)
async def create_item(item: CreateItem):
    """Создать новый элемент"""
    new_id = max(i["id"] for i in fake_db) + 1 if fake_db else 1
    new_item = {
        "id": new_id,
        "name": item.name,
        "description": item.description,
        "created_at": datetime.now()
    }
    fake_db.append(new_item)
    return new_item


@app.delete("/items/{item_id}")
async def delete_item(item_id: int):
    """Удалить элемент по ID"""
    for i, item in enumerate(fake_db):
        if item["id"] == item_id:
            del fake_db[i]
            return {"message": f"Item {item_id} deleted"}
    raise HTTPException(status_code=404, detail="Item not found")
