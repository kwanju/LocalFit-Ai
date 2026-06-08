# faster-qwen3-tts 통합 가이드 (다음 세션 진입점)

> 새 세션에서 이 문서를 진입점으로 작업 시작. 이 문서만 있으면 통합 끝까지 갈 수 있도록
> 작성. 현재 상태에서 PR 한두 개로 정리될 것.

## 0. 새 세션 시작 시 첫 메시지 (참고)

```
이전 세션 끝에서 faster-qwen3-tts 통합이 다음 작업으로 정해졌습니다.
조사·계획은 docs/future/faster-qwen3-tts.md 에 정리돼 있고, 그대로 진행 가능합니다.

먼저 다음 두 가지 확인 후 시작하겠습니다:
1. 현 MeloTTS 음성 품질에 만족하셨는지 (만족이면 faster-qwen3 보류 옵션)
2. GPU (RTX 5090) 에 약 4GB VRAM 여유 있는지 — 1.7B 모델 로딩에 필요

준비되면 §3 의 구현 순서대로 갑니다.
```

## 1. 결론 (1줄)

**현 `Qwen3-TTS-12Hz-1.7B-Base` 모델 그대로 유지 + 백엔드만 `faster-qwen3-tts` 로 교체**.
TTFA (Time-To-First-Audio) 5455ms → ~170ms 추정 (RTX 4090 기준), RTX 5090 이면 그 이하.

## 2. 조사 결과

### 2-1. faster-qwen3-tts 지원 모델

[andimarafioti/faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts) 에서 다음 변형 지원:

| 모델 | 인터페이스 | 우리에게 적합? |
|---|---|---|
| `Qwen/Qwen3-TTS-12Hz-0.6B-Base` | voice cloning (ref audio) | 더 작음 — 옵션 |
| **`Qwen/Qwen3-TTS-12Hz-1.7B-Base`** | **voice cloning (ref audio)** | **✅ 현재 사용 중. 그대로 유지** |
| `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | 미리 정의된 speaker ID | 한국어 speaker 유무 미확인. 우리는 안 씀 |
| `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | 자연어 instruct 로 음성 디자인 | 우리 use case 아님 |

### 2-2. Base vs CustomVoice 속도 차이

- 같은 1.7B 백본, 인터페이스만 다름
- faster 백엔드 (CUDA Graphs 캡처/재생) 는 두 변형 모두 동일 적용
- **속도 차이 무시 가능** — 인터페이스 선택은 voice 정책으로 결정 (우리는 voice cloning 이미 함)

### 2-3. 성능 (RTX 4090 기준)

| 변형 | TTFA | RTF |
|---|---|---|
| 0.6B-Base | 156ms | 4.78× |
| **1.7B-Base** | **174ms** | **4.22×** |

- RTX 5090 (Blackwell, sm_120) 은 4090 보다 빠름 — 더 좋은 수치 기대
- 현재 우리 첫 청크 5455ms → **약 31× 개선**

### 2-4. 호환성

- Python 3.10+ ✅ (우리 3.11)
- PyTorch 2.5.1+ — 확인 필요
- **Windows native 지원** ✅ (Linux/macOS WSL 도 OK)
- NVIDIA GPU + CUDA 필수
- RTX 40-series / H100 가 최적이지만 RTX 5090 도 호환 (Blackwell 은 CUDA 12.8+ 필요)

## 3. 구현 순서

### Step 1 — 의존성 추가

```bash
cd D:\claude-dev\localfit-ai
uv add faster-qwen3-tts
```

기존 `qwen-tts` 패키지는 일단 유지 (롤백 대비). 안정화 확인 후 제거.

PyTorch 버전 확인:
```bash
uv pip show torch | grep -i version
# 2.5.1+ 면 OK. 미만이면 업그레이드 필요.
```

### Step 2 — `app/adapters/tts/qwen3_client.py` 수정

현재 `_load_model` (line 124-152) 과 `_synth_sentence` (line 162-179) 가 핵심 교체 지점.

**변경 전 (현재)**:
```python
from qwen_tts import Qwen3TTSModel
model = Qwen3TTSModel.from_pretrained(
    model_id, device_map=..., dtype=torch.bfloat16, attn_implementation=...
)
# ...
wavs, sr = self._model.generate_voice_clone(
    text=sentence, language=self._language, voice_clone_prompt=self._voice_prompt,
)
```

**변경 후 (faster)**:
```python
from faster_qwen3_tts import FasterQwen3TTS
model = FasterQwen3TTS.from_pretrained(model_id)  # 인자 단순. dtype/attn 은 내부에서 결정.
# voice_clone_prompt 캐싱이 faster 에서 어떻게 되는지 README 재확인 — 아마 직접 ref_audio/ref_text 매 호출.
audio_list, sr = self._model.generate_voice_clone(
    text=sentence,
    language=self._language,
    ref_audio=self._ref_audio_path,
    ref_text=self._ref_text or None,
)
```

