# DB 스키마 + API 명세 (MVP)

## 1) 데이터 모델 (PostgreSQL 기준)

### users
- id (uuid, pk)
- created_at (timestamptz)

### room_profiles
- id (uuid, pk)
- user_id (uuid, fk users.id)
- width_cm (int)
- length_cm (int)
- height_cm (int)
- mood (text)
- purpose (text)
- budget_krw (int)
- created_at (timestamptz)

### furniture_items
- id (uuid, pk)
- source (text) — ikea, coupang, etc
- external_id (text)
- name (text)
- category (text) — bed, desk, chair, storage...
- width_cm (int)
- depth_cm (int)
- height_cm (int)
- price_krw (int)
- style_tags (text[])
- url (text)
- image_url (text)
- created_at (timestamptz)

### recommendation_runs
- id (uuid, pk)
- room_profile_id (uuid, fk)
- score_json (jsonb)
- created_at (timestamptz)

### recommendation_items
- id (uuid, pk)
- run_id (uuid, fk recommendation_runs.id)
- furniture_item_id (uuid, fk furniture_items.id)
- score (numeric)
- reason (text)

## 2) API

### POST /v1/room/estimate
요청:
```json
{
  "width_cm": 280,
  "length_cm": 340,
  "height_cm": 240,
  "mood": "minimal_warm",
  "purpose": "work_sleep",
  "budget_krw": 1200000
}
```
응답:
```json
{
  "room_profile": {
    "room_id": "...",
    "area_m2": 9.52,
    "recommended_walkway_cm": 60
  }
}
```

### POST /v1/recommendations
요청:
```json
{
  "room_id": "...",
  "required_categories": ["bed", "desk", "chair", "storage"]
}
```
응답:
```json
{
  "summary": {
    "total_price_krw": 1090000,
    "fit_score": 0.86,
    "style_score": 0.78
  },
  "items": [
    {
      "name": "...",
      "category": "desk",
      "price_krw": 199000,
      "reason": "예산/치수/무드 적합"
    }
  ]
}
```

### GET /v1/catalog
카탈로그 목록 조회 (필터: category, max_price)

## 3) 추천 엔진 로직 (MVP)
1. category별 후보 필터
2. room size 대비 가구 footprint 합산 검증
3. 통로(60cm) 확보 여부 체크
4. mood/purpose 태그 일치도로 랭킹
5. 설명문 생성
