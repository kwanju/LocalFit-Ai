# 테스트 전략 — 수동 디버깅 루프를 끊기 위한 심층 시나리오 테스트

> 작성 2026-06-08. 동기: v3 마무리 단계에서 "사용자가 직접 클릭 → 버그 발견 → 에이전트 수정 →
> 또 다른 버그" 루프가 반복됐다. 자동 테스트 280+개가 통과해도 사용자가 처음 부딪히는
> 버그가 끊이지 않았다. 이 문서는 **앱이 어느 정도 완성된 시점에 에이전트가 직접 시나리오를
> 수립·실행·로그검토·수정**해서, 사용자의 수동 디버깅에서 오류가 최대한 안 나오게 하는 절차다.
>
> 함께 읽기: `docs/retrospectives/2026-06-07-v3-lessons.md` (왜 루프가 생겼나).

---

## 0. 핵심 원칙 (한 줄)

**"사용자가 클릭으로 잡던 버그를, 에이전트가 시나리오 자동 구동 + 로그 검토로 먼저 잡는다."**

---

## 1. 왜 기존 테스트가 못 잡았나 — 버그 계층 지도

실제로 사용자가 먼저 발견한 버그들을 분류하면, 전부 **계층 경계**에서 났다. 각 버그가 어느
테스트 계층에서 잡혔어야 했는지 기록한다 (재발 시 그 계층을 의심).

| 실제 escaped 버그 | 근본 계층 | 잡았어야 할 테스트 |
|---|---|---|
| 채팅 입력이 `TextFrame`이라 ConfirmRule/Safety 우회 | serializer ↔ 프로세서 프레임 계약 | 백엔드 contract/scenario |
| 시스템 멘트(`TextFrame`)가 LLM을 깨워 GPU 경합 | 프레임 타입 의미 과적재 | 백엔드 scenario (LLM 호출 감시) |
| 카운트 큐가 TTS 집계로 뭉쳐 지연 재생 | TTSService 내부 텍스트 집계 | 백엔드 scenario (synth 단위 검증) |
| `is_active()` ← `@property`를 호출 | 런타임 배선 | 백엔드 scenario (실객체 + ErrorFrame) |
| ConfirmRule 활용형("시작할게요") 미인식 | 도메인 로직 | 백엔드 unit |
| `ws.end()`가 소켓을 안 닫아 세션 안 끝남 | UI WS 생명주기 | **UI unit (Vitest)** |
| 탭 이동 시 SessionProvider 언마운트 → 세션 종료 | UI 라우팅/생명주기 | **UI unit / 수동 E2E** |
| opener가 특정 경로에서만 발화 | UI 마운트/연결 타이밍 | 수동 E2E (브라우저) |

**교훈**: mock 편중 단위 테스트는 "내가 짠 함수"만 검증한다. 버그는 **모듈·계층·프로세스가
만나는 지점**에서 난다. 그 지점을 겨냥한 테스트가 없으면 무조건 사용자가 먼저 만난다.

---

## 2. 테스트 4계층과 각자 잡는 것

| 계층 | 위치 | 무엇을 잡나 | 실행 |
|---|---|---|---|
| **백엔드 unit** | `tests/unit/` | 순수 도메인 로직 (cue 선택, 확답 분류, WAV 인코딩 등) | `uv run pytest tests/unit -q` |
| **백엔드 scenario(통합)** | `tests/integration/test_counting_scenario.py` 등 | **실객체**를 엮어 사용자 흐름 구동 + **ErrorFrame 0 단언**. 런타임 배선·프레임 계약·GPU 경합 대리(=LLM 호출 여부) | `uv run pytest tests/integration -q -m "not gpu and not ollama"` |
| **UI unit (Vitest)** | `ui/src/**/*.test.ts(x)` | WS 생명주기, reducer 상태 전이, 메시지 계약. **Python이 못 건드리는 React/WS 로직** | `cd ui && pnpm test` |
| **수동 E2E (사람/브라우저)** | `docs/qa-checklist-v4.md` 체크리스트 | 실제 오디오 청취, 브라우저 자동재생, 마이크, 멀티탭, 음색 품질 | 사람이 §5 체크리스트로 |

