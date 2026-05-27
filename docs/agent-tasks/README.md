# 에이전트 작업 템플릿

각 Phase 작업을 코딩 에이전트에 던질 때 사용하는 명세. 의존성 순서대로 진행.

## 진행 순서

| Phase | 파일 | 의존 | 추정 |
|---|---|---|---|
| 0 | phase-0-poc.md | 없음 (직접 수행) | 1~3시간 |
| 1A | phase-1a-scaffold.md | 0 | 30분 |
| 1B | phase-1b-infra.md | 1A | 반나절 |
| 2A | phase-2a-llm-adapter.md | 1B | 반나절 |
| 2B | phase-2b-stt-adapter.md | 1B | 반나절 |
| 2C | phase-2c-tts-adapter.md | 1B | 반나절 |
| 3 | phase-3-domain-core.md | 2A | 2~3일 |
| 4A | phase-4a-orchestrator.md | 2,3 | 1~2일 |
| 4B | phase-4b-api.md | 4A | 반나절 |
| 5 | phase-5-ui.md | 4B | 3~4일 |
| 6 | phase-6-validation.md | 5 | 2일 |

총 예상: 13~17일 (풀타임 기준)

## 사용법

1. 새 에이전트 세션 시작
2. 해당 phase 파일 + AGENTS.md를 컨텍스트에 제공
3. "이 작업을 수행해줘" 지시
4. 완료 보고 받으면 code-review-checklist.md로 검증
5. 통과 시 커밋, 다음 phase로

## 주의
- 2A/2B/2C는 병렬 가능 (서로 독립)
- Phase 3, 5는 하위 작업 묶음 — 하위 작업마다 별도 세션 권장
- UI(Phase 5)는 Python과 별도 컨텍스트로
