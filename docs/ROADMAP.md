# ROADMAP - Roomfit Architecture & Product Plan

## 목표
- **단기:** 지금 바로 쓸 수 있는 신뢰 가능한 방 추천 UX (빠름/안정성/설명 가능성)
- **중기:** CV+LLM 기반 반자동 인테리어 코파일럿
- **장기:** 쇼핑 연동 + 시뮬레이션 + 개인화로 전환율/재방문 최적화

---

## Phase 0 (Now, no/low-cost 우선)

### 아키텍처
- FastAPI 모놀리식 API
- SQLite + 추상화된 DB 계층 (`DATABASE_URL`), Postgres 전환 준비
- 규칙 기반 추천 엔진 + 카탈로그 JSON
- Ops logs + 기본 대시보드
- PWA 웹 프론트

### 현재 AI 전략
- 외부 유료 모델 없이 규칙/휴리스틱 + mock inference
- 이미지 실측은 placeholder 워커 스캐폴드로 분리 준비

### 품질 포커스
- 로그인/세션 안정화
- 오류 상태 명확화
- 추천 히스토리 및 운영 가시성

---

## Phase 1 (MVP AI integration)

### 핵심 추가
- 비동기 Job Queue (Redis/RQ or Celery)
- CV worker: 방 윤곽/기준 물체 기반 치수 추정
- LLM: 추천 이유 문장 고도화 + 스타일 설명
- 임베딩: 카탈로그 검색/유사도 확장

### 제안 기본 스택
- LLM: OpenAI GPT-4.1-mini 또는 동급 저비용 모델 (reasoning light)
- Vision: GPT-4.1-mini vision + open-source 보조 (YOLO/Depth Anything)
- Embedding: text-embedding-3-small 또는 bge-small(오픈소스)
- Rerank: cross-encoder/ms-marco 계열(오픈소스) 또는 API rerank

### 안전/품질
- prompt/version 관리
- 평가셋 기반 회귀 테스트 (추천 품질 scorecard)
- fallback 체인: API 실패 시 규칙 기반 추천으로 자동 다운그레이드

---

## Phase 2 (Growth)

### 제품
- 스타일 보드 생성, 방 타입 템플릿, 예산 시나리오 비교
- 쇼핑몰 커넥터(가격/재고 동기화)
- 사용자 선호 학습 (클릭/저장/구매 신호)

### 플랫폼
- Postgres 전환 + Alembic migration
- 캐시/큐/worker autoscaling
- 관측성: metrics, traces, alerting

---

## Phase 3 (Scale)

### 고도화
- 멀티모달 planner (텍스트+이미지+공간 제약 통합)
- 실시간 레이아웃 탐색/시뮬레이션
- 멀티테넌트 B2B API

### 운영
- 비용-aware routing (요청 난이도별 모델 선택)
- SLA 기반 latency budget 관리
- 데이터 flywheel (품질 평가 → 재학습/튜닝)

---

## 기술 원칙
1. **항상 fallback 제공** (유료 AI 실패해도 핵심 UX 유지)
2. **모델 교체 가능하게** (provider lock-in 최소화)
3. **관측 가능한 AI** (비용/지연/품질 트래킹)
4. **점진적 도입** (작게 붙이고, 측정 후 확장)

---

## 당장 다음 구현 우선순위
1. 비동기 job 모델 + mocked CV estimation API
2. 추천 결과 설명 품질 개선(템플릿 + 규칙 확장)
3. 히스토리 상세 조회/재실행 UX
4. Postgres migration script 초안 + 환경별 실행 가이드