**주의 사항**:
- 현재 우리는 `_compute_voice_prompt()` 로 한 번만 prompt 계산해서 캐시 — faster API 에 같은 캐싱 메커니즘이 있는지 확인. 없다면 매 호출 ref 전달.
- `attn_implementation="sdpa"` → `"eager"` 폴백 로직은 faster 에서 불필요할 가능성 (자체 최적화). 폴백 코드 제거 가능 여부 README 재확인.

### Step 3 — Streaming 모드 도입

faster-qwen3-tts 는 `*_streaming()` 메서드로 token-level streaming 지원. 우리 현재는 sentence-batch.

**옵션 A — 그대로 sentence-batch 유지**:
간단. 첫 청크 latency 가 이미 ~170ms 라 sentence 끝까지 기다려도 OK.

**옵션 B — token streaming 으로 교체**:
첫 청크 latency 더 단축. 코드 변경 양 더 큼.

우선 옵션 A 로 시작, 만족 못 하면 B.

```python
# 옵션 A — 그대로
audio_list, sr = await asyncio.to_thread(
    self._model.generate_voice_clone, text=sentence, language=self._language,
    ref_audio=self._ref_audio_path, ref_text=self._ref_text,
)
```

```python
# 옵션 B — 스트리밍
async for chunk in self._model.generate_voice_clone_streaming(...):
    yield _float_to_pcm16(chunk)
```

### Step 4 — `config.yaml` 토글

`tts.active` 에 `"qwen3_fast"` 같은 새 값을 추가하거나, 기존 `qwen3` 의 의미를 faster 로 바꾸기.

```yaml
tts:
  active: "qwen3"              # melo / qwen3 (이제 faster 백엔드) / qwen3_legacy
  qwen3:
    model_id: "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
    ref_audio_path: "data/ref_voice.wav"
    ref_text: "..."
    # attn_implementation 제거 (faster 내부 처리)
    # device_map 제거 (faster 내부 처리)
    language: "Korean"
    timeout_sec: "30.0"          # latency 짧아져서 줄여도 됨
```

### Step 5 — `service_factory.py` 분기

`build_tts_service(client)` 에서 client 타입에 따라 적절한 Pipecat service 반환.
faster 가 같은 `Qwen3TTSClient` 클래스를 쓴다면 변경 없음. 만약 새 클라이언트 `FasterQwen3TTSClient` 를 분리한다면 분기 추가.

권장: **같은 `Qwen3TTSClient` 클래스 안에서 백엔드 분기** (config 토글로). 분리하면 코드 중복.

### Step 6 — 검증

#### 6-1. 단위 테스트
- `tests/integration/test_tts.py` 에 faster 모드 분기 추가 또는 기존 테스트 재실행
- TTFA, RTF 측정 → 로그로 검증 (`latency.tts.first_chunk=...ms`)

#### 6-2. E2E 검증 (사용자가 직접)
1. 백엔드 + UI 재시작
2. C2S 모드 → 코치 첫 응답 listen
3. **첫 청크 latency 가 1초 이내** 인지 (이전 5초)
4. 카운팅 시작 → "하나" "둘" 음성이 자연스럽게 이어지는지
5. 음성 품질 (MeloTTS 대비) 확인

#### 6-3. 회귀 체크
- 인터럽트 (탭 → stop)
- 모드 전환 (C2S → S2S)
- 세션 종료 (UI 종료 버튼)
- 세트 간 휴식 (자동 카운트다운 안내)

### Step 7 — 정리

검증 통과하면:
- `qwen-tts` 패키지 의존성 제거 (`uv remove qwen-tts`)
- ADR-006 개정 (faster-qwen3-tts 채택 명시)
- 사용자에게 GitHub commit 메시지 같이 검토 부탁

## 4. 리스크 & 대비

### 4-1. CUDA Graph 호환성
- faster 는 CUDA Graphs 로 decode 단계 캡처
- RTX 5090 의 sm_120 (Blackwell) 가 CUDA Graphs 지원 잘 되는지 확인
- 안 되면: 기존 `qwen-tts` 백엔드로 폴백 (config 토글)

### 4-2. PyTorch 2.5.1+ 요구
- 현 환경의 torch 버전 확인. 2.5.1 미만이면 업그레이드.
- 업그레이드 시 다른 의존성 (faster-whisper, melo 등) 충돌 가능
- 충돌 시: 별도 venv 또는 conda env 로 격리 테스트

### 4-3. voice cloning prompt 캐싱
- 현재 우리는 한 번만 ref_audio 처리 → 매 호출 prompt 만 전달
- faster API 가 같은 패턴 지원 안 하면 매 호출 ref_audio 전달 → 호출당 prompt 계산 비용 추가
- TTFA 측정에 포함된 부담 (블로그의 1.48s 는 hot loop 평균 — 같은 prompt 재사용)

