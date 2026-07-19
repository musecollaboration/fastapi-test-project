from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
from uuid import uuid4, UUID

app = FastAPI()

# ---------- Модели ----------


class Item(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    created_at: datetime


class CreateItem(BaseModel):
    name: str
    description: str | None = None


# ---------- База (заглушка) ----------
fake_db = [
    {"id": uuid4(), "name": "First item", "description": "This is the first item", "created_at": datetime.now()},
    {"id": uuid4(), "name": "Second item", "description": "This is the second item", "created_at": datetime.now()},
]

# ---------- Эндпоинты ----------


@app.get("/")
async def root():
    return {"message": "API is running"}


@app.get("/items", response_model=list[Item])
async def get_items():
    return fake_db


@app.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: UUID):
    for item in fake_db:
        if item["id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")


@app.post("/items", response_model=Item, status_code=201)
async def create_item(item: CreateItem):
    new_item = {
        "id": uuid4(),
        "name": item.name,
        "description": item.description,
        "created_at": datetime.now()
    }
    fake_db.append(new_item)
    return new_item


@app.delete("/items/{item_id}")
async def delete_item(item_id: UUID):
    for i, item in enumerate(fake_db):
        if item["id"] == item_id:
            del fake_db[i]
            return {"message": f"Item {item_id} deleted"}
    raise HTTPException(status_code=404, detail="Item not found")
