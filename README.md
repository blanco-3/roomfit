# AI Room Styler (Pre-Launch Scaffold)

방 정보(추후 사진 인식 포함)를 기반으로 실제 배치 가능한 가구 조합을 추천하는 서비스의 출시 직전 스캐폴드입니다.

## 포함된 것
- PRD v0.1 (`docs/PRD.md`)
- DB 스키마 + API 명세 (`docs/TECH_SPEC.md`)
- 4주 스프린트 계획 (`docs/SPRINT_PLAN.md`)
- FastAPI API 서버 (`app/main.py`)
- SQLite 영속 저장 (`app/db.py`, `data/roomstyler.db`)
- 추천 엔진 모듈 (`app/recommender.py`)
- 샘플 카탈로그 (`data/furniture_catalog.json`)
- 기본 웹 데모 (`app/static/index.html`)
- API 테스트 (`tests/test_api.py`)
- Docker 실행 파일 (`Dockerfile`, `docker-compose.yml`)

## 로컬 실행
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

- 앱: http://localhost:8080/
- API 문서: http://localhost:8080/docs

## 테스트
```bash
pytest -q
```

## Docker 실행
```bash
docker compose up --build
```

## API 흐름
1. `POST /v1/room/estimate` → room_id 생성/저장
2. `POST /v1/recommendations` → 추천 결과 + run_id 저장
3. `GET /v1/catalog` → 카테고리/가격 필터 조회

## 다음 개발 우선순위
1. Postgres 전환 + Alembic 마이그레이션
2. 이미지 업로드 + depth/segmentation 연동
3. 추천 explainability 강화 및 A/B 실험 로깅
4. 외부 쇼핑몰 카탈로그 수집 파이프라인 자동화
