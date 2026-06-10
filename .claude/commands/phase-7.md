---
description: Phase v4-7 — 모델 lifecycle on-demand (세션 로드/언로드 + 콜드스타트 완화) (030)
---
`docs/agent-tasks/v4/phase-7-model-lifecycle.md` 의 작업을 수행해줘.

규칙:
- 먼저 `CLAUDE.md` 와 phase 명세의 "관련 ADR"에 적힌 ADR(030, 029, 005, 006, 015)만 읽어라. 그 외 ADR은 읽지 마라 (컨텍스트 절약).
- v4 우선: ADR-030 으로 ADR-015(상주 정책) Superseded. lifespan 전모델 상주 → 세션 로드/언로드(Ollama `keep_alive=0` + `empty_cache()`)로 교체.
- 병렬 로드 + 앱-열림 prewarm + "코치 준비 중" UX 로 콜드스타트(~30s) 체감 단축. 스케줄러 prewarm 은 금지. VRAM 완전 반환 실측 게이트.
- 의존: phase 6(Tauri 셸)이 들어와 있어야 의미. `CLAUDE.md` §4 폴더 구조 고정, §6 외부 호출 정책, §8 의존성 추가 시 사용자 확인 필수.
- 끝나면 `CLAUDE.md` §9 보고 형식 + `docs/conventions/code-review-checklist.md` 자가 점검 결과 포함.
- ADR/PRD와 충돌하거나 모호하면 멈추고 사용자에게 물어라.
