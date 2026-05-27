# ADR-007: DB로 SQLite + SQLModel ORM 채택

- **상태**: Accepted (Revised 2026-05-21)
- **이력**: 초기 Deferred였으나 사용자 결정으로 SQLModel 확정
- **관련 ADR**: ADR-008 (FastAPI)

## 컨텍스트

PRD에서 SQLite 사용은 확정되었고, ADR-008에서 백엔드 프레임워크로 FastAPI를 채택했다. ORM 사용으로 결정되었으므로, FastAPI 생태계와 가장 잘 통합되는 ORM을 선택한다.

## 결정

**SQLModel**을 채택한다.

```python
from sqlmodel import SQLModel, Field, create_engine, Session

class Routine(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 마이그레이션
**MVP에서는 Alembic 도입하지 않음**. `SQLModel.metadata.create_all(engine)`로 단순 테이블 생성.
첫 스키마 변경 시점 또는 P1 진입 시 `alembic init` 실행.

### Repository 패턴
`app/db/repositories.py`에서 CRUD를 추상화. `core` 레이어는 Repository만 호출하고 SQLModel을 직접 import하지 않음.

## 결과

### 긍정
- FastAPI 작자(Sebastián Ramírez)가 만든 도구 — 동일 철학·타입 시스템
- Pydantic 모델 = SQLAlchemy 모델 → 도메인 모델·DB 스키마 일원화
- FastAPI 엔드포인트 스키마로 그대로 사용 가능

### 부정
- SQLModel은 비교적 신규 (2021년~) — 일부 고급 기능에서 SQLAlchemy 직접 사용 필요할 수 있음
- ORM 학습 곡선 (raw SQL 대비 초기 느림)

## 대안

| 후보 | 탈락 사유 |
|---|---|
| SQLAlchemy 2.0 직접 사용 | 보일러플레이트 ↑, SQLModel이 1인 친화도 우위 |
| raw sqlite3 + Pydantic | 스키마 변경 마이그레이션 수동, 관계 처리 번거로움 |
| Tortoise ORM | async 네이티브이지만 FastAPI 통합 미흡 |
| Peewee | async 부재, FastAPI와 부조화 |
