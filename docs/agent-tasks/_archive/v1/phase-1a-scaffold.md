# Task: Phase 1A — 프로젝트 골격

## 배경 자료 (먼저 읽기)
- `AGENTS.md` (필수)
- `docs/architecture/adr/015-package-manager.md`
- `docs/architecture/adr/016-no-wsl2.md`
- `docs/conventions/coding-style.md`

## 작업 범위
1. `uv init` → `pyproject.toml` 생성 (Python 3.11 고정)
2. AGENTS.md 4번의 폴더 구조 전체 생성 (빈 `__init__.py` 포함)
3. `.gitignore` (.venv, __pycache__, *.db, config.yaml, models/, node_modules 등)
4. `config.example.yaml` 템플릿 (llm/stt/tts/db/counting 섹션, 값은 ADR 기준)
5. `README.md` 초안 (셋업 순서, 실행법, 확장 안내)
6. `pyproject.toml`에 의존성 그룹 정의 (실제 설치는 다음 Phase, 여기선 선언만)

## 제약
- 폴더 구조는 AGENTS.md대로 정확히 (변경 금지)
- 코드 로직 작성 금지 — 골격과 설정만
- 의존성 버전은 명시하되 설치는 하지 마라

## 비범위
- DB 모델 (Phase 1B)
- 어댑터 구현 (Phase 2)

## 완료 기준
- `uv run python -c "print('ok')"` 동작
- 폴더 트리가 AGENTS.md와 일치
- config.example.yaml이 모든 ADR 설정값 포함

## 자가 보고
AGENTS.md 9번 형식으로 보고. code-review-checklist.md A·C 항목 확인.
