---
description: 현재 변경분을 코드리뷰 체크리스트로 자가 점검 (v4 — ADR-012 4계층 분리 검증 포함)
---
지금까지의 변경분(`git diff`)을 `docs/conventions/code-review-checklist.md` 의 A~H 항목 기준으로 점검해줘.

규칙:
- 각 항목을 ✅ / ❌ / N/A 와 한 줄 근거로 표에 정리.
- ADR 또는 CLAUDE.md 규칙 위반이 있으면 명확히 지적.
- **ADR-012 4계층 분리 위반 별도 확인** — `core/`에 Pipecat·FastAPI·SQLModel·transformers import 없는지, `adapters/`가 `core` 역참조 안 하는지 grep으로 검증.
- v4 핵심 ADR(021 3모드·025 영속메모리·023 컨디션·024 플랜·028 체력검증·031 Tauri·030 모델 lifecycle·027 알림·022 캘린더·029 qwen3.5:9b) 결정과 어긋난 부분 명시.
- v3 계승 ADR(006 TTS·011 Pipecat·012 4계층·013 능동 코치·014 카운팅·002 단일사용자) 도 함께 점검. v3와 충돌 시 v4 우선(ADR-021).
- 끝나면 `CLAUDE.md` §12 v1 자산 재활용 정책 준수 — 폐기 모듈을 재활용했거나 재활용 모듈을 잘못 폐기한 부분 점검.
- 통과 못 한 항목이 있으면 수정안을 제안(적용은 사용자 승인 후).
