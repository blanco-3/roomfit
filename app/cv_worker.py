from __future__ import annotations

import base64
import json
import os
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

_CV_PROMPT = (
    "이 방 사진들을 분석해서 방의 너비/길이/높이(cm)와 신뢰도를 추정하세요. "
    "기준 물체가 보이면 그것을 기준으로 치수를 추정하세요. "
    "반드시 아래 JSON 형식으로만 응답하세요:\n"
    '{"width_cm": 280, "length_cm": 340, "height_cm": 240, "confidence": 0.75, "analysis_notes": "..."}'
)


def infer_room_dimensions_from_photos(
    photo_count: int,
    reference_object: str,
    photo_paths: Optional[list[str]] = None,
) -> dict:
    """방 사진에서 치수 추정. Gemini → OpenAI → mock 순으로 fallback."""
    google_key = os.getenv("GOOGLE_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if google_key and photo_paths:
        try:
            return _gemini_infer(photo_paths, reference_object, google_key)
        except Exception:
            pass

    if openai_key and photo_paths:
        try:
            return _openai_infer(photo_paths, reference_object, openai_key)
        except Exception:
            pass

    return _mock_infer(photo_count, reference_object)


def _gemini_infer(photo_paths: list[str], reference_object: str, api_key: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    ref_cm = REFERENCE_WIDTHS_CM.get(reference_object, 21.0)
    prompt = f"기준 물체: {reference_object} ({ref_cm}cm). " + _CV_PROMPT

    parts: list = [types.Part(text=prompt)]
    loaded = 0
    for path in photo_paths[:4]:
        try:
            img_bytes = Path(path).read_bytes()
            if len(img_bytes) < 100:
                continue
            parts.append(types.Part(
                inline_data=types.Blob(mime_type="image/jpeg", data=img_bytes)
            ))
            loaded += 1
        except Exception:
            continue

    if loaded == 0:
        return _mock_infer(len(photo_paths), reference_object)

    response = client.models.generate_content(
        model=model,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    raw = json.loads(response.text or "{}")
    return _parse_cv_result(raw, reference_object, len(photo_paths), "gemini-vision")


def _openai_infer(photo_paths: list[str], reference_object: str, api_key: str) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    ref_cm = REFERENCE_WIDTHS_CM.get(reference_object, 21.0)

    content: list = [{"type": "text", "text": f"기준 물체: {reference_object} ({ref_cm}cm). " + _CV_PROMPT}]
    loaded = 0
    for path in photo_paths[:4]:
        try:
            img_bytes = Path(path).read_bytes()
            if len(img_bytes) < 100:
                continue
            b64 = base64.b64encode(img_bytes).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            loaded += 1
        except Exception:
            continue

    if loaded == 0:
        return _mock_infer(len(photo_paths), reference_object)

    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        messages=[{"role": "user", "content": content}],
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    raw = json.loads(resp.choices[0].message.content or "{}")
    return _parse_cv_result(raw, reference_object, len(photo_paths), "gpt-4o-vision")


def _parse_cv_result(raw: dict, reference_object: str, photo_count: int, engine: str) -> dict:
    width_cm = max(180, min(int(raw.get("width_cm", 280)), 600))
    length_cm = max(180, min(int(raw.get("length_cm", 340)), 800))
    height_cm = max(210, min(int(raw.get("height_cm", 240)), 320))
    confidence = max(0.0, min(float(raw.get("confidence", 0.7)), 1.0))

    return {
        "engine": engine,
        "reference_object": reference_object,
        "photo_count": photo_count,
        "estimated": {
            "width_cm": width_cm,
            "length_cm": length_cm,
            "height_cm": height_cm,
            "area_m2": round((width_cm * length_cm) / 10000, 2),
            "recommended_walkway_cm": 60,
        },
        "confidence": round(confidence, 2),
        "needs_manual_review": confidence < 0.7,
        "analysis_notes": raw.get("analysis_notes", ""),
    }


def _mock_infer(photo_count: int, reference_object: str) -> dict:
    base_scale = REFERENCE_WIDTHS_CM.get(reference_object, 21.0)
    confidence = min(0.52 + (photo_count * 0.06), 0.9)

    width_cm = max(180, min(int(240 + (base_scale * 2.8) + (photo_count * 12)), 600))
    length_cm = max(180, min(int(300 + (base_scale * 3.1) + (photo_count * 14)), 800))
    height_cm = max(210, min(int(228 + (photo_count * 2)), 320))

    return {
        "engine": "mock-local-cv-v1",
        "reference_object": reference_object,
        "photo_count": photo_count,
        "estimated": {
            "width_cm": width_cm,
            "length_cm": length_cm,
            "height_cm": height_cm,
            "area_m2": round((width_cm * length_cm) / 10000, 2),
            "recommended_walkway_cm": 60,
        },
        "confidence": round(confidence, 2),
        "needs_manual_review": confidence < 0.7,
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
            "width_cm": int(room["width_cm"]),
            "length_cm": int(room["length_cm"]),
            "height_cm": int(room["height_cm"]),
            "area_m2": area_m2,
            "usable_area_m2": usable_area_m2,
            "recommended_walkway_cm": 60,
        },
        "confidence": round(confidence, 2),
    }
