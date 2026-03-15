from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.db import get_room, init_db, load_catalog, save_recommendation, save_room
from app.recommender import recommend
from app.schemas import RecommendationRequest, RoomEstimateRequest

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="AI Room Styler", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (BASE_DIR / "app" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "ai-room-styler"}


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
    room = save_room(payload.model_dump())
    return {
        "room_profile": {
            "room_id": room["room_id"],
            "area_m2": room["area_m2"],
            "recommended_walkway_cm": 60,
        }
    }


@app.post("/v1/recommendations")
def recommendations(payload: RecommendationRequest):
    room = get_room(payload.room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room_id not found")

    result = recommend(room, payload.required_categories, load_catalog())
    run_id = save_recommendation(payload.room_id, result)
    result["run_id"] = run_id
    return result
