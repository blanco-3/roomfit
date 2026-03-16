from __future__ import annotations

from typing import List


def style_score(item: dict, mood: str, purpose: str, pref_colors: List[str] = [], pref_materials: List[str] = []) -> float:
    mood_tokens = set(mood.lower().replace("-", "_").split("_"))
    purpose_tokens = set(purpose.lower().replace("-", "_").split("_"))
    tags = set(t.lower() for t in item.get("style_tags", []))

    score = 0.0
    score += 0.5 * (len(tags & mood_tokens) / max(1, len(mood_tokens)))
    score += 0.3 * (len(tags & purpose_tokens) / max(1, len(purpose_tokens)))

    # 색상/소재 선호도 보너스 (enriched 데이터 있을 때)
    if pref_colors:
        item_colors = set(c.lower() for c in item.get("colors", []))
        if item_colors & set(c.lower() for c in pref_colors):
            score += 0.15
    if pref_materials:
        item_mats = set(m.lower() for m in item.get("materials", []))
        if item_mats & set(m.lower() for m in pref_materials):
            score += 0.15

    return round(min(1.0, score), 3)


def footprint_cm2(item: dict) -> int:
    return int(item["width_cm"] * item["depth_cm"])


def walkway_fit(room: dict, items: List[dict], min_walkway_cm: int = 60) -> bool:
    room_area = room["width_cm"] * room["length_cm"]
    occupied = sum(footprint_cm2(i) for i in items)
    occupancy_ratio = occupied / max(room_area, 1)
    return occupancy_ratio <= 0.55 and min(room["width_cm"], room["length_cm"]) >= (min_walkway_cm * 3)


ITEMS_PER_CATEGORY = 3  # 카테고리당 추천 항목 수


def recommend(room: dict, required_categories: List[str], catalog: List[dict],
              pref_colors: List[str] = [], pref_materials: List[str] = []) -> dict:
    selected = []
    total_price = 0
    mood_tokens = set(room["mood"].lower().replace("-", "_").split("_"))
    purpose_tokens = set(room["purpose"].lower().replace("-", "_").split("_"))

    for cat in required_categories:
        candidates = [i for i in catalog if i["category"] == cat and i["price_krw"] <= room["budget_krw"]]
        if not candidates:
            continue

        scored = []
        for item in candidates:
            s_score = style_score(item, room["mood"], room["purpose"], pref_colors, pref_materials)
            size_penalty = footprint_cm2(item) / max(1, room["width_cm"] * room["length_cm"])
            final_score = (0.75 * s_score) + (0.25 * (1 - min(size_penalty, 1)))
            scored.append((round(final_score, 3), item))

        scored.sort(key=lambda x: x[0], reverse=True)

        for rank, (score, item) in enumerate(scored[:ITEMS_PER_CATEGORY]):
            matched = set(t.lower() for t in item.get("style_tags", [])) & (mood_tokens | purpose_tokens)
            reason = f"스타일 매칭: {', '.join(sorted(matched))}" if matched else "예산/치수 적합"

            selected.append({
                "id": item["id"],
                "name": item["name"],
                "category": item["category"],
                "price_krw": item["price_krw"],
                "dimensions_cm": {
                    "width": item["width_cm"],
                    "depth": item["depth_cm"],
                    "height": item["height_cm"],
                },
                "source": item["source"],
                "url": item["url"],
                "image_url": item.get("image_url", ""),
                "score": score,
                "rank": rank + 1,
                "reason": reason,
            })
            if rank == 0:
                total_price += int(item["price_krw"])  # 합계는 1위 항목 기준

    # walkway check: rank=1 항목만 대상
    top_items = [i for i in selected if i["rank"] == 1]
    fits = walkway_fit(
        room,
        [{"width_cm": i["dimensions_cm"]["width"], "depth_cm": i["dimensions_cm"]["depth"]} for i in top_items],
    )
    if not fits and top_items:
        # 가장 큰 카테고리의 rank=1 제거
        largest = max(top_items, key=lambda i: i["dimensions_cm"]["width"] * i["dimensions_cm"]["depth"])
        drop_cat = largest["category"]
        selected = [i for i in selected if i["category"] != drop_cat]
        total_price = sum(i["price_krw"] for i in selected if i["rank"] == 1)

    fit_score = round(min(1.0, 1 - (total_price / max(room["budget_krw"], 1) * 0.2)), 3)
    top_scores = [i["score"] for i in selected if i["rank"] == 1]
    style_avg = round(sum(top_scores) / max(1, len(top_scores)), 3)
    budget = int(room["budget_krw"])

    return {
        "summary": {
            "total_price_krw": total_price,
            "fit_score": fit_score,
            "style_score": style_avg,
            "selected_count": len([i for i in selected if i["rank"] == 1]),
            "budget_krw": budget,
            "remaining_budget_krw": max(0, budget - total_price),
            "budget_usage_pct": round((total_price / max(budget, 1)) * 100, 1),
        },
        "items": selected,
    }
