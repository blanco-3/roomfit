# COST & MODEL RESEARCH - Roomfit

> 기준: 2026년 Q1 대략치(공식 단가 변동 가능). 정확 견적은 실제 사용량으로 재산정 필요.

## 1) 어디에 유료 서비스가 "진짜" 필요한가?

### 거의 필수(품질/속도 위해)
- **멀티모달 LLM/Vision API**: 사진 기반 공간 해석 정확도/설명 품질
- **고성능 임베딩/검색 인프라** (트래픽 증가 시)

### 조건부 필요
- **Rerank API**: 카탈로그가 커지고 결과 품질이 떨어질 때
- **전용 벡터DB SaaS**: 운영 단순화가 필요할 때

### 당장은 불필요/대체 가능
- 초기 운영에서 고가 reasoning 모델 상시 사용
- 전 구간 managed SaaS 의존 (오픈소스/셀프호스팅으로 대체 가능)

---

## 2) 단계별 월 비용 밴드 (rough order-of-magnitude)

가정(예시):
- MVP: DAU 200, 추천 1,500회/월, 평균 사진 4장
- Growth: DAU 3,000, 추천 40,000회/월
- Scale: DAU 30,000+, 추천 500,000회/월

### MVP (초기)
- LLM+Vision API: **$50 ~ $400 /mo**
- 인프라(서버/DB/스토리지): **$30 ~ $200 /mo**
- 모니터링/기타: **$0 ~ $50 /mo**
- **합계: $80 ~ $650 /mo**

### Growth
- LLM+Vision API: **$1.5k ~ $8k /mo**
- 인프라/DB/큐/캐시: **$400 ~ $2k /mo**
- 검색/벡터/rerank: **$200 ~ $1.5k /mo**
- **합계: $2.1k ~ $11.5k /mo**

### Scale
- LLM+Vision API: **$20k ~ $120k+ /mo**
- 인프라: **$5k ~ $30k /mo**
- 데이터/관측성/ops: **$3k ~ $20k /mo**
- **합계: $28k ~ $170k+ /mo**

---

## 3) 추천 모델 스택 (기본안)

## A. Default (품질+속도 균형)
- **LLM 생성/설명:** GPT-4.1-mini 급
- **Vision 추론:** GPT-4.1-mini vision + open-source detector 보강
- **Embedding:** text-embedding-3-small 급
- **Rerank:** 오픈소스 cross-encoder (CPU/GPU 여건 따라)

장점: 구현 단순, 품질 안정, 빠른 출시
단점: API 비용 누적

## B. Cost saver (저비용)
- LLM: 저가 모델 (요약/템플릿 중심)
- Vision: 오픈소스 파이프라인 중심 (YOLO + depth/seg)
- Embedding/Rerank: 전부 오픈소스

장점: 비용 절감
단점: 품질 튜닝/운영 난이도 상승

## C. Premium (경쟁 우위)
- 상위 멀티모달 모델 + 강한 rerank + personalization

장점: 상위 UX/설명력
단점: 높은 비용, SLO 관리 복잡

---

## 4) 품질/지연/비용 트레이드오프

- **품질↑**: 더 큰 모델, 더 많은 컨텍스트, 멀티패스 rerank → 비용↑/지연↑
- **지연↓**: 캐시/사전계산/작은 모델 우선 → 품질 변동 가능
- **비용↓**: 난이도 기반 라우팅, fallback, 배치처리 → 개발 복잡도↑

권장: "기본은 저비용 모델 + 실패/고난도만 상위 모델" 라우팅.

---

## 5) 오픈소스 fallback 제안

- Vision: YOLOv8/11 + Segment Anything + Depth Anything
- Embedding: bge-small/multilingual-e5
- Rerank: bge-reranker-base 또는 ms-marco cross-encoder
- LLM(자체호스팅): Llama 계열(요약/설명 템플릿용)

Fallback policy:
1) API 모델 실패/timeout
2) 오픈소스 파이프라인 실행
3) 최소 기능 규칙 기반 추천 반환

---

## 6) 최종 권장 기본 선택

1. 출시 초반: **A(Default)**
2. 트래픽 증가/원가 압박: **A + B 하이브리드** (난이도 라우팅)
3. 엔터프라이즈/프리미엄: **부분적으로 C**

핵심 KPI:
- 추천 성공률
- 평균 응답 시간(p95)
- 추천 1회당 AI 비용
- 사용자 저장/클릭/구매 전환율
