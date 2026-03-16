from __future__ import annotations

from app.db import count_room_photos

REFERENCE_WIDTHS_CM = {
    "credit_card": 8.6,
    "a4_short": 21.0,
    "a4_long": 29.7,
    "door_single": 90.0,
    "desk_standard": 120.0,
    "single_bed": 100.0,
}


def infer_room_dimensions_from_photos(photo_count: int, reference_object: str) -> dict:
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
