from __future__ import annotations
import json
from app.schemas import Product


def save_catalog(products: list[Product], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([p.model_dump() for p in products], f, ensure_ascii=False)


def load_catalog(path: str) -> list[Product]:
    with open(path, encoding="utf-8") as f:
        return [Product(**d) for d in json.load(f)]
