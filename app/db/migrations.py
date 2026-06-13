"""Lightweight forward-only DB migrations (ADR-008, phase v4-1 scaffold).

SQLite + 단일 사용자(ADR-002)라 Alembic 은 과잉(YAGNI). `schema_version` 정수 +
순차 멱등 스텝 함수로 충분하다. `init_db()` 가 `create_all` 직후 `apply_migrations()`
를 호출한다 — 새 테이블은 `create_all` 이 만들고, **기존 테이블의 컬럼 추가/데이터
변환**만 여기 스텝으로 처리한다(create_all 은 기존 테이블을 ALTER 하지 않으므로).

스텝 추가 규칙 (phase 2·4 등에서):
- `_STEPS` 리스트 끝에 async 스텝 함수를 추가(버전 = 리스트 인덱스+1, 연속).
- 각 스텝은 **멱등**해야 한다 — 재실행해도 안전하게. 컬럼 추가는 아래 `_column_exists`
  가드를 쓰고, 데이터 UPDATE 는 자연 멱등하게 작성한다.
- 이미 적용된 스텝(버전 ≤ 현재)은 다시 실행하지 않는다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

MigrationStep = Callable[[AsyncConnection], Awaitable[None]]


async def _ensure_version_table(conn: AsyncConnection) -> int:
    await conn.execute(
        text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    )
    row = (await conn.execute(text("SELECT version FROM schema_version LIMIT 1"))).first()
    if row is None:
        await conn.execute(text("INSERT INTO schema_version (version) VALUES (0)"))
        return 0
    return int(row[0])


async def _set_version(conn: AsyncConnection, version: int) -> None:
    await conn.execute(text("UPDATE schema_version SET version = :v"), {"v": version})


async def _column_exists(conn: AsyncConnection, table: str, column: str) -> bool:
    """멱등 컬럼-추가 스텝용 가드. 후속 phase(메모리·플랜)에서 사용."""
    rows = (await conn.execute(text(f"PRAGMA table_info({table})"))).all()
    return any(r[1] == column for r in rows)


# --- steps (forward-only, 1-indexed by list position) ----------------------


async def _step_1_drop_s2c_mode(conn: AsyncConnection) -> None:
    """ADR-021: S2C 제거. 기존 세션의 ``mode='s2c'`` 행을 ``'s2s'`` 로 변환.

    S2C 는 마이크 on(음성입력)이었으므로 음성입력 모드 S2S 로 매핑한다.
    UPDATE 는 자연 멱등(두 번 돌려도 결과 동일).
    """
    await conn.execute(text("UPDATE session SET mode = 's2s' WHERE mode = 's2c'"))


async def _step_2_condition_checkin(conn: AsyncConnection) -> None:
    """ADR-023: 컨디션 체크인 — ``condition_log.soreness`` 추가 + ``session_id`` nullable.

    create_all 은 기존 테이블을 ALTER 하지 않으므로 구 스키마(``session_id`` NOT NULL,
    ``soreness`` 없음)를 SQLite 테이블 재작성으로 옮긴다. SQLite 는 컬럼 nullability 를
    직접 바꿀 수 없어 새 테이블 생성 → 복사 → DROP → RENAME 이 정석이다.

    멱등: 새 DB(create_all 이 이미 최신 스키마 생성) 또는 이미 적용된 경우 즉시 반환한다.
    condition_log 를 FK 로 참조하는 테이블이 없어 재작성이 안전하다.
    """
    rows = (await conn.execute(text("PRAGMA table_info(condition_log)"))).all()
    if not rows:
        return  # 테이블 부재(create_all 전) — 발생하지 않음
    by_name = {r[1]: r for r in rows}  # (cid, name, type, notnull, dflt, pk)
    has_soreness = "soreness" in by_name
    sid = by_name.get("session_id")
    session_notnull = bool(sid[3]) if sid is not None else False
    if has_soreness and not session_notnull:
        return  # 이미 최신/마이그레이션 완료
    soreness_src = "soreness" if has_soreness else "NULL"
    await conn.execute(
        text(
            "CREATE TABLE condition_log_new ("
            " id INTEGER NOT NULL PRIMARY KEY,"
            " session_id INTEGER,"
            " logged_at DATETIME NOT NULL,"
            " fatigue_level INTEGER,"
            " soreness INTEGER,"
            " pain_report VARCHAR,"
            " notes VARCHAR,"
            " FOREIGN KEY(session_id) REFERENCES session (id))"
        )
    )
    await conn.execute(
        text(
            "INSERT INTO condition_log_new"
            " (id, session_id, logged_at, fatigue_level, soreness, pain_report, notes)"
            f" SELECT id, session_id, logged_at, fatigue_level, {soreness_src},"
            " pain_report, notes FROM condition_log"
        )
    )
    await conn.execute(text("DROP TABLE condition_log"))
    await conn.execute(text("ALTER TABLE condition_log_new RENAME TO condition_log"))


async def _step_3_profile_assessment_seed(conn: AsyncConnection) -> None:
    """ADR-028: 온보딩 자가보고 시드 보존 — ``user_profile.assessment_json`` 추가.

    첫 체력검증 대화에서 코치가 원본 자가보고치를 시드로 쓰려면 보존이 필요하다
    (routine 처방은 0.65× 라 원본 손실). 단순 컬럼 추가라 ``_column_exists`` 가드로
    멱등 처리한다. 새 DB 는 ``create_all`` 이 이미 컬럼을 만들어 이 스텝은 즉시 반환.
    """
    if await _column_exists(conn, "user_profile", "assessment_json"):
        return
    await conn.execute(
        text("ALTER TABLE user_profile ADD COLUMN assessment_json VARCHAR NOT NULL DEFAULT '{}'")
    )


_STEPS: list[MigrationStep] = [
    _step_1_drop_s2c_mode,
    _step_2_condition_checkin,
    _step_3_profile_assessment_seed,
]


async def apply_migrations(engine: AsyncEngine) -> None:
    """Apply forward-only migration steps idempotently.

    ``init_db()`` 가 ``create_all`` 이후 매 기동 시 호출한다. 현재 버전 이후의
    스텝만 순서대로 적용하고 ``schema_version`` 을 갱신한다.
    """
    async with engine.begin() as conn:
        current = await _ensure_version_table(conn)
        target = len(_STEPS)
        if current >= target:
            return
        for version in range(current + 1, target + 1):
            step = _STEPS[version - 1]
            logger.info("Applying migration step {} ({})", version, step.__name__)
            await step(conn)
        await _set_version(conn, target)
    logger.info("DB migrations applied: {} -> {}", current, target)
