from __future__ import annotations

import base64
import json
import os
import re
import statistics
from pathlib import Path
from typing import Optional

from app.db import count_room_photos

REFERENCE_WIDTHS_CM: dict[str, float] = {
    "credit_card": 8.6,
    "a4_short": 21.0,
    "a4_long": 29.7,
    "door_single": 90.0,
    "desk_standard": 120.0,
    "single_bed": 100.0,
}

# 한국 주거 공간 표준 치수 (사전 지식으로 활용)
_KR_ROOM_PRIORS = {
    "studio":     {"width_cm": 330, "length_cm": 450, "height_cm": 240},  # 원룸
    "bedroom":    {"width_cm": 300, "length_cm": 360, "height_cm": 240},  # 침실
    "living":     {"width_cm": 380, "length_cm": 500, "height_cm": 245},  # 거실
    "default":    {"width_cm": 300, "length_cm": 380, "height_cm": 240},
}

# ── 체인-오브-싱크 2단계 프롬프트 ──────────────────────────────────────────

_STEP1_PROMPT = """You are a precise room measurement assistant.

STEP 1 — Identify calibration anchors:
Look at this room photo carefully. List every object you can see that has a known real-world size:
- Standard door: 200cm tall × 90cm wide
- Standard ceiling height in Korean apartments: 230~250cm
- A4 paper: 21×29.7cm
- Credit card: 8.5×5.4cm
- Standard desk: 120cm wide × 75cm tall
- Standard single bed: 100cm wide × 200cm long
- Standard double bed: 140~160cm wide × 200cm long
- Standard dining chair seat height: 45cm
- Standard light switch: ~8cm wide (mounted 120cm from floor)
- Baseboard height: ~10cm

List what you see: object name, estimated pixel size in the photo, and known real-world size.
Then calculate the pixel-per-cm ratio from the most reliable anchor.

STEP 2 — Estimate room dimensions:
Using the calibration ratio from Step 1:
- Measure the visible wall widths in pixels
- Estimate depth using perspective (foreshortening)
- Account for the camera field of view

STEP 3 — Output JSON only:
{"width_cm": <int>, "length_cm": <int>, "height_cm": <int>, "confidence": <0.0-1.0>, "anchors_used": ["door", "ceiling"], "analysis_notes": "<brief reasoning>"}

Rules:
- width_cm: shorter horizontal dimension (180–600)
- length_cm: longer dimension (180–800)
- height_cm: floor-to-ceiling (210–320)
- confidence: 0.9 if 2+ anchors matched, 0.7 if 1 anchor, 0.4 if guessing
- Output ONLY the JSON, no other text"""

_STEP1_WITH_REF_PROMPT = """You are a precise room measurement assistant.

A reference object is visible in this photo: {ref_name} (real width: {ref_cm}cm).

STEP 1 — Find the reference object and measure it in pixels.
Calculate pixel-per-cm ratio = (reference object pixel width) / {ref_cm}

STEP 2 — Measure the room:
Using the pixel-per-cm ratio:
- Measure the back wall width
- Estimate room depth from perspective
- Measure floor-to-ceiling height

STEP 3 — Output JSON only:
{{"width_cm": <int>, "length_cm": <int>, "height_cm": <int>, "confidence": <0.0-1.0>, "anchors_used": ["{ref_name}"], "analysis_notes": "<pixel measurements used>"}}

Rules:
- width_cm: 180–600, length_cm: 180–800, height_cm: 210–320
- confidence: 0.85 if reference clearly visible, 0.5 if partially visible
- Output ONLY the JSON"""


def infer_room_dimensions_from_photos(
    photo_count: int,
    reference_object: str,
    photo_paths: Optional[list[str]] = None,
) -> dict:
    """방 사진에서 치수 추정. 다중 사진 투표 집계 + Groq → Gemini → mock fallback."""
    groq_key = os.getenv("GROQ_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")

    if not photo_paths:
        return _mock_infer(photo_count, reference_object)

    valid_paths = [p for p in photo_paths if Path(p).exists() and Path(p).stat().st_size > 100]
    if not valid_paths:
        return _mock_infer(photo_count, reference_object)

    results: list[dict] = []

    # 각 사진을 개별 추론 후 집계 (multi-photo voting)
    for path in valid_paths[:4]:
        if groq_key:
            try:
                r = _groq_infer_single(path, reference_object, groq_key)
                if r:
                    results.append(r)
                    continue
            except Exception:
                pass
        if google_key:
            try:
                r = _gemini_infer_single(path, reference_object, google_key)
                if r:
                    results.append(r)
            except Exception:
                pass

    if not results:
        return _mock_infer(photo_count, reference_object)

    return _aggregate_results(results, reference_object, len(valid_paths))