> 비율 의식 (회고 원칙 4): unit 다수 + scenario 충분 + UI unit 필수 + 수동 E2E는 "기계가 못
> 듣는 것"으로 한정. 어느 하나 0이면 그 계층 버그는 전부 사용자 몫이 된다.

---

## 3. 백엔드 scenario 테스트 — 가장 중요한 패턴

`tests/integration/test_counting_scenario.py`가 본보기다. 핵심 규칙:

1. **mock이 아니라 실객체를 엮는다** — `CountingManager`, `ConfirmRuleProcessor`,
   `ActionDispatcherProcessor`, 실제 엔진. (mock manager는 `is_active()` 같은 런타임 오류를
   가린다 — 그 버그가 실제로 그렇게 샜다.)
2. **`run_test()`로 파이프라인을 구동**하고 **ErrorFrame이 있으면 실패**시킨다:
   ```python
   def _assert_no_error_frame(frames):
       errors = [f for f in frames if isinstance(f, ErrorFrame)]
       assert not errors, f"파이프라인 ErrorFrame: {[e.error for e in errors]}"
   ```
   사용자가 본 "코치 연결 문제 / bool is not callable"이 전부 ErrorFrame으로 나타났다.
3. **버그를 잡으면 그 시나리오를 즉시 추가** (회고 4-3 박제). 되돌려서 실제로 실패하는지 한 번
   확인한 뒤 수정 복구 — "잘못된 이유로 초록불"인 테스트를 방지.
4. 측정이 필요한 건 로그로 검증 (synth 단위, latency, 호출 횟수).

---

## 4. 에이전트의 심층 테스트 루프 (이 문서의 핵심 절차)

앱이 어느 정도 완성됐을 때(또는 사용자가 버그를 보고했을 때) 에이전트는 **수동 디버깅을
사용자에게 떠넘기지 말고** 다음을 직접 수행한다:

```
1. 시나리오 수립   — §6 카탈로그에서 관련 흐름 선정 (해피 + 안 행복한 경로 모두)
2. 자동 구동       — scenario 테스트로 실행 (없으면 작성). UI면 Vitest.
3. 로그 검토       — logs/localfit_YYYY-MM-DD.log 에서
                     · ERROR / WARNING / ErrorFrame
                     · latency.* (타임아웃·경합 징후)
                     · sentence synth (큐 뭉침·지연)
                     · beat/dispatch/confirm 흐름이 기대와 일치하는지
4. 근본 진단       — 표면 vs 근본 5분 질문 (회고 4-1). 프레임 타입? 생명주기? 계약?
5. 수정 + 박제     — 고치고, 그 시나리오를 테스트로 남김. 되돌려 실패 확인.
6. 회귀 전체 실행  — 백엔드 + UI 전 계층 green 확인
7. 사람 몫만 남김  — 오디오 청취/품질 등 기계가 못 하는 것만 사용자에게 요청
```

**로그 검토 빠른 명령** (Windows PowerShell / bash 공용 — bash 툴 기준):
```bash
f=$(ls -t logs/localfit_*.log | head -1)
grep -iE "ERROR|ErrorFrame|REJECTED|structured LLM call failed" "$f" | tail -40
grep -iE "latency\.|sentence synth|beat kind|start_set|complete" "$f" | tail -60
```

---

## 5. 출시 전(= master 동결 전) 심층 테스트 체크리스트

각 항목: scenario 테스트로 자동화돼 있으면 ✅(자동), 사람이 봐야 하면 👤(수동).

### 5-1. 세션 생명주기
- [ ] 세션 시작 → 종료 → 재시작 (UI `started` 리셋, 소켓 재연결) — ✅ `ws.test.ts`
- [ ] 운동 중 기록/설정 탭 이동 → 세션 유지 — 👤 (SessionShell 구조, 수동 확인)
- [ ] 시작(온보딩) 탭으로 이동 → 세션 종료 (의도된 동작) — 👤
- [ ] disconnect 후 늦게 도착한 LLM 응답이 운동 시작 안 시킴 — ✅ 백엔드