### 4-4. 한국어 품질
- faster 는 백엔드만 빠르게 — 음성 품질은 동일 모델
- MeloTTS 대비 Qwen3 의 한국어 자연스러움이 어떤지 사용자 청취 필요
- 만약 Qwen3 도 어색하면 다른 TTS 모색 (v4 로 미루기)

### 4-5. 메모리
- 1.7B 모델 + CUDA Graphs 캡처 → VRAM 약 3-4GB 추정
- faster-whisper (1.5GB) + Qwen3-TTS + LLM (qwen3:8b ~5GB) → 총 10GB+
- RTX 5090 32GB 여유 충분 — OK

## 5. 작업 일정 가늠

| 단계 | 예상 시간 |
|---|---|
| 의존성 설치 + 환경 확인 | 30분 |
| qwen3_client.py 수정 + 테스트 | 1-2시간 |
| config + 토글 + service_factory | 30분 |
| E2E 검증 (사용자) | 30분 |
| 회귀 체크 + ADR 개정 | 30분 |
| **총** | **3-4시간** |

PR 한 개로 마무리 가능. 실패 시 config 토글로 즉시 melo 또는 qwen3-legacy 로 롤백.

## 6. 관련 파일 위치

- 어댑터: `app/adapters/tts/qwen3_client.py`
- Pipecat 래퍼: `app/pipecat_services/qwen3_tts_service.py`
- 서비스 팩토리: `app/pipecat_services/service_factory.py`
- 어댑터 선택: `app/adapters/tts/__init__.py` (`get_tts_adapter`)
- 설정: `config.yaml` (`tts.active`, `tts.qwen3.*`)
- ADR: `docs/architecture/adr/adr-006-tts.md` (혹은 인덱스에서 확인)

## 7. 참고 링크

- faster-qwen3-tts GitHub: https://github.com/andimarafioti/faster-qwen3-tts
- Qwen3-TTS 공식: https://github.com/QwenLM/Qwen3-TTS
- Base 모델: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base
- 블로그 (한국 개발자 분석): https://developer-bing-gu.tistory.com/entry/Qwen3-TTS-%EC%B5%9C%EC%A2%85-%EC%84%A0%ED%83%9D%EC%9D%80-%EB%AC%B4%EC%97%87%EC%9D%B4%EC%97%88%EB%82%98

## 8. 작업 끝나면 업데이트할 것

### 실측 결과 (2026-06-07, RTX 5090 + torch 2.11.0+cu128)

| 항목 | 측정값 | 비고 |
|---|---|---|
| 모델 로드 | 22.2s | startup 1회 |
| warmup 합성 (CUDA graph 캡처) | ~6.5s | `__init__`에서 흡수 → 첫 사용자 발화 빠름 |
| HOT 비스트리밍 (문장) | ~470~970ms | RTF ~0.34x |
| **sentence-batch 첫 청크 5x 평균** | **884ms** | 기존 4818ms → **5.5x 개선** |
| streaming 첫 청크 (chunk_size=12) | 391ms | Option B 도입 시 |

- API 차이: `create_voice_clone_prompt` 메서드 없음(README 오류). 대신 `FasterQwen3TTS`가 `(ref_audio, ref_text)` 키로 **내부 캐싱** → 매 호출 ref만 전달하면 됨. `from_pretrained`는 `device`/`dtype`/`attn_implementation` 그대로 수용.

### 체크리스트 (2026-06-08 완료)

- [x] 실측 TTFA / RTF 수치 (위 표)
- [x] ADR-006 개정 (`docs/architecture/adr/006-tts.md` §faster-qwen3-tts 백엔드, 2026-06-07 개정)
- [x] config.yaml / config.example.yaml: `active: qwen3`, `device`(was device_map), `timeout 30s`
- [x] 단위 + GPU 통합(qwen3) 통과
- [x] **사용자 브라우저 E2E** — opener/카운트TTS/탭이동/세션종료 확인. 후속 버그(카운트 뭉침·드롭, 휴식 침묵, 음색 일관성, 5세트 수정, 플랭크 시간) 전부 수정 (커밋 `697801b` 외).
- [x] 음성 품질/일관성: `do_sample=false` + `xvec_only=true` (x-vector 클로닝)로 음색 고정. temperature 0.7.
- [x] ~~`qwen-tts` 패키지 제거~~ → **불가**: `faster-qwen3-tts`가 `qwen-tts`를 transitive 의존성으로 요구함(lock 확인). 대신 **우리 명시적(direct) 의존성에서만 제거** (pyproject `gpu` 그룹: qwen-tts → faster-qwen3-tts). qwen-tts는 faster를 통해서만 설치됨.
- [x] 통합 완료 → 이 문서 `docs/_archive/v3/` 로 이동 (2026-06-08)