# ── 단일 사진 추론 ────────────────────────────────────────────────────────────

def _groq_infer_single(photo_path: str, reference_object: str, api_key: str) -> Optional[dict]:
    from groq import Groq

    client = Groq(api_key=api_key)
    model = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

    ref_cm = REFERENCE_WIDTHS_CM.get(reference_object, 21.0)
    has_ref = reference_object != "none"
    prompt = (
        _STEP1_WITH_REF_PROMPT.format(ref_name=reference_object, ref_cm=ref_cm)
        if has_ref else _STEP1_PROMPT
    )

    img_bytes = Path(photo_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode()

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
        max_tokens=1024,
    )
    raw_text = resp.choices[0].message.content or "{}"
    m = re.search(r"\{[^{}]*\"width_cm\"[^{}]*\}", raw_text, re.DOTALL)
    if not m:
        return None
    raw = json.loads(m.group(0))
    return _parse_cv_result(raw, reference_object, 1, f"groq-{model}")


def _gemini_infer_single(photo_path: str, reference_object: str, api_key: str) -> Optional[dict]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

    ref_cm = REFERENCE_WIDTHS_CM.get(reference_object, 21.0)
    has_ref = reference_object != "none"
    prompt = (
        _STEP1_WITH_REF_PROMPT.format(ref_name=reference_object, ref_cm=ref_cm)
        if has_ref else _STEP1_PROMPT
    )

    img_bytes = Path(photo_path).read_bytes()
    response = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=[
            types.Part(text=prompt),
            types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=img_bytes)),
        ])],
    )
    raw_text = response.text or "{}"
    m = re.search(r"\{[^{}]*\"width_cm\"[^{}]*\}", raw_text, re.DOTALL)
    if not m:
        return None
    raw = json.loads(m.group(0))
    return _parse_cv_result(raw, reference_object, 1, "gemini-vision")


# ── 기존 호환용 (auto-estimate 엔드포인트에서 여러 장 한 번에 보내는 경우) ──

def _groq_infer(photo_paths: list[str], reference_object: str, api_key: str) -> dict:
    results = [r for p in photo_paths[:4] if (r := _groq_infer_single(p, reference_object, api_key))]
    if not results:
        return _mock_infer(len(photo_paths), reference_object)
    return _aggregate_results(results, reference_object, len(photo_paths))


def _gemini_infer(photo_paths: list[str], reference_object: str, api_key: str) -> dict:
    results = [r for p in photo_paths[:4] if (r := _gemini_infer_single(p, reference_object, api_key))]
    if not results:
        return _mock_infer(len(photo_paths), reference_object)
    return _aggregate_results(results, reference_object, len(photo_paths))


def _openai_infer(photo_paths: list[str], reference_object: str, api_key: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    ref_cm = REFERENCE_WIDTHS_CM.get(reference_object, 21.0)
    has_ref = reference_object != "none"
    prompt = (
        _STEP1_WITH_REF_PROMPT.format(ref_name=reference_object, ref_cm=ref_cm)
        if has_ref else _STEP1_PROMPT
    )

    results: list[dict] = []
    for path in photo_paths[:4]:
        try:
            img_bytes = Path(path).read_bytes()
            if len(img_bytes) < 100:
                continue
            b64 = base64.b64encode(img_bytes).decode()
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ]}],
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            raw = json.loads(resp.choices[0].message.content or "{}")
            r = _parse_cv_result(raw, reference_object, 1, "gpt-4o-vision")
            results.append(r)
        except Exception:
            continue

    if not results:
        return _mock_infer(len(photo_paths), reference_object)
    return _aggregate_results(results, reference_object, len(photo_paths))


# ── 집계: 중앙값 기반 투표 ───────────────────────────────────────────────────

