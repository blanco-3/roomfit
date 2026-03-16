#!/usr/bin/env python3
"""Naver Shopping API로 실제 가구 데이터를 가져와 furniture_catalog.json에 저장.

사전 준비:
    1. https://developers.naver.com/apps/ 접속
    2. 애플리케이션 등록 → Shopping 검색 API 활성화
    3. Client ID / Client Secret 복사

실행:
    export NAVER_CLIENT_ID=your_id
    export NAVER_CLIENT_SECRET=your_secret
    python scripts/fetch_naver_catalog.py

    또는 .env에 추가 후:
    export $(grep -v '^#' .env | xargs)
    python scripts/fetch_naver_catalog.py
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CATALOG_PATH = Path(__file__).parent.parent / "data" / "furniture_catalog.json"

# 카테고리별 검색어 (각 검색어당 최대 100개 → 중복 제거)
CATEGORY_QUERIES: dict[str, list[str]] = {
    "bed": ["이케아 침대 프레임", "원목 침대 프레임", "북유럽 침대 프레임", "싱글 침대 프레임", "퀸 침대 프레임"],
    "desk": ["이케아 책상", "원목 책상 화이트", "학생 책상 수납", "컴퓨터 책상 모던", "사무용 책상 원목"],
    "chair": ["이케아 의자", "원목 식탁의자", "사무용 의자 메쉬", "카페 의자 북유럽", "패브릭 의자 미니멀"],
    "storage": ["이케아 수납장", "원목 수납함 선반", "책장 수납 화이트", "옷장 수납장 미니멀", "큐브 수납함"],
    "sofa": ["이케아 소파", "패브릭 2인 소파", "미니멀 소파 화이트", "원룸 소파 소형", "북유럽 소파"],
    "table": ["이케아 식탁", "원목 테이블 4인", "거실 테이블 미니멀", "커피 테이블 원목", "북유럽 식탁"],
}

# 키워드 → style_tags 매핑 (recommender의 mood/purpose 토큰과 일치해야 함)
# mood tokens: minimal, warm, white, scandinavian, light, modern, dark, bohemian
# purpose tokens: work, sleep, focus, storage, relax
STYLE_MAP: list[tuple[list[str], list[str]]] = [
    (["원목", "우드", "wood", "나무"], ["warm", "scandinavian"]),
    (["화이트", "white", "흰색", "밝은", "연한"], ["white", "minimal"]),
    (["블랙", "black", "검정", "다크", "블랙프레임"], ["dark", "modern"]),
    (["북유럽", "스칸디나비아", "nordic", "네이처", "내추럴"], ["scandinavian", "light"]),
    (["미니멀", "심플", "슬림", "simple"], ["minimal"]),
    (["모던", "modern", "인더스트리얼", "메탈"], ["modern"]),
    (["패브릭", "벨벳", "쿠션", "부드러운", "따뜻"], ["warm", "bohemian"]),
    (["보헤미안", "빈티지", "레트로", "라탄", "위커"], ["bohemian"]),
    (["수납", "서랍", "정리", "멀티", "다용도"], ["storage"]),
    (["책상", "스터디", "study", "사무", "워크"], ["work", "focus"]),
    (["침대", "bed", "매트리스", "수면"], ["sleep"]),
    (["소파", "릴렉스", "휴식", "라운지"], ["relax"]),
]

# 카테고리별 치수 기본값 (cm)
DIMENSION_DEFAULTS: dict[str, dict[str, int]] = {
    "bed": {"width_cm": 100, "depth_cm": 200, "height_cm": 85},
    "desk": {"width_cm": 120, "depth_cm": 60, "height_cm": 75},
    "chair": {"width_cm": 55, "depth_cm": 55, "height_cm": 90},
    "storage": {"width_cm": 80, "depth_cm": 40, "height_cm": 180},
    "sofa": {"width_cm": 180, "depth_cm": 85, "height_cm": 80},
    "table": {"width_cm": 120, "depth_cm": 60, "height_cm": 75},
}

# 쇼핑몰명 → source 매핑
MALL_SOURCE_MAP: list[tuple[list[str], str]] = [
    (["이케아", "ikea"], "ikea_kr"),
    (["한샘", "hanssem"], "hanssem"),
    (["일룸", "iloom"], "iloom"),
    (["리바트", "livart"], "livart"),
    (["까사미아", "casamia"], "casamia"),
    (["에이스침대", "ace"], "ace_bed"),
    (["오늘의집", "ohou"], "ohou"),
]


def clean_html(text: str) -> str:
    """HTML 태그 및 중복 공백 제거."""
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def infer_style_tags(title: str, category: str) -> list[str]:
    """제품명에서 style_tags 추론."""
    title_lower = title.lower()
    tags: set[str] = set()
    for keywords, tag_list in STYLE_MAP:
        if any(kw in title_lower for kw in keywords):
            tags.update(tag_list)
    # 카테고리 기반 기본 태그
    if not tags:
        default_tags = {
            "bed": ["minimal", "sleep"],
            "desk": ["minimal", "work"],
            "chair": ["minimal"],
            "storage": ["minimal", "storage"],
            "sofa": ["minimal", "relax"],
            "table": ["minimal"],
        }
        tags.update(default_tags.get(category, ["minimal"]))
    return sorted(tags)


def extract_dimensions(title: str, category: str) -> dict[str, int]:
    """제품명에서 치수 추출 (예: '120x60cm', 'W120 D60 H75')."""
    defaults = DIMENSION_DEFAULTS[category].copy()

    # WxDxH 세 값
    m = re.search(r"(\d{2,3})\s*[xX×]\s*(\d{2,3})\s*[xX×]\s*(\d{2,3})", title)
    if m:
        w, d, h = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 30 <= w <= 600 and 20 <= d <= 400 and 20 <= h <= 320:
            defaults.update({"width_cm": w, "depth_cm": d, "height_cm": h})
            return defaults

    # W/D/H 레이블 포함
    m = re.search(r"[Ww](\d{2,3})[^\d]*[Dd](\d{2,3})[^\d]*[Hh](\d{2,3})", title)
    if m:
        defaults.update({"width_cm": int(m.group(1)), "depth_cm": int(m.group(2)), "height_cm": int(m.group(3))})
        return defaults

    # WxH 두 값 (침대: WxL)
    m = re.search(r"(\d{2,3})\s*[xX×]\s*(\d{2,3})", title)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if category == "bed" and 80 <= a <= 200 and 150 <= b <= 230:
            defaults.update({"width_cm": a, "depth_cm": b})
        elif 50 <= a <= 300:
            defaults["width_cm"] = a

    return defaults


def infer_source(title: str, mall_name: str) -> str:
    """쇼핑몰명/제품명에서 source 추론."""
    combined = (title + " " + mall_name).lower()
    for keywords, source in MALL_SOURCE_MAP:
        if any(kw in combined for kw in keywords):
            return source
    return "naver_shopping"


def fetch_naver(query: str, client_id: str, client_secret: str, display: int = 100) -> list[dict]:
    """Naver Shopping API 호출."""
    params = urlencode({"query": query, "display": display, "sort": "sim"})
    url = f"https://openapi.naver.com/v1/search/shop.json?{params}"
    req = Request(url, headers={
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "User-Agent": "RoomfitCatalogFetcher/1.0",
    })
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("items", [])


def main() -> None:
    client_id = os.getenv("NAVER_CLIENT_ID", "").strip()
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        print("ERROR: Naver API 키가 없습니다.")
        print("  1. https://developers.naver.com/apps/ 에서 앱 등록 (Shopping API)")
        print("  2. .env에 추가:")
        print("     NAVER_CLIENT_ID=your_id")
        print("     NAVER_CLIENT_SECRET=your_secret")
        print("  3. export $(grep -v '^#' .env | xargs) && python scripts/fetch_naver_catalog.py")
        return

    catalog: list[dict] = []
    sku_counter = 1
    seen_urls: set[str] = set()

    for category, queries in CATEGORY_QUERIES.items():
        print(f"\n[{category}] 검색 중...")
        raw_items: list[dict] = []

        for query in queries:
            print(f"  '{query}' ...", end=" ", flush=True)
            try:
                items = fetch_naver(query, client_id, client_secret, display=100)
                raw_items.extend(items)
                print(f"{len(items)}개")
            except URLError as e:
                print(f"실패: {e}")
            except Exception as e:
                print(f"오류: {e}")
            time.sleep(0.35)  # API 레이트 리밋 준수

        # URL 기준 중복 제거
        unique: list[dict] = []
        for item in raw_items:
            link = item.get("link", "")
            if link and link not in seen_urls:
                seen_urls.add(link)
                unique.append(item)

        # 정규화
        added = 0
        for item in unique:
            title = clean_html(item.get("title", ""))
            if not title or len(title) < 4:
                continue

            try:
                price = int(item.get("lprice", 0))
            except (ValueError, TypeError):
                continue

            # 비현실적인 가격 필터링
            if price < 10000 or price > 10_000_000:
                continue

            dims = extract_dimensions(title, category)
            tags = infer_style_tags(title, category)
            mall = item.get("mallName", "")
            source = infer_source(title, mall)

            catalog.append({
                "id": f"sku_{sku_counter:04d}",
                "source": source,
                "name": title[:80],
                "category": category,
                "width_cm": dims["width_cm"],
                "depth_cm": dims["depth_cm"],
                "height_cm": dims["height_cm"],
                "price_krw": price,
                "style_tags": tags,
                "url": item.get("link", ""),
                "image_url": item.get("image", ""),
            })
            sku_counter += 1
            added += 1

        print(f"  → {added}개 추가 (총 {sku_counter - 1}개)")

    # 저장
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료: {len(catalog)}개 제품 저장 → {CATALOG_PATH}")

    # 카테고리별 통계
    from collections import Counter
    counts = Counter(item["category"] for item in catalog)
    for cat, cnt in sorted(counts.items()):
        print(f"  {cat}: {cnt}개")


if __name__ == "__main__":
    main()
