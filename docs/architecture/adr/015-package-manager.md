# ADR-015: 패키지 매니저 — uv (Python) + pnpm (JS)

- **상태**: Accepted
- **작성일**: 2026-05-21

## 컨텍스트

Python 의존성 관리 도구는 pip, poetry, pdm, uv 등이 있다. JavaScript는 npm, yarn, pnpm이 있다. 1인 프로젝트의 개발 속도와 의존성 안정성을 동시에 고려해야 한다.

## 결정

| 영역 | 도구 | 잠금 파일 |
|---|---|---|
| Python | **uv** (Astral, Rust 기반) | `uv.lock` |
| JavaScript | **pnpm** | `pnpm-lock.yaml` |

설정 파일: `pyproject.toml` + `package.json`.

## 결과

### 긍정
- uv는 pip 대비 10~100배 빠름 — 1인 개발 사이클 단축
- uv는 Python 버전 관리도 통합 (`uv python install 3.11`)
- pnpm은 디스크 절약, npm 대비 빠름

### 부정
- uv는 신규 도구 (2024년 출시) — 생태계 안정성 모니터링 필요

## 대안

| 후보 | 탈락 사유 |
|---|---|
| poetry | 안정적이지만 느림, uv 우위 |
| pip + requirements.txt | lock 파일 부재 → 재현성 문제 |
| conda | 과한 추상화, 1인 부담 |
| npm | pnpm 대비 디스크·속도 열위 |
| yarn | pnpm 대비 강점 약함 |