def _aggregate_results(results: list[dict], reference_object: str, total_photos: int) -> dict:
    """여러 추론 결과를 중앙값으로 집계. 이상치 제거 포함."""
    if len(results) == 1:
        return results[0]

    widths  = [r["estimated"]["width_cm"]  for r in results]
    lengths = [r["estimated"]["length_cm"] for r in results]
    heights = [r["estimated"]["height_cm"] for r in results]
    confs   = [r["confidence"]             for r in results]

    # 이상치 필터: 중앙값 ±40% 범위만 사용
    def filtered_median(vals: list[float]) -> float:
        med = statistics.median(vals)
        filtered = [v for v in vals if abs(v - med) / max(med, 1) <= 0.4]
        return statistics.median(filtered) if filtered else med

    width_cm  = int(filtered_median(widths))
    length_cm = int(filtered_median(lengths))
    height_cm = int(filtered_median(heights))
    confidence = round(min(statistics.mean(confs) + 0.05 * (len(results) - 1), 1.0), 2)

    engines = list({r.get("engine", "") for r in results})
    notes   = "; ".join(r.get("analysis_notes", "") for r in results if r.get("analysis_notes"))

    return {
        "engine": f"ensemble({','.join(engines)})",
        "reference_object": reference_object,
        "photo_count": total_photos,
        "estimated": {
            "width_cm":  max(180, min(width_cm,  600)),
            "length_cm": max(180, min(length_cm, 800)),
            "height_cm": max(210, min(height_cm, 320)),
            "area_m2": round((width_cm * length_cm) / 10000, 2),
            "recommended_walkway_cm": 60,
        },
        "confidence": confidence,
        "needs_manual_review": confidence < 0.65,
        "analysis_notes": notes[:300] if notes else f"{len(results)}장 앙상블 집계",
    }


# ── 파싱 & mock ───────────────────────────────────────────────────────────────

def _parse_cv_result(raw: dict, reference_object: str, photo_count: int, engine: str) -> dict:
    width_cm  = max(180, min(int(raw.get("width_cm",  280)), 600))
    length_cm = max(180, min(int(raw.get("length_cm", 340)), 800))
    height_cm = max(210, min(int(raw.get("height_cm", 240)), 320))
    confidence = max(0.0, min(float(raw.get("confidence", 0.5)), 1.0))

    return {
        "engine": engine,
        "reference_object": reference_object,
        "photo_count": photo_count,
        "estimated": {
            "width_cm":  width_cm,
            "length_cm": length_cm,
            "height_cm": height_cm,
            "area_m2": round((width_cm * length_cm) / 10000, 2),
            "recommended_walkway_cm": 60,
        },
        "confidence": round(confidence, 2),
        "needs_manual_review": confidence < 0.65,
        "analysis_notes": raw.get("analysis_notes", ""),
    }


def _mock_infer(photo_count: int, reference_object: str) -> dict:
    base_scale = REFERENCE_WIDTHS_CM.get(reference_object, 21.0)
    confidence = min(0.35 + (photo_count * 0.05), 0.55)

    prior = _KR_ROOM_PRIORS["default"]
    width_cm  = max(180, min(int(prior["width_cm"]  + base_scale * 0.5), 600))
    length_cm = max(180, min(int(prior["length_cm"] + base_scale * 0.5), 800))
    height_cm = int(prior["height_cm"])

    return {
        "engine": "mock-kr-prior-v2",
        "reference_object": reference_object,
        "photo_count": photo_count,
        "estimated": {
            "width_cm":  width_cm,
            "length_cm": length_cm,
            "height_cm": height_cm,
            "area_m2": round((width_cm * length_cm) / 10000, 2),
            "recommended_walkway_cm": 60,
        },
        "confidence": round(confidence, 2),
        "needs_manual_review": True,
        "analysis_notes": "사진 없음 — 한국 평균 치수 사용",
    }


def mock_measurement_estimation(room: dict) -> dict:
    """Mocked CV estimation for scaffolding."""
    photo_count = count_room_photos(room["room_id"])
    area_m2 = float(room["area_m2"])
    usable_area_m2 = round(max(area_m2 * 0.88, 1.0), 2)
    confidence = min(0.55 + (photo_count * 0.04), 0.92)

    return {
        "engine": "mock-cv-v0",
        "photo_count": photo_count,
        "estimated": {
            "width_cm":  int(room["width_cm"]),
            "length_cm": int(room["length_cm"]),
            "height_cm": int(room["height_cm"]),
            "area_m2":   area_m2,
            "usable_area_m2": usable_area_m2,
            "recommended_walkway_cm": 60,
        },
        "confidence": round(confidence, 2),
    }
