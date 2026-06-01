# Task: Phase 1B — 인프라 기초 (config, DB, logging)

## 배경 자료
- `AGENTS.md`
- `docs/architecture/adr/007-db-orm.md`
- `docs/architecture/adr/008-backend-framework.md` (config 로딩 맥락)
- `docs/conventions/coding-style.md` 5번 (설정·상수)
- 데이터 스키마 정의 (이전 설계 산출물의 SQLModel models.py)

## 작업 범위
1. `app/config.py` — Pydantic Settings로 config.yaml 로딩 + 검증. `DEFAULT_USER_ID = 1` 상수
2. `app/db/models.py` — SQLModel 테이블 정의 (UserProfile, Exercise, Routine, RoutineExercise, Session, SetLog, ConditionLog, InteractionLog) + Enum + EXERCISE_SEED
3. `app/db/engine.py` — SQLite 엔진(WAL 모드), `init_db()`, `get_session()`
4. `app/db/repositories.py` — SessionRepository, SetLogRepository, ConditionRepository, InteractionRepository (기본 CRUD)
5. `app/utils/logging.py` — loguru 설정 (파일 + 콘솔, 영어 로그)
6. `tests/unit/test_db_models.py` — 테이블 생성 + 시드 삽입 검증

## 제약
- 멀티유저 금지 — user_profile_id는 항상 DEFAULT_USER_ID 사용
- Repository 패턴 준수 (ADR-007)
- JSON 컬럼(metadata, available_times)은 검색 안 함 전제

## 비범위
- API 엔드포인트 (Phase 4B)
- Alembic (MVP 미사용, P1)

## 완료 기준
- `uv run python -c "from app.db.engine import init_db; init_db()"` → DB 파일 + 4종 운동 시드 생성
- `pytest tests/unit/test_db_models.py` 통과

## 자가 보고
AGENTS.md 9번 형식. checklist A·C·D·E 확인.
