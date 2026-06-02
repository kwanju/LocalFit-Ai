---
description: 현재 변경분을 코드리뷰 체크리스트로 자가 점검 (v3 — ADR-012 4계층 분리 검증 포함)
---
지금까지의 변경분(`git diff`)을 `docs/conventions/code-review-checklist.md` 의 A~H 항목 기준으로 점검해줘.

규칙:
- 각 항목을 ✅ / ❌ / N/A 와 한 줄 근거로 표에 정리.
- ADR 또는 CLAUDE.md 규칙 위반이 있으면 명확히 지적.
- **ADR-012 4계층 분리 위반 별도 확인** — `core/`에 Pipecat·FastAPI·SQLModel·transformers import 없는지, `adapters/`가 `core` 역참조 안 하는지 grep으로 검증.
- v3 핵심 ADR(006 TTS·011 Pipecat·012 4계층·013 능동 코치·014 카운팅·020 캘린더) 결정과 어긋난 부분 명시.
- v1 자산 재활용 정책(CLAUDE.md §12) 준수 — 폐기 모듈을 재활용했거나 재활용 모듈을 잘못 폐기한 부분 점검.
- 통과 못 한 항목이 있으면 수정안을 제안(적용은 사용자 승인 후).
