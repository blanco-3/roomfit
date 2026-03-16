# AI Room Styler (Roomfit)

방 치수 + 다중 사진 + 무드/용도 기반으로 실제 배치 가능한 가구 SKU를 추천하는 서비스 스캐폴드입니다.

## 현재 구현
- 이메일/비밀번호 로그인 (`/v1/auth/register`, `/v1/auth/login`)
- 사용자별 room profile 저장
- 다중 사진 업로드 (`/v1/room/photos`, 2~12장)
- **AI 실측 추정 API** (`POST /v1/room/auto-estimate`): 업로드 사진 + 기준 물체 선택으로 방 치수/신뢰도 추정
- 촬영 기준 가이드 API (`/v1/scan-guidelines`)
- 추천 엔진 + 결과 저장 (수동 치수/AI 치수 모두 지원, 하위호환)
- 648 SKU 카탈로그
- **모바일 퍼스트 5단계 위저드 UI + PWA**
  - 1) 계정, 2) 방 기본, 3) 사진+기준물체, 4) AI 추정 리뷰/수정, 5) 추천 결과+근거/히스토리
- **DB 백엔드 추상화 스캐폴드** (`DATABASE_URL` 기반, SQLite 기본 / Postgres 전환 경로 준비)
- **운영 로그 테이블 + API** (`/v1/ops/logs`) 및 간단 대시보드 (`/ops`)
- **추천 실행 히스토리 API** (`/v1/recommendations/history`) + 메인 UI 히스토리 패널
- **CV 작업 스캐폴드 + 모의 실측 추정** (`POST /v1/cv/jobs`, `GET /v1/cv/jobs/{job_id}`)

## 실행
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

- 앱: http://localhost:8080/
- API 문서: http://localhost:8080/docs

## 테스트용 계정
웹에서 바로 가입/로그인 가능. (개발자 계정으로 생성)

## 주요 파일
- `app/main.py` API 엔트리
- `app/db.py` SQLite + 인증 + 업로드 저장
- `app/recommender.py` 추천 로직
- `app/static/index.html` 웹/PWA UI
- `docs/PHOTO_CAPTURE_GUIDE.md` 다중 사진 촬영 기준
- `docs/POSTGRES_MIGRATION.md` Postgres 전환 경로
- `scripts/generate_catalog.py` SKU 생성 파이프라인
- `scripts/export_sqlite_to_json.py` SQLite 데이터 export 스크립트

## 다음 단계
1. 이미지 분석(CV) 워커 붙여 실측 추정 자동화
2. Postgres 전환 + 운영 로그 대시보드
3. 실쇼핑몰 커넥터 + 증분 동기화
4. React Native 앱 래퍼(동일 API 사용)
