from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="Test RESTful API")

class Item(BaseModel):
    name: str
    description: str = ""
    price: float = 0.0

class ItemResponse(Item):
    id: int

# in-memory "database"
db: dict[int, Item] = {}
next_id = 1


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/items", response_model=list[ItemResponse])
def list_items(q: Optional[str] = None, limit: int = 50):
    results = list(db.items())
    if q:
        results = [(i, item) for i, item in results if q.lower() in item.name.lower()]
    results = results[:limit]
    return [ItemResponse(id=i, **item.dict()) for i, item in results]


@app.get("/items/{item_id}", response_model=ItemResponse)
def get_item(item_id: int):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemResponse(id=item_id, **db[item_id].dict())


@app.post("/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(item: Item):
    global next_id
    db[next_id] = item
    resp = ItemResponse(id=next_id, **item.dict())
    next_id += 1
    return resp


@app.put("/items/{item_id}", response_model=ItemResponse)
def update_item(item_id: int, item: Item):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    db[item_id] = item
    return ItemResponse(id=item_id, **item.dict())


@app.patch("/items/{item_id}", response_model=ItemResponse)
def partial_update_item(item_id: int, item: dict):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    stored = db[item_id].dict()
    stored.update(item)
    updated = Item(**stored)
    db[item_id] = updated
    return ItemResponse(id=item_id, **updated.dict())


@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int):
    if item_id not in db:
        raise HTTPException(status_code=404, detail="Item not found")
    del db[item_id]
    return None
