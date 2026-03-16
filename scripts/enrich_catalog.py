#!/usr/bin/env python3
"""
상품 상세 페이지를 크롤링하고 Gemini Vision으로 색상/소재/스타일 정보를 추출.
결과를 furniture_catalog.json에 enriched 필드로 저장.

실행:
    export $(grep -v '^#' .env | xargs)
    python scripts/enrich_catalog.py              # 전체 (unenriched 항목만)
    python scripts/enrich_catalog.py --limit 100  # 처음 100개만
    python scripts/enrich_catalog.py --category bed --limit 50
    python scripts/enrich_catalog.py --redo       # 이미 처리된 것도 재처리

Gemini free tier: 15 RPM, 1500 RPD → 약 1500개/일 처리 가능
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

CATALOG_PATH = Path(__file__).parent.parent / "data" / "furniture_catalog.json"
SAVE_INTERVAL = 30  # N개마다 중간 저장
REQUEST_DELAY = 4.5  # Gemini 15 RPM 안전 간격 (초)

# Gemini가 사용할 유효 style_tags (recommender 토큰과 일치)
VALID_STYLE_TAGS = {
    "minimal", "warm", "white", "scandinavian", "light",
    "modern", "dark", "bohemian", "work", "sleep", "focus", "storage", "relax",
}

ENRICH_PROMPT = """Analyze this furniture product and return ONLY a JSON object.

Product name: {name}
Category: {category}
Page description: {page_desc}

Return this exact JSON structure:
{{
  "colors": ["color1", "color2"],
  "materials": ["material1", "material2"],
  "style_tags": ["tag1", "tag2"],
  "short_description": "one sentence in Korean"
}}

Rules:
- colors: use simple English words like white, black, gray, brown, natural, beige, blue, green, pink, red, gold, silver, walnut, oak
- materials: solid_wood, mdf, plywood, metal, iron, steel, fabric, leather, velvet, rattan, glass, plastic
- style_tags: ONLY from this list: minimal warm white scandinavian light modern dark bohemian work sleep focus storage relax
- short_description: 20자 이내 한국어로 핵심 특징 요약
"""


class MetaExtractor(HTMLParser):
    """HTML 페이지에서 og:description, description, title 추출."""

    def __init__(self):
        super().__init__()
        self.og_description = ""
        self.description = ""
        self.og_title = ""
        self._in_title = False
        self._title_buf = ""

    def handle_starttag(self, tag: str, attrs):
        d = dict(attrs)
        if tag == "meta":
            prop = d.get("property", "")
            name = d.get("name", "")
            content = d.get("content", "")[:600]
            if prop == "og:description":
                self.og_description = content
            elif prop == "og:title":
                self.og_title = content
            elif name == "description":
                self.description = content
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data: str):
        if self._in_title:
            self._title_buf += data

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False

    def best_description(self) -> str:
        return self.og_description or self.description or ""

    def best_title(self) -> str:
        return self.og_title or self._title_buf.strip()


def fetch_page_text(url: str) -> str:
    """URL에서 og:description 등 텍스트를 뽑는다. 실패시 빈 문자열."""
    try:
        req = Request(url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        })
        with urlopen(req, timeout=8) as resp:
            raw = resp.read(60_000)  # 60KB만 읽음
        html = raw.decode("utf-8", errors="ignore")
        p = MetaExtractor()
        p.feed(html)
        return p.best_description()
    except Exception:
        return ""


def download_image(url: str) -> bytes:
    """이미지 바이너리 다운로드. 실패시 빈 bytes."""
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=8) as resp:
            data = resp.read(2_000_000)  # 최대 2MB
        return data if len(data) > 200 else b""
    except Exception:
        return b""


def call_gemini(item: dict, page_desc: str, api_key: str) -> dict | None:
    """Gemini Vision으로 색상/소재/스타일 분석. 성공시 dict, 실패시 None."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

    prompt = ENRICH_PROMPT.format(
        name=item["name"],
        category=item["category"],
        page_desc=page_desc[:400] if page_desc else "(없음)",
    )
    parts: list = [types.Part(text=prompt)]

    # 이미지 첨부
    img_bytes = download_image(item.get("image_url", ""))
    if img_bytes:
        parts.append(types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=img_bytes)))

    try:
        resp = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        raw = json.loads(resp.text or "{}")
        return raw
    except Exception as e:
        print(f"    Gemini 오류: {e}")
        return None


