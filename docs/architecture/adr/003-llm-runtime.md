# ADR-003: LLM 런타임으로 Ollama 채택

- **상태**: Accepted
- **작성일**: 2026-05-21
- **관련 ADR**: ADR-004 (모델), ADR-011 (동시 실행), ADR-014 (게임 워크플로우)

## 컨텍스트

로컬 LLM을 띄울 런타임이 필요하다. 후보는 Ollama, LM Studio, llama.cpp 직접 바인딩, vLLM 등이 있다. 환경은 Windows + RTX 5090(32GB VRAM)이며, ADR-014의 게임 시 수동 종료/재시작 워크플로우와 통합되어야 한다.

## 결정

**Ollama**를 LLM 런타임으로 채택한다.

- 환경변수 `OLLAMA_KEEP_ALIVE=1h`를 기본값으로 사용
- 코드에서 API 호출 시 `keep_alive` 파라미터로 동적 제어
- OpenAI 호환 엔드포인트(`/v1/chat/completions`) 사용

## 결과

### 긍정
- 헤드리스 데몬 형태로 동작, Windows 서비스 등록 자동
- `ollama stop` / `ollama serve` 명령으로 게임 워크플로우 통합 간단
- OpenAI 호환 API + 모델 동적 관리 API 모두 제공
- 오픈소스(MIT), 한국어 자료 풍부

### 부정
- Modelfile 추상화 한 단계 추가 — GGUF 직접 제어 시 약간 우회 필요
- llama.cpp 신규 모델 지원 대비 1~2주 지연 가능

## 대안

| 후보 | 탈락 사유 |
|---|---|
| LM Studio | GUI 의존, 헤드리스 약함, 클로즈드 소스 |
| llama.cpp 직접 바인딩 | 빌드·업데이트 관리 부담, 오버킬 |
| vLLM | Windows 지원 약함, 단일 사용자엔 오버킬 |
| Text Generation WebUI | GUI 의존, 자동화 약함 |
