from __future__ import annotations

from app.db import count_room_photos


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
