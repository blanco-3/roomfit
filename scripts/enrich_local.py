#!/usr/bin/env python3
"""
상품명 + 카테고리 키워드 기반 로컬 enrichment (API 불필요).
Naver Shopping 상품명에는 색상/소재/스타일 정보가 풍부하게 포함되어 있음.

실행:
    python scripts/enrich_local.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CATALOG_PATH = Path(__file__).parent.parent / "data" / "furniture_catalog.json"

# ── 색상 키워드 ──────────────────────────────────────────────────
COLOR_MAP: list[tuple[str, list[str]]] = [
    ("white",   ["화이트", "흰", "white", "아이보리", "ivory", "크림", "cream"]),
    ("black",   ["블랙", "black", "다크블랙"]),
    ("gray",    ["그레이", "gray", "grey", "실버", "silver"]),
    ("brown",   ["브라운", "brown", "다크브라운", "월넛", "walnut", "초코"]),
    ("natural", ["내추럴", "natural", "베이지", "beige", "샌드", "sand"]),
    ("oak",     ["오크", "oak"]),
    ("blue",    ["블루", "blue", "네이비", "navy", "스카이"]),
    ("green",   ["그린", "green", "카키", "khaki", "올리브"]),
    ("pink",    ["핑크", "pink", "로즈", "rose", "살구"]),
    ("red",     ["레드", "red", "버건디", "burgundy", "와인"]),
    ("yellow",  ["옐로우", "yellow", "머스타드", "mustard"]),
    ("gold",    ["골드", "gold", "황동"]),
]

# ── 소재 키워드 ───────────────────────────────────────────────────
MATERIAL_MAP: list[tuple[str, list[str]]] = [
    ("solid_wood",  ["원목", "solid wood", "솔리드", "천연목", "참나무", "소나무", "고무나무"]),
    ("mdf",         ["mdf", "중밀도", "엠디에프"]),
    ("plywood",     ["합판", "plywood", "자작나무합판"]),
    ("metal",       ["철재", "철제", "메탈", "metal", "알루미늄", "aluminum"]),
    ("iron",        ["아이언", "iron", "주철"]),
    ("steel",       ["스틸", "steel", "스테인리스"]),
    ("fabric",      ["패브릭", "fabric", "천", "린넨", "linen", "면"]),
    ("velvet",      ["벨벳", "velvet"]),
    ("leather",     ["가죽", "leather", "leatherette", "인조가죽", "pu가죽"]),
    ("rattan",      ["라탄", "rattan", "등나무", "등"]),
    ("glass",       ["유리", "glass", "강화유리"]),
    ("plastic",     ["플라스틱", "plastic", "pp", "abs"]),
]

# ── 스타일 태그 키워드 ────────────────────────────────────────────
STYLE_MAP: list[tuple[str, list[str]]] = [
    ("minimal",      ["미니멀", "minimal", "심플", "simple", "슬림", "slim"]),
    ("modern",       ["모던", "modern", "현대", "contemporary"]),
    ("warm",         ["따뜻", "warm", "아늑", "cozy"]),
    ("white",        ["화이트", "white"]),
    ("scandinavian", ["북유럽", "스칸디", "scandinav", "nordic", "노르딕"]),
    ("light",        ["밝", "라이트", "light", "내추럴", "natural"]),
    ("dark",         ["다크", "dark", "블랙", "black"]),
    ("bohemian",     ["보헤미안", "bohemian", "라탄", "rattan", "빈티지", "vintage"]),
    ("work",         ["책상", "desk", "사무", "office", "work", "워크"]),
    ("sleep",        ["침대", "bed", "수면", "sleep"]),
    ("focus",        ["집중", "독서", "study", "홈오피스"]),
    ("storage",      ["수납", "storage", "서랍", "drawer", "선반", "shelf"]),
    ("relax",        ["소파", "sofa", "의자", "recliner", "리클라이너", "안락"]),
]

# 카테고리 → 기본 style_tag
CATEGORY_DEFAULT_TAGS: dict[str, list[str]] = {
    "bed":     ["sleep"],
    "desk":    ["work", "focus"],
    "chair":   ["work"],
    "storage": ["storage"],
    "sofa":    ["relax"],
    "table":   [],
}


def normalize(text: str) -> str:
    return text.lower()


def extract_colors(name: str) -> list[str]:
    n = normalize(name)
    found = []
    for color, keywords in COLOR_MAP:
        if any(kw.lower() in n for kw in keywords):
            found.append(color)
    return found[:4]


def extract_materials(name: str) -> list[str]:
    n = normalize(name)
    found = []
    for mat, keywords in MATERIAL_MAP:
        if any(kw.lower() in n for kw in keywords):
            found.append(mat)
    return found[:4]


def extract_style_tags(name: str, category: str) -> list[str]:
    n = normalize(name)
    found = set(CATEGORY_DEFAULT_TAGS.get(category, []))
    for tag, keywords in STYLE_MAP:
        if any(kw.lower() in n for kw in keywords):
            found.add(tag)
    return sorted(found)


def make_description(item: dict, colors: list[str], materials: list[str]) -> str:
    parts = []
    if materials:
        parts.append(materials[0].replace("_", " "))
    if colors:
        color_kr = {"white": "화이트", "black": "블랙", "gray": "그레이", "brown": "브라운",
                    "natural": "내추럴", "oak": "오크", "blue": "블루", "green": "그린",
                    "pink": "핑크", "red": "레드", "gold": "골드"}.get(colors[0], colors[0])
        parts.append(color_kr)
    cat_kr = {"bed": "침대", "desk": "책상", "chair": "의자", "storage": "수납", "sofa": "소파", "table": "테이블"}.get(item["category"], "가구")
    parts.append(cat_kr)
    return " ".join(parts)[:40]


def main() -> None:
    catalog: list[dict] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    updated = 0
    for item in catalog:
        name = item.get("name", "")
        category = item.get("category", "")

        colors = extract_colors(name)
        materials = extract_materials(name)
        style_tags = extract_style_tags(name, category)

        # 기존 style_tags 병합
        existing_tags = set(item.get("style_tags", []))
        merged_tags = sorted(existing_tags | set(style_tags))

        item["colors"] = colors
        item["materials"] = materials
        item["style_tags"] = merged_tags
        item["description"] = make_description(item, colors, materials)
        item["enriched"] = True
        updated += 1

    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")

    # 통계
    has_colors = sum(1 for i in catalog if i.get("colors"))
    has_materials = sum(1 for i in catalog if i.get("materials"))
    print(f"완료: {updated}개 처리")
    print(f"  colors 있음:    {has_colors}/{updated}")
    print(f"  materials 있음: {has_materials}/{updated}")

    # 샘플 5개
    print("\n샘플:")
    for item in catalog[:5]:
        print(f"  [{item['category']}] {item['name'][:40]}")
        print(f"    colors={item['colors']}  materials={item['materials']}")
        print(f"    style_tags={item['style_tags']}")
        print(f"    desc={item['description']}")


if __name__ == "__main__":
    main()