### 5-2. 능동 코치 / 확답
- [ ] opener가 모든 진입 경로에서 발화 — 👤 (브라우저 Network WS 확인)
- [ ] 다양한 긍정형 확답(좋아/ㄱㄱ/고고/시작할게요…) 수락 — ✅ `test_confirm_rule.py`
- [ ] 부정형(안 할래/나중에/안 해요) 거부 — ✅
- [ ] 카운팅 중 LLM 자발 start_counting 무시 — ✅ scenario
- [ ] 채팅(C2C)·음성(S2S) 입력 모두 Safety/Confirm 통과 — ✅ serializer + scenario

### 5-3. 카운팅
- [ ] 확답 → 카운트 시작, 하나~열 모두 발화(격려는 덧붙음) — ✅ scenario
- [ ] 큐가 코치 말/서로 안 뭉치고 박자에 맞게 개별 합성(TTSSpeakFrame) — ✅(구조) / 👤(청취)
- [ ] 다회 세트 + 자동 휴식 + 다음 세트 — 👤
- [ ] 카운팅 정지 버튼 — ✅ UIControl + 👤

### 5-4. 음성/오디오 (대부분 👤 — 기계가 못 들음)
- [ ] 첫 청크 지연 체감 (<1s) — 👤
- [ ] 음색 일관성 (큐마다 다른 목소리 X) — 👤 (config temperature/do_sample 튜닝)
- [ ] 코치 멈춤(인터럽트) 시 즉시 정지 (잔여 청크 포함) — 👤
- [ ] 모드 전환(C2C↔S2S) 후 입출력 정상 — 👤

### 5-5. 에러/빈 데이터
- [ ] 신규 사용자(기록 0) — "지난주처럼" 같은 과거 참조 안 함 — ✅ 프롬프트 + 👤
- [ ] LLM 타임아웃 시 카운팅은 독립 진행 — ✅ scenario
- [ ] 데이터 초기화(/admin/reset) 후 정상 — 👤

---

## 6. 사용자 시나리오 카탈로그 (scenario 테스트의 소스)

해피 경로 + **안 행복한 경로**(회고 원칙 1)를 한 쌍으로 적는다. 신규 시나리오는 여기 추가.

1. **신규 사용자 첫 세션**: 온보딩 → /session → opener → 제안 → 확답 → 카운트 → 종료
   - 안행복: 온보딩 스킵, 기록 0, 확답 대신 거절, 중간 탭 이동
2. **재방문 사용자**: 기존 프로필 → opener가 과거 패턴 언급 → 운동
   - 안행복: 마지막 운동 오래 전, 휴식 streak
3. **운동 중 이탈/복귀**: 카운팅 중 기록 탭 확인 → 복귀 (세션 유지)
   - 안행복: 설정에서 모드 변경, 카운팅 중 disconnect
4. **확답 변형**: "ㄱㄱ"/"고고"/"운동 시작할게요"/"네"/"콜" 등
   - 안행복: "나중에"/"안 할래"/"안 해요"/중립 발화
5. **다회 세트 + 휴식**: 10회 3세트 → 세트 간 자동 휴식 카운트다운 → 자동 다음 세트
   - 안행복: 휴식 중 사용자 발화, 마지막 세트 후 follow-up
6. **모드별 입출력**: C2C(채팅) / C2S(채팅→음성) / S2S(음성↔음성) / S2C(음성→채팅)
   - 안행복: 자동재생 차단(제스처 전), 마이크 권한 거부
7. **세션 종료/재시작**: 종료 버튼 → UI 리셋 → 재시작
   - 안행복: 종료 직후 탭 이동, 종료 후 재연결

---

## 7. 이 문서를 갱신하는 규칙

- 사용자가 새 버그를 보고하면 → §1 표에 (버그, 계층, 잡을 테스트) 추가 + §6에 시나리오 추가
- 그 시나리오를 자동 테스트로 박제하면 §5 체크리스트 항목을 ✅로 전환
- "기계가 못 듣는 것"만 👤로 남기고, 나머지는 점진적으로 자동화 비율을 올린다
