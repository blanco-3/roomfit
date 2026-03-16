# Roomfit – Claude Code Instructions

## Project Overview
AI interior design copilot. Users chat with an AI that asks about their room, then recommends real furniture products.

**Stack:** FastAPI + SQLite (Python 3.9) · Groq/Gemini/OpenAI LLM chain · Vanilla JS PWA

## Running Locally
```bash
cd /Users/blanco/roomfit
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload
# → http://127.0.0.1:8000
```

## Key Files
| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI routes |
| `app/chat_engine.py` | LLM chat logic (Groq → Gemini → OpenAI → mock) |
| `app/recommender.py` | Furniture scoring & selection |
| `app/db.py` | SQLite helpers |
| `app/schemas.py` | Pydantic models |
| `app/cv_worker.py` | Room dimension estimation from photos |
| `data/furniture_catalog.json` | Product catalog (648 dummy SKUs — needs real data) |
| `app/static/index.html` | Chat UI (PWA) |

## API Keys (.env)
```
GROQ_API_KEY=...      # primary — free, qwen/qwen3-32b
GOOGLE_API_KEY=...    # fallback — Gemini (quota=0 in Korea)
OPENAI_API_KEY=...    # fallback — GPT-4o (paid)
DEV_MODE=true         # skip auth in development
```

## LLM Provider Chain
Priority: GROQ → GOOGLE → OPENAI → mock

Current model: `qwen/qwen3-32b` (best Korean quality on Groq free tier)

**Known quirks:**
- Qwen3 outputs `<think>...</think>` blocks → stripped in `_strip_extracted_tag`
- System prompt is in English for cross-model consistency; language rule forces reply in user's language
- Parameter extraction via `<extracted>{...}</extracted>` at end of reply

## Python Version
**Must use Python 3.9.6** (`/usr/bin/python3`). The `.venv` is built on 3.9.
- Use `Optional[str]` NOT `str | None`
- Use `from __future__ import annotations` at top of files

---

## Active Development Tracks

### Track 1 — Real SKU Data

**Goal:** Replace 648 dummy SKUs in `data/furniture_catalog.json` with real purchasable products.

**Catalog schema per item:**
```json
{
  "id": "sku_XXXX",
  "source": "ikea_kr | naver | ohou | coupang",
  "name": "제품명",
  "category": "bed | desk | chair | storage | sofa | table",
  "width_cm": 120,
  "depth_cm": 60,
  "height_cm": 75,
  "price_krw": 149000,
  "style_tags": ["minimal", "warm", "wood", "scandinavian", "dark", "white"],
  "url": "https://실제구매링크",
  "image_url": "https://이미지URL"
}
```

**Valid style_tags** (must match mood/purpose tokens in recommender):
- mood: `minimal`, `warm`, `white`, `scandinavian`, `light`, `modern`, `dark`, `bohemian`
- purpose: `work`, `sleep`, `focus`, `storage`, `relax`

**Data sources (priority order):**

1. **Naver Shopping API** (recommended — free, structured, Korean market)
   - Endpoint: `https://openapi.naver.com/v1/search/shop.json`
   - Headers: `X-Naver-Client-Id`, `X-Naver-Client-Secret`
   - Query per category: `"이케아 침대"`, `"이케아 책상"`, etc.
   - Returns: title, lprice, mallName, link, image
   - Env vars needed: `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`

2. **Manual curation** — copy from IKEA Korea / Ohou / Coupang product pages

**Script to write:** `scripts/fetch_naver_catalog.py`
- Fetch 50-100 items per category (6 categories)
- Normalize to catalog schema
- Infer style_tags from product name keywords
- Output to `data/furniture_catalog.json`

**Keyword → style_tag mapping for inference:**
```python
STYLE_MAP = {
    "원목": ["wood", "warm", "scandinavian"],
    "화이트": ["white", "minimal"],
    "블랙": ["dark", "modern"],
    "무드": ["warm", "bohemian"],
    "북유럽": ["scandinavian", "light"],
    "미니멀": ["minimal", "white"],
    "수납": ["storage"],
}
```

---

### Track 2 — Copilot Quality

**Current issues:**
- Qwen3 sometimes outputs `<think>` tags visibly (fix applied, verify in testing)
- Model occasionally asks multiple questions in one turn
- `<extracted>` block sometimes emitted too early (before all 3 fields confirmed)

**System prompt location:** `app/chat_engine.py` → `SYSTEM_PROMPT` constant

**Improvement areas:**

1. **Extraction reliability** — Add few-shot examples to system prompt showing when to emit `<extracted>`
2. **Question discipline** — Reinforce ONE question per turn with negative example in prompt
3. **Recommendation display** — `index.html` should render product cards with image, name, price, buy link
4. **Session continuity** — After recommendation, copilot should ask "마음에 드시나요? 다른 스타일도 보여드릴까요?"

**Chat endpoint:** `POST /v1/chat` (Form: `message`, `session_id?`, `files?`)

**Response shape:**
```json
{
  "session_id": "...",
  "reply": "AI 응답 텍스트",
  "extracted": {"mood": "...", "purpose": "...", "budget_krw": 0, ...} | null,
  "recommendation": { "summary": {...}, "items": [...] } | null
}
```

**Recommendation trigger:** `trigger_recommend = extracted is not None AND has mood+purpose+budget_krw`

---

## Recommender Logic (`app/recommender.py`)
- Scores each catalog item: `0.75 * style_match + 0.25 * size_fit`
- Budget filter: only items where `price_krw <= room.budget_krw`
- Walkway check: total footprint ≤ 55% of room area
- Returns best item per category + 2 alternatives

---

## Testing
```bash
cd /Users/blanco/roomfit
source .venv/bin/activate
pytest tests/ -v
```

Test file: `tests/test_api.py`

---

## Common Gotchas
- `extracted.get("width_cm") or 280` — use `or` not `.get("width_cm", 280)` because key may exist with `null` value
- After changing `.env`, re-export: `export $(grep -v '^#' .env | xargs)`
- Groq free tier: no rate limit issues for dev, but don't run load tests
- IKEA direct scraping: infeasible (Cloudflare + JS-rendered)
