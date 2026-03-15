# AI Room Styler Demo (MVP)

사진 기반으로 방 치수를 추정하고, 가구 카탈로그를 기반으로 배치 가능한 추천을 반환하는 데모입니다.

## 포함된 것
- PRD v0.1 (`docs/PRD.md`)
- DB 스키마 + API 명세 (`docs/TECH_SPEC.md`)
- 4주 스프린트 계획 (`docs/SPRINT_PLAN.md`)
- FastAPI 백엔드 데모 (`app/main.py`)
- 샘플 카탈로그 (`data/furniture_catalog.json`)

## 실행
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

브라우저:
- 앱: http://localhost:8080/
- API 문서: http://localhost:8080/docs

## 데모 흐름
1. `/`에서 방 정보(폭/길이/예산/무드/용도) 입력
2. `POST /v1/room/estimate`로 room profile 생성
3. `POST /v1/recommendations`로 가구 추천 반환

## 주의
- 현재는 **MVP 데모**로, 실측 추정은 단순 휴리스틱/입력 기반입니다.
- 향후 depth estimation, segmentation, 제휴 API 연동으로 고도화합니다.
