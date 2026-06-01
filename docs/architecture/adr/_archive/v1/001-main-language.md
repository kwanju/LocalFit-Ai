# ADR-001: 메인 언어로 Python 채택

- **상태**: Accepted
- **작성일**: 2026-05-21
- **결정자**: 프로젝트 오너 (1인)

## 컨텍스트

LocalFit AI는 로컬 LLM 기반 오프라인 우선 피트니스 코치 앱이다. PRD가 명시한 핵심 라이브러리(Whisper, Ollama, Kokoro-82M, Coqui TTS, silero-vad, webrtcvad)가 모두 Python을 1차 시민으로 지원한다. 1인 프로젝트이며 한국어 처리가 필수다.

## 결정

백엔드(AI 및 도메인 로직) 전체를 **Python 3.11+**로 작성한다.

UI는 별도 ADR-009에서 결정하며, 백엔드와 UI 사이는 로컬 HTTP/WebSocket으로 통신한다.

## 결과

### 긍정
- Whisper, Ollama, Kokoro, Coqui 통합에서 마찰이 최소화된다
- AI 모델 교체와 실험 속도가 빠르다 (PRD 미결 사항 #1 TTS 비교에 유리)
- 동시성은 `asyncio` 기반으로 일관되게 처리 가능

### 부정
- 패키징이 까다롭다 — MVP에서는 "내 컴퓨터에서 동작"만 목표로 두고, 배포 패키징은 부록 D(QA) 시점 이후로 미룬다
- GIL 때문에 카운팅·LLM·STT 동시 실행은 `asyncio` 설계 + Ollama 등 외부 프로세스 활용이 필요하다
- 타입 안정성은 mypy/pyright로 별도 확보해야 함

## 대안

| 후보 | 탈락 사유 |
|---|---|
| TypeScript/Node.js | Whisper 바인딩이 fragile하고 Kokoro/Coqui 통합이 거의 없음 |
| Rust | candle 등 AI 생태계 미성숙, 학습 곡선이 1인 프로젝트를 죽일 위험 |
| Go | AI 라이브러리 빈약 |
| Python + TypeScript 하이브리드 | UI 계층에서 자연스럽게 도입됨 (ADR-009 참조) |
