from __future__ import annotations

from typing import List


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
    room_area = room["width_cm"] * room["length_cm"]
    occupied = sum(footprint_cm2(i) for i in items)
    occupancy_ratio = occupied / max(room_area, 1)
    return occupancy_ratio <= 0.55 and min(room["width_cm"], room["length_cm"]) >= (min_walkway_cm * 3)


def recommend(room: dict, required_categories: List[str], catalog: List[dict]) -> dict:
    selected = []
    alternatives: dict[str, list[dict]] = {}
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

        # reason: 실제 매칭된 스타일 태그 기반
        matched = set(t.lower() for t in best_item.get("style_tags", [])) & (
            set(room["mood"].lower().replace("-", "_").split("_")) |
            set(room["purpose"].lower().replace("-", "_").split("_"))
        )
        reason = f"스타일 매칭: {', '.join(sorted(matched))}" if matched else "예산/치수 적합"

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
            "image_url": best_item.get("image_url", ""),
            "score": best_score,
            "reason": reason,
        })
        alternatives[cat] = [
            {
                "id": alt_item["id"],
                "name": alt_item["name"],
                "price_krw": alt_item["price_krw"],
                "score": alt_score,
                "url": alt_item["url"],
            }
            for alt_score, alt_item in scored[1:3]
        ]
        total_price += int(best_item["price_krw"])

    fits = walkway_fit(
        room,
        [{"width_cm": i["dimensions_cm"]["width"], "depth_cm": i["dimensions_cm"]["depth"]} for i in selected],
    )

    if not fits and selected:
        selected = sorted(selected, key=lambda i: i["dimensions_cm"]["width"] * i["dimensions_cm"]["depth"])
        selected = selected[:-1]
        total_price = sum(i["price_krw"] for i in selected)

    fit_score = round(min(1.0, 1 - (total_price / max(room["budget_krw"], 1) * 0.2)), 3)
    style_avg = round(sum(i["score"] for i in selected) / max(1, len(selected)), 3)
    budget = int(room["budget_krw"])

    return {
        "summary": {
            "total_price_krw": total_price,
            "fit_score": fit_score,
            "style_score": style_avg,
            "selected_count": len(selected),
            "budget_krw": budget,
            "remaining_budget_krw": max(0, budget - total_price),
            "budget_usage_pct": round((total_price / max(budget, 1)) * 100, 1),
        },
        "items": selected,
        "alternatives": alternatives,
    }
