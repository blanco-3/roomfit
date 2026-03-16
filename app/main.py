from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.cv_worker import infer_room_dimensions_from_photos, mock_measurement_estimation
from app.db import (
    authenticate_user,
    count_room_photos,
    create_cv_job,
    create_token,
    create_user,
    get_cv_job,
    get_room,
    get_user_by_token,
    init_db,
    list_ops_logs,
    list_recommendation_runs,
    load_catalog,
    log_event,
    save_recommendation,
    save_room,
    save_room_photo,
    update_cv_job,
)
from app.recommender import recommend
from app.schemas import LoginRequest, RecommendationRequest, RegisterRequest, RoomEstimateRequest

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Room Styler", version="0.5.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


def get_current_user(authorization: Optional[str]) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    user = get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


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


@app.post("/v1/room/auto-estimate")
async def room_auto_estimate(
    reference_object: str = Form(...),
    files: list[UploadFile] = File(...),
    mood: str = Form("minimal_warm"),
    purpose: str = Form("work_sleep"),
    budget_krw: int = Form(1200000),
    room_id: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    user = get_current_user(authorization)
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="at least 2 photos required")
    if len(files) > 12:
        raise HTTPException(status_code=400, detail="max 12 photos")

    target_room_id = room_id
    if target_room_id:
        room = get_room(target_room_id)
        if not room:
            raise HTTPException(status_code=404, detail="room_id not found")
        if room["user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="forbidden")
    else:
        bootstrap = save_room(
            user["user_id"],
            {
                "width_cm": 280,
                "length_cm": 340,
                "height_cm": 240,
                "mood": mood,
                "purpose": purpose,
                "budget_krw": budget_krw,
                "estimate_source": "bootstrap",
            },
        )
        target_room_id = bootstrap["room_id"]

    saved = []
    for f in files:
        content = await f.read()
        saved.append(save_room_photo(target_room_id, f.filename or "photo.jpg", content))

    estimate = infer_room_dimensions_from_photos(len(saved), reference_object)
    room = save_room(
        user["user_id"],
        {
            "room_id": target_room_id,
            "width_cm": estimate["estimated"]["width_cm"],
            "length_cm": estimate["estimated"]["length_cm"],
            "height_cm": estimate["estimated"]["height_cm"],
            "mood": mood,
            "purpose": purpose,
            "budget_krw": budget_krw,
            "estimate_source": "ai_photo_reference",
            "estimate_confidence": estimate["confidence"],
            "estimation_notes": f"reference={reference_object}; photos={len(saved)}",
        },
    )
    log_event(
        "room.auto_estimate",
        "room profile auto-estimated from photos",
        context={"room_id": target_room_id, "photo_count": len(saved), "confidence": estimate["confidence"]},
    )

    return {
        "room_profile": {
            "room_id": room["room_id"],
            "area_m2": room["area_m2"],
            "width_cm": estimate["estimated"]["width_cm"],
            "length_cm": estimate["estimated"]["length_cm"],
            "height_cm": estimate["estimated"]["height_cm"],
            "estimate_source": room["estimate_source"],
            "estimate_confidence": room["estimate_confidence"],
            "editable": True,
            "recommended_walkway_cm": 60,
        },
        "photos": [{"photo_id": p["photo_id"], "original_name": p["original_name"]} for p in saved],
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
            "estimate_source": room.get("estimate_source", payload.estimate_source),
            "estimate_confidence": room.get("estimate_confidence", payload.estimate_confidence),
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
    result["room_estimation"] = {
        "source": room.get("estimate_source", "manual"),
        "confidence": room.get("estimate_confidence"),
        "width_cm": room.get("width_cm"),
        "length_cm": room.get("length_cm"),
        "height_cm": room.get("height_cm"),
    }
    log_event("recommendations.run", "recommendation generated", context={"room_id": payload.room_id, "run_id": run_id})
    return result


@app.get("/v1/recommendations/history")
def recommendation_history(limit: int = Query(20, ge=1, le=100), authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    items = list_recommendation_runs(user_id=user["user_id"], limit=limit)
    return {"count": len(items), "items": items}


@app.post("/v1/cv/jobs")
def create_room_cv_job(room_id: str = Query(...), authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    room = get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room_id not found")
    if room["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")

    photo_count = count_room_photos(room_id)
    if photo_count < 2:
        raise HTTPException(status_code=400, detail="at least 2 uploaded photos required before CV job")

    job_id = create_cv_job(room_id=room_id, user_id=user["user_id"])
    log_event("cv.job.queued", "cv estimation job queued", context={"job_id": job_id, "room_id": room_id})

    try:
        update_cv_job(job_id, "running")
        result = mock_measurement_estimation(room)
        update_cv_job(job_id, "completed", result=result)
        log_event("cv.job.completed", "cv estimation job completed", context={"job_id": job_id, "room_id": room_id})
    except Exception as e:
        update_cv_job(job_id, "failed", error_text=str(e))
        log_event("cv.job.failed", "cv estimation job failed", level="error", context={"job_id": job_id, "error": str(e)})

    item = get_cv_job(job_id)
    return {"job": item}


@app.get("/v1/cv/jobs/{job_id}")
def get_room_cv_job(job_id: str, authorization: Optional[str] = Header(None)):
    user = get_current_user(authorization)
    job = get_cv_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    if job["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="forbidden")
    return {"job": job}


@app.get("/v1/ops/logs")
def ops_logs(limit: int = Query(50, ge=1, le=200), authorization: Optional[str] = Header(None)):
    # lightweight protection: reuse standard auth for internal dashboard use
    _ = get_current_user(authorization)
    return {"count": limit, "items": list_ops_logs(limit=limit)}