def apply_enrichment(item: dict, enriched: dict) -> None:
    """enriched 결과를 item에 적용. item을 in-place 수정."""
    item["colors"] = [str(c).strip().lower() for c in enriched.get("colors", []) if c][:6]
    item["materials"] = [str(m).strip().lower() for m in enriched.get("materials", []) if m][:6]
    item["description"] = str(enriched.get("short_description", ""))[:100]

    # style_tags: 기존 + Gemini 추출, VALID_STYLE_TAGS 필터
    existing = set(item.get("style_tags", []))
    new_tags = {t for t in enriched.get("style_tags", []) if t in VALID_STYLE_TAGS}
    item["style_tags"] = sorted(existing | new_tags)
    item["enriched"] = True


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich furniture catalog with Gemini Vision")
    parser.add_argument("--limit", type=int, default=0, help="처리할 최대 항목 수 (0=전체)")
    parser.add_argument("--category", default="", help="특정 카테고리만 (bed/desk/chair/storage/sofa/table)")
    parser.add_argument("--redo", action="store_true", help="이미 처리된 항목도 재처리")
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not api_key:
        print("ERROR: GOOGLE_API_KEY가 없습니다. .env를 확인하세요.")
        return

    catalog: list[dict] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    id_map = {item["id"]: idx for idx, item in enumerate(catalog)}

    # 처리 대상 필터링
    targets = catalog
    if not args.redo:
        targets = [i for i in targets if not i.get("enriched")]
    if args.category:
        targets = [i for i in targets if i["category"] == args.category]
    if args.limit:
        targets = targets[: args.limit]

    total = len(targets)
    print(f"처리 대상: {total}개 (전체 카탈로그: {len(catalog)}개)")
    print(f"예상 소요: {total * REQUEST_DELAY / 60:.1f}분\n")

    success = 0
    for i, item in enumerate(targets, 1):
        prefix = f"[{i}/{total}] {item['id']} [{item['category']}] {item['name'][:35]}"
        print(prefix, end=" ", flush=True)

        # 1. 상세 페이지 크롤링
        page_desc = fetch_page_text(item.get("url", "")) if item.get("url") else ""

        # 2. Gemini 분석
        result = call_gemini(item, page_desc, api_key)

        if result:
            idx = id_map[item["id"]]
            apply_enrichment(catalog[idx], result)
            colors_str = ",".join(catalog[idx].get("colors", []))
            mats_str = ",".join(catalog[idx].get("materials", []))
            print(f"✓  colors=[{colors_str}]  mat=[{mats_str}]")
            success += 1
        else:
            catalog[id_map[item["id"]]]["enriched"] = False
            print("✗")

        # 중간 저장
        if i % SAVE_INTERVAL == 0:
            CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  💾 중간 저장 ({i}개 처리, 성공 {success}개)\n")

        time.sleep(REQUEST_DELAY)

    # 최종 저장
    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    enriched_total = sum(1 for i in catalog if i.get("enriched") is True)
    print(f"\n완료: {success}/{total}개 성공")
    print(f"전체 enriched: {enriched_total}/{len(catalog)}개")

    # 샘플 출력
    sample = next((i for i in catalog if i.get("colors")), None)
    if sample:
        print(f"\n샘플: {sample['name'][:40]}")
        print(f"  colors: {sample['colors']}")
        print(f"  materials: {sample['materials']}")
        print(f"  style_tags: {sample['style_tags']}")
        print(f"  description: {sample['description']}")


if __name__ == "__main__":
    main()
