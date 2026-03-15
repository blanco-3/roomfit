from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "furniture_catalog.json"

app = FastAPI(title="AI Room Styler Demo", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


class RoomEstimateRequest(BaseModel):
    width_cm: int = Field(..., ge=180, le=1200)
    length_cm: int = Field(..., ge=180, le=1200)
    height_cm: int = Field(240, ge=180, le=400)
    mood: str = "minimal"
    purpose: str = "work_sleep"
    budget_krw: int = Field(..., ge=100000)


class RecommendationRequest(BaseModel):
    room_id: str
    required_categories: List[str] = Field(default_factory=lambda: ["bed", "desk", "chair", "storage"])


room_store: Dict[str, dict] = {}


def load_catalog() -> List[dict]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def style_score(item_tags: List[str], mood: str, purpose: str) -> float:
    score = 0.0
    mood_tokens = set(mood.lower().replace("-", "_").split("_"))
    purpose_tokens = set(purpose.lower().replace("-", "_").split("_"))
    tags = set(t.lower() for t in item_tags)

    score += 0.6 * (len(tags.intersection(mood_tokens)) / max(1, len(mood_tokens)))
    score += 0.4 * (len(tags.intersection(purpose_tokens)) / max(1, len(purpose_tokens)))
    return round(min(1.0, score), 3)


def footprint_cm2(item: dict) -> int:
    return int(item["width_cm"] * item["depth_cm"])


def walkway_fit(room: dict, items: List[dict], min_walkway_cm: int = 60) -> bool:
    # 단순 휴리스틱: 전체 점유율 기반
    room_area = room["width_cm"] * room["length_cm"]
    occupied = sum(footprint_cm2(i) for i in items)
    occupancy_ratio = occupied / room_area
    # 일반 원룸 기준 55% 이상 점유 시 동선 악화로 판정
    return occupancy_ratio <= 0.55 and min(room["width_cm"], room["length_cm"]) >= (min_walkway_cm * 3)


def recommend(room: dict, required_categories: List[str]) -> dict:
    catalog = load_catalog()

    selected = []
    total_price = 0

    for cat in required_categories:
        candidates = [i for i in catalog if i["category"] == cat and i["price_krw"] <= room["budget_krw"]]
        if not candidates:
            continue

        scored = []
        for item in candidates:
            s_score = style_score(item.get("style_tags", []), room["mood"], room["purpose"])
            size_penalty = footprint_cm2(item) / max(1, room["width_cm"] * room["length_cm"])
            final_score = (0.75 * s_score) + (0.25 * (1 - min(size_penalty, 1)))
            scored.append((round(final_score, 3), item))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_item = scored[0]

        selected.append({
            "id": best_item["id"],
            "name": best_item["name"],
            "category": best_item["category"],
            "price_krw": best_item["price_krw"],
            "dimensions_cm": {
                "width": best_item["width_cm"],
                "depth": best_item["depth_cm"],
                "height": best_item["height_cm"],
            },
            "source": best_item["source"],
            "url": best_item["url"],
            "score": best_score,
            "reason": "예산/치수/무드 적합",
        })
        total_price += int(best_item["price_krw"])

    fits = walkway_fit(room, [
        {
            "width_cm": i["dimensions_cm"]["width"],
            "depth_cm": i["dimensions_cm"]["depth"],
        }
        for i in selected
    ])

    if not fits:
        # 동선 악화 시 가장 footprint 큰 아이템 제거
        selected = sorted(selected, key=lambda i: i["dimensions_cm"]["width"] * i["dimensions_cm"]["depth"])
        selected = selected[:-1] if selected else selected
        total_price = sum(i["price_krw"] for i in selected)

    fit_score = round(min(1.0, 1 - (total_price / max(room["budget_krw"], 1) * 0.2)), 3)
    style_avg = round(sum(i["score"] for i in selected) / max(1, len(selected)), 3)

    return {
        "summary": {
            "total_price_krw": total_price,
            "fit_score": fit_score,
            "style_score": style_avg,
            "selected_count": len(selected),
        },
        "items": selected,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html_path = BASE_DIR / "app" / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/v1/catalog")
def get_catalog(category: Optional[str] = Query(None), max_price: Optional[int] = Query(None)):
    items = load_catalog()
    if category:
        items = [i for i in items if i["category"] == category]
    if max_price:
        items = [i for i in items if i["price_krw"] <= max_price]
    return {"count": len(items), "items": items}


@app.post("/v1/room/estimate")
def room_estimate(payload: RoomEstimateRequest):
    room_id = str(uuid.uuid4())
    area_m2 = round((payload.width_cm * payload.length_cm) / 10000, 2)

    room_store[room_id] = {
        "room_id": room_id,
        "width_cm": payload.width_cm,
        "length_cm": payload.length_cm,
        "height_cm": payload.height_cm,
        "mood": payload.mood,
        "purpose": payload.purpose,
        "budget_krw": payload.budget_krw,
    }

    return {
        "room_profile": {
            "room_id": room_id,
            "area_m2": area_m2,
            "recommended_walkway_cm": 60,
        }
    }


@app.post("/v1/recommendations")
def recommendations(payload: RecommendationRequest):
    room = room_store.get(payload.room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room_id not found")

    return recommend(room, payload.required_categories)
