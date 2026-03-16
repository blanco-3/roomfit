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

_CV_SYSTEM_PROMPT = """당신은 방 사진을 분석해서 실측 치수를 추정하는 컴퓨터 비전 전문가입니다.
주어진 사진들을 분석해서 반드시 아래 JSON 형식으로만 응답하세요:
{
  "width_cm": 280,
  "length_cm": 340,
  "height_cm": 240,
  "confidence": 0.75,
  "analysis_notes": "기준 물체를 기준으로 추정..."
}
- 기준 물체가 보이면 그것을 기준으로 치수를 추정하세요
- confidence는 0.0~1.0, 0.7 미만이면 재촬영 권장
- 치수 범위: width/length 180~800cm, height 210~320cm"""


def infer_room_dimensions_from_photos(
    photo_count: int,
    reference_object: str,
    photo_paths: Optional[list[str]] = None,
) -> dict:
    """방 사진에서 치수 추정.

    GPT-4o vision을 우선 시도하고, API key가 없거나 실패하면 mock으로 fallback.
    photo_paths를 제공하면 실제 이미지를 vision API에 전송.
    """
    api_key = os.getenv("OPENAI_API_KEY")

    if api_key and photo_paths:
        try:
            return _vision_infer(photo_paths, reference_object, api_key)
        except Exception:
            pass  # fallback to mock

    return _mock_infer(photo_count, reference_object)


def _vision_infer(photo_paths: list[str], reference_object: str, api_key: str) -> dict:
    from openai import OpenAI  # lazy import

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    ref_cm = REFERENCE_WIDTHS_CM.get(reference_object, 21.0)

    content: list = [
        {
            "type": "text",
            "text": (
                f"이 방 사진들을 분석하세요. "
                f"기준 물체: {reference_object} (너비 {ref_cm}cm). "
                "방의 너비/길이/높이(cm)와 신뢰도를 추정해 JSON으로만 반환하세요."
            ),
        }
    ]

    loaded = 0
    for path in photo_paths[:4]:  # max 4장 전송 (비용/속도)
        try:
            img_bytes = Path(path).read_bytes()
            if len(img_bytes) < 100:  # 너무 작은 파일(fake) 스킵
                continue
            b64 = base64.b64encode(img_bytes).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            })
            loaded += 1
        except Exception:
            continue

    if loaded == 0:
        return _mock_infer(len(photo_paths), reference_object)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _CV_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        max_tokens=512,
        response_format={"type": "json_object"},
    )

    raw = json.loads(resp.choices[0].message.content or "{}")
    width_cm = max(180, min(int(raw.get("width_cm", 280)), 600))
    length_cm = max(180, min(int(raw.get("length_cm", 340)), 800))
    height_cm = max(210, min(int(raw.get("height_cm", 240)), 320))
    confidence = max(0.0, min(float(raw.get("confidence", 0.7)), 1.0))

    return {
        "engine": "gpt-4o-vision",
        "reference_object": reference_object,
        "photo_count": len(photo_paths),
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

    width_cm = int(240 + (base_scale * 2.8) + (photo_count * 12))
    length_cm = int(300 + (base_scale * 3.1) + (photo_count * 14))
    height_cm = int(228 + (photo_count * 2))

    width_cm = max(180, min(width_cm, 600))
    length_cm = max(180, min(length_cm, 800))
    height_cm = max(210, min(height_cm, 320))

    area_m2 = round((width_cm * length_cm) / 10000, 2)
    return {
        "engine": "mock-local-cv-v1",
        "reference_object": reference_object,
        "photo_count": photo_count,
        "estimated": {
            "width_cm": width_cm,
            "length_cm": length_cm,
            "height_cm": height_cm,
            "area_m2": area_m2,
            "recommended_walkway_cm": 60,
        },
        "confidence": round(confidence, 2),
        "needs_manual_review": confidence < 0.7,
    }


def mock_measurement_estimation(room: dict) -> dict:
    """Mocked CV estimation for scaffolding.

    Heuristic only (no paid APIs):
    - confidence increases with room photo count
    - suggested usable area applies small deduction
    """
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
