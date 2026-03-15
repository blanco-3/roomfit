from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.db import (
    authenticate_user,
    create_token,
    create_user,
    get_room,
    get_user_by_token,
    init_db,
    list_ops_logs,
    load_catalog,
    log_event,
    save_recommendation,
    save_room,
    save_room_photo,
)
from app.recommender import recommend
from app.schemas import LoginRequest, RecommendationRequest, RegisterRequest, RoomEstimateRequest

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title="AI Room Styler", version="0.4.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


def get_current_user(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


@app.on_event("startup")
def on_startup() -> None:
    init_db()


# Ensure DB schema is available during tests/import usage without lifespan hooks.
init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (BASE_DIR / "app" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/ops", response_class=HTMLResponse)
def ops_dashboard() -> str:
    return (BASE_DIR / "app" / "static" / "ops.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "ai-room-styler"}


@app.post("/v1/auth/register")
def auth_register(payload: RegisterRequest):
    try:
        user = create_user(payload.email, payload.password, payload.display_name)
        log_event("auth.register", "user registered", context={"user_id": user["user_id"], "email": user["email"]})
    except Exception as e:
        raise HTTPException(status_code=400, detail="Email already exists") from e
    token = create_token(user["user_id"])
    return {"token": token, "user": user}


@app.post("/v1/auth/login")
def auth_login(payload: LoginRequest):
    user = authenticate_user(payload.email, payload.password)
    if not user:
        log_event("auth.login", "login failed", level="warn", context={"email": payload.email})
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user["user_id"])
    log_event("auth.login", "login success", context={"user_id": user["user_id"]})
    return {"token": token, "user": user}


@app.get("/v1/me")
def me(authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    return {"user": user}


@app.get("/v1/scan-guidelines")
def scan_guidelines():
    return {
        "photo_count": {"min": 4, "recommended": 6, "max": 10},
        "angles": [
            "방 입구에서 좌/우 코너 포함 전경",
            "창문/문이 보이게 반대 방향",
            "바닥-벽 경계가 잘 보이는 각도",
            "천장 모서리 1장 (높이 추정 보조)",
        ],
        "quality": [
            "밝은 조명",
            "0.5x 광각 가능하면 사용",
            "모션블러 없는 고정 촬영",
            "가급적 기준 물체(A4/문/침대) 포함",
        ],
    }


@app.post("/v1/room/photos")
async def upload_room_photos(
    room_id: str = Form(...),
    files: list[UploadFile] = File(...),
    authorization: Optional[str] = Header(None),
):
    user = get_current_user(authorization)
    room = get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room_id not found")
    if room["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    if len(files) < 2:
        raise HTTPException(status_code=400, detail="at least 2 photos required")
    if len(files) > 12:
        raise HTTPException(status_code=400, detail="max 12 photos")

    saved = []
    for f in files:
        content = await f.read()
        saved.append(save_room_photo(room_id, f.filename or "photo.jpg", content))

    log_event("room.photos.upload", "room photos uploaded", context={"room_id": room_id, "count": len(saved)})
    return {
        "room_id": room_id,
        "uploaded_count": len(saved),
        "photos": [{"photo_id": p["photo_id"], "original_name": p["original_name"]} for p in saved],
        "next": "사진 스캔 파이프라인에서 depth/segmentation 분석 예정",
    }


@app.get("/v1/catalog")
def get_catalog(category: Optional[str] = Query(None), max_price: Optional[int] = Query(None)):
    items = load_catalog()
    if category:
        items = [i for i in items if i["category"] == category]
    if max_price:
        items = [i for i in items if i["price_krw"] <= max_price]
    return {"count": len(items), "items": items}


@app.post("/v1/room/estimate")
def room_estimate(payload: RoomEstimateRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    room = save_room(user["user_id"], payload.model_dump())
    log_event("room.estimate", "room profile estimated", context={"room_id": room["room_id"], "user_id": user["user_id"]})
    return {
        "room_profile": {
            "room_id": room["room_id"],
            "area_m2": room["area_m2"],
            "recommended_walkway_cm": 60,
        }
    }


@app.post("/v1/recommendations")
def recommendations(payload: RecommendationRequest, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    room = get_room(payload.room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room_id not found")
    if room["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    result = recommend(room, payload.required_categories, load_catalog())
    run_id = save_recommendation(payload.room_id, result)
    result["run_id"] = run_id
    log_event("recommendations.run", "recommendation generated", context={"room_id": payload.room_id, "run_id": run_id})
    return result


@app.get("/v1/ops/logs")
def ops_logs(limit: int = Query(50, ge=1, le=200), authorization: Optional[str] = Header(None)):
    # lightweight protection: reuse standard auth for internal dashboard use
    _ = get_current_user(authorization)
    return {"count": limit, "items": list_ops_logs(limit=limit)}
