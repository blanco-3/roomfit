# Postgres Migration Path (Roomfit)

## 목적
현재 SQLite 기반 데이터를 Postgres로 점진 전환하기 위한 안전한 경로를 제공합니다.

## 1) 환경 변수
```bash
export DATABASE_URL="postgresql://<user>:<pass>@<host>:5432/roomfit"
```

현재 코드는 Postgres 연결 드라이버를 아직 포함하지 않았고, **스캐폴드 단계**입니다.
즉, 당장은 SQLite 운영 + 데이터 export/import 준비가 목적입니다.

## 2) 스키마 준비
- `app/db.py`의 테이블 구조를 기준으로 Postgres DDL 생성
- 권장: Alembic 초기 마이그레이션 생성

핵심 테이블:
- users, auth_tokens, room_profiles, room_photos, recommendation_runs, ops_logs, cv_jobs

## 3) 데이터 내보내기 (SQLite)
```bash
PYTHONPATH=. .venv/bin/python scripts/export_sqlite_to_json.py
```
- 결과: `data/sqlite_export.json`

## 4) 데이터 적재 (Postgres)
- 초기에는 간단 Python import 스크립트로 적재
- 이후 운영 단계에서는 Alembic + ETL job으로 표준화

## 5) 롤아웃 전략
1. Shadow write (옵션): SQLite + Postgres 동시 기록 검증
2. Read switch: 읽기 트래픽 Postgres로 단계 전환
3. SQLite를 백업/롤백 경로로 일정 기간 유지

## 6) 체크리스트
- [ ] Postgres 드라이버/클라이언트 계층 구현
- [ ] Alembic baseline migration
- [ ] import script 작성 + dry-run 검증
- [ ] staging 부하 테스트
- [ ] cutover + rollback plan 문서화
