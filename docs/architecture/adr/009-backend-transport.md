# ADR-009: 백엔드 — FastAPI + Pipecat FastAPIWebsocketTransport

- **상태**: Accepted (2026-05-31)
- **관련 ADR**: ADR-002 (127.0.0.1), ADR-008 (DB), ADR-011 (Pipecat), ADR-012 (어댑터)

## 컨텍스트

v1은 FastAPI + 자체 WebSocket(`/ws/coach`)을 사용했다. v3는 Pipecat을 전면 채택(ADR-011)하므로 음성 파이프라인 transport를 Pipecat이 제공하는 것 중 선택해야 한다.

후보 transport (Pipecat 공식):
- `FastAPIWebsocketTransport` — FastAPI WebSocket 위에서 동작, telephony·로컬 모두 가능
- `WebsocketTransport` (server) — 단독 WebSocket 서버
- `DailyTransport` / `LiveKitTransport` — WebRTC 기반, SFU 의존
- `LocalAudioTransport` — 같은 프로세스에서 mic·speaker 직접 캡처

본 프로젝트는 브라우저 PWA(ADR-010)가 mic 캡처를 하고 WebSocket으로 백엔드에 보낸다 → `FastAPIWebsocketTransport`가 자연 fit. WebRTC는 단일 사용자 환경에 over-engineering.

## 결정

- **백엔드 프레임워크 = FastAPI 0.115+**
- **음성 파이프라인 transport = `pipecat.transports.network.fastapi_websocket.FastAPIWebsocketTransport`**
- **REST API** = FastAPI 그대로 (`/health`, `/api/session/*`, `/api/routine/*`, `/api/onboarding/*`)
- **음성 WS 엔드포인트** = `/ws/voice` (Pipecat 파이프라인 마운트)
- **lifespan**: 시작 시 LLM warmup, 종료 시 graceful shutdown

### 엔드포인트 구조

```
GET  /health                       # 어댑터 + Pipecat 상태
GET  /api/profile                  # 사용자 프로필
POST /api/profile                  # 온보딩 저장
GET  /api/session/recent           # 최근 세션 목록
POST /api/session/start            # 세션 시작
POST /api/session/end              # 세션 종료
GET  /api/routine                  # 활성 루틴
POST /api/routine                  # 루틴 갱신
WS   /ws/voice                     # Pipecat 음성 파이프라인 (S2S/S2C/C2S/C2C 4-모드)
```

### 4-모드 분리

음성 파이프라인 WS 하나로 STT/TTS on/off만 토글하면 4-모드가 자연 동작:
- S2S: STT on + TTS on
- C2S: STT off + TTS on (텍스트는 별도 frame으로 inject)
- C2C: STT off + TTS off
- S2C: STT on + TTS off

각 모드는 Pipecat 파이프라인 조립 시점에 결정 (세션 시작 시 사용자가 mode 지정).

### lifespan 책임

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. DB 초기화
    init_db()
    # 2. LLM warmup (Ollama keep_alive 24h)
    await llm_service.warmup()
    # 3. TTS 모델 로드 + ref WAV latent 캐시
    await tts_service.warmup()
    # 4. STT 모델 로드
    await stt_service.warmup()
    yield
    # 종료: Pipecat 파이프라인 graceful cancel
    await pipeline_runner.cancel_all()
```

## 결과

### 긍정
- v1 FastAPI 자산 그대로 재사용 — REST 부분 변경 없음
- Pipecat 공식 transport — 별도 글루 코드 최소
- 단일 WS 엔드포인트로 4-모드 처리 — 코드 단순
- lifespan에서 warmup → 첫 사용자 요청 cold start 0

### 부정
- Pipecat은 공식적으로 일반 client/server엔 WebRTC 권장 — 우리는 단일 사용자·로컬이라 WebSocket 충분하나 best path에서 벗어남 (사용자 검증 후 WebRTC 도입은 P1)
- `FastAPIWebsocketTransport`는 telephony 위주로 진화 중 — 일반 PWA 사용 사례 문서·예제 적음
- 인터럽트 처리는 v1보다 견고하나, audio buffer flush 등 검증 필요

## 대안

| 후보 | 탈락 사유 |
|---|---|
| `WebsocketTransport` (Pipecat 단독 서버) | FastAPI REST 자산과 분리 — 두 서버 운영 부담 |
| `LocalAudioTransport` | 브라우저 PWA가 mic 캡처 — 백엔드가 직접 mic 접근 안 함 |
| `DailyTransport` / `LiveKitTransport` (WebRTC SFU) | 단일 사용자엔 over-engineering, SFU 운영 부담 |
| v1 자체 WebSocket 유지 | ADR-011 Pipecat 채택과 모순, 인터럽트 견고성 직접 구현 부담 |

## References
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/)
- [Pipecat FastAPIWebsocketTransport](https://docs.pipecat.ai/server/services/transport/fastapi-websocket)
- [Pipecat Transport Overview](https://docs.pipecat.ai/server/services/transport/overview)
