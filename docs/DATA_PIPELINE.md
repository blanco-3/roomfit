# SKU 데이터 파이프라인

## 현재 상태
- `scripts/generate_catalog.py`로 대량 SKU 카탈로그를 생성
- 생성 수량: 648개 (6개 카테고리 × 6개 소스 × 18개 변형)
- 출력 파일: `data/furniture_catalog.json`

## 사용법
```bash
python3 scripts/generate_catalog.py
```

## 컬럼
- id
- source
- name
- category
- width_cm / depth_cm / height_cm
- price_krw
- style_tags
- url

## 다음 단계 (실수집)
1. 소스별 커넥터 작성 (`scripts/connectors/*.py`)
2. 수집 raw 저장 (`data/raw/{source}.jsonl`)
3. 정규화 매핑 (치수/가격/카테고리 통일)
4. 중복 제거 (상품명 + 치수 + 가격 해시)
5. 주기 실행 (cron) + 변경 SKU 증분 반영

## 주의
- 현재 카탈로그는 데모/랭킹 튜닝용 대량 SKU 세트입니다.
- 운영 전환 시 실제 제휴/API/정책 준수 수집으로 교체해야 합니다.
