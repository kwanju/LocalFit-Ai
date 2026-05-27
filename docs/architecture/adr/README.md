# Architecture Decision Records (ADR)

LocalFit AI의 모든 아키텍처 결정 이력입니다. 각 결정은 독립된 마크다운 파일로 관리되며, 새 결정이 생길 때마다 번호를 증가시켜 추가합니다.

## 형식

각 ADR은 다음 섹션을 포함합니다.

- **Status**: Proposed / Accepted / Deferred / Superseded / Deprecated
- **Context**: 결정이 필요한 배경
- **Decision**: 채택된 결정
- **Consequences**: 결과 (긍정·부정 모두)
- **Alternatives**: 검토했으나 탈락한 대안과 이유

## 변경 정책

- 한 번 Accepted된 ADR은 **수정하지 않습니다**. 결정을 바꾸려면 새 번호로 ADR을 발행하고, 이전 ADR의 Status를 `Superseded by ADR-XXX`로 갱신합니다.
- ADR-007처럼 보류였다가 재결정된 경우는 동일 번호로 갱신하되, 본문에 `(Revised YYYY-MM-DD)` 표기합니다.

## 인덱스

| # | 제목 | 상태 |
|---|---|---|
| [001](001-main-language.md) | 메인 언어로 Python 채택 | Accepted |
| [002](002-mvp-topology.md) | MVP 토폴로지 — 데스크탑 단독 백엔드 | Accepted |
| [003](003-llm-runtime.md) | LLM 런타임으로 Ollama 채택 | Accepted |
| [004](004-llm-models.md) | 듀얼 LLM 모델 — Qwen 3.5 9B + Gemma 4 E4B | Accepted (Revised) |
| [005](005-stt.md) | STT로 faster-whisper (large-v3-turbo) | Accepted (Revised) |
| [006](006-tts.md) | TTS 교체형 어댑터 (Kokoro + Qwen3-TTS) | Accepted (Revised) |
| [007](007-db-orm.md) | DB로 SQLite + SQLModel ORM 채택 | Accepted (Revised) |
| [008](008-backend-framework.md) | 백엔드 프레임워크로 FastAPI 채택 | Accepted |
| [009](009-ui-framework.md) | UI 프레임워크로 React + Vite PWA | Accepted |
| [010](010-adapter-interfaces.md) | 핵심 어댑터 인터페이스 명세 | Accepted |
| [011](011-model-concurrency.md) | 모델 동시 실행 전략 | Accepted |
| [012](012-vad.md) | VAD로 silero-vad 채택 | Accepted |
| [013](013-model-download.md) | 모델 다운로드 전략 | Accepted (Revised) |
| [014](014-process-lifecycle.md) | 프로세스 라이프사이클 및 게임 워크플로우 | Accepted |
| [015](015-package-manager.md) | 패키지 매니저 — uv + pnpm | Accepted |
| [016](016-no-wsl2.md) | WSL2 미사용, Windows 네이티브 Python | Accepted |

## 후속 검토 예정

다음은 ADR로 정식 작성 가치가 있으나 현재는 미작성된 항목입니다.

- ADR-017 (예정): 로깅·관측성 전략 (loguru + 파일 로그)
- ADR-018 (예정): 테스트 전략 (pytest + 어댑터 Mock 패턴)
- ADR-019 (예정): 듀얼 LLM 회고 후 단일 모델 좁히기 또는 의도별 라우팅 결정

각 항목은 첫 코딩 진입 시 또는 P1 회고 시점에 결정합니다.
