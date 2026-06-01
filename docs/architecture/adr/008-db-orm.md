# ADR-008: DB — SQLite + SQLModel

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-002 (단일 사용자), ADR-013 (능동 코치 컨텍스트 빌더)

## 컨텍스트

v1에서 SQLite + SQLModel 조합이 검증됐다. 단일 사용자 환경에서 동시성 이슈 없음, 마이그레이션은 코드 변경으로 처리(Alembic 미사용). v3에서 변경 사유 없음.

## 결정

- **DB = SQLite 3.x** (앱 시작 시 `data/localfit.db` 자동 생성)
- **ORM = SQLModel 0.0.20+** (FastAPI 생태계 표준)
- **마이그레이션** = 코드 기반 (`SQLModel.metadata.create_all`) — Alembic 미사용 (단일 사용자, 데이터 수십~수백 행 규모)
- **테이블 명명 규칙**:
  - 클래스명 = `WorkoutSession` (sqlmodel.Session과 충돌 회피, v1 known_constraint 계승)
  - JSON 컬럼명 = `extra_data` (`metadata` 예약어 회피, v1 known_constraint 계승)
- **Repository 패턴**: 단순 SELECT는 직접 호출 허용, 복잡 쿼리는 Repository 경유 (`UserProfileRepository`, `SessionRepository`, `SetLogRepository`, `ConditionRepository`, `RoutineRepository`)

### 주요 테이블

| 테이블 | 용도 |
|---|---|
| `user_profile` | 단일 사용자 프로필 (1 행) |
| `session` | 운동 세션 (시작/종료/모드/총 볼륨) |
| `set_log` | 세트 단위 기록 (운동·렙·세트·실제 수행 여부) |
| `condition_log` | 컨디션 체크인 (1~10점, 자유 텍스트) |
| `interaction_log` | LLM 입출력 로그 (분석용, P1) |
| `routine` | 주간 루틴 + exercise 매핑 |

### 능동 코치 컨텍스트 활용

ADR-013 컨텍스트 빌더는 다음 Repository read를 사용한다:
- `UserProfileRepository.get()` — 프로필 1건
- `SessionRepository.get_recent(n=5)` — 최근 5세션 요약
- `SetLogRepository.get_by_session(session_id)` — 직전 세트 기록
- `ConditionRepository.get_recent(n=3)` — 최근 컨디션 체크인
- `RoutineRepository.list_all()` — 활성 루틴

## 결과

### 긍정
- v1 검증 그대로 — 회귀 위험 0
- SQLite + Python 단일 의존성 — 외부 DB 서버 불필요
- SQLModel = Pydantic + SQLAlchemy 결합으로 type-safe

### 부정
- SQLite는 동시 쓰기 부족 — 단일 사용자 환경엔 무관
- 마이그레이션 자동화 없음 — 스키마 변경 시 수동 백업 + 재생성 (소량 데이터라 OK)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| PostgreSQL | 단일 사용자에 over-engineering |
| DuckDB | OLAP 위주 — 운동 기록은 OLTP 패턴 |
| TinyDB / JSON 파일 | 쿼리·조인 부족 |
| Pure SQLAlchemy | SQLModel이 FastAPI 통합 더 자연스러움 |

## References
- [SQLModel](https://sqlmodel.tiangolo.com/)
- [SQLite 동시성 가이드](https://www.sqlite.org/lockingv3.html)
- v1 known_constraints — `WorkoutSession`/`extra_data` 네이밍 계승
