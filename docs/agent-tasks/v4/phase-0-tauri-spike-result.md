# Phase v4-0 — Tauri 탐사 결과 (Go/No-Go 기록)

> 명세: `phase-0-tauri-spike.md`. 본 문서는 회고 4-3(재현 가능 기록).
> 진행: 2026-06-10. **결론: GO** (사용자 결정 — native 확정). S-4 마이크 입력은 GO 차단 아닌 **후속 fix 항목**으로 이월. 상세 §3.

## 0. 환경 (실측)

| 항목 | 값 |
|---|---|
| OS | Windows 10 Pro 19045 |
| Rust | 1.59.0 → **1.96.0** 로 갱신 (Tauri 2 최소 1.77.2). rustup `stable` 채널. |
| 링커 | MSVC 14.43 (VS 2022 BuildTools) — `target_env=msvc` |
| WebView2 | 런타임 설치됨 (Edge WebView **148** 가동 확인) |
| Node / pnpm | 24.16.0 / 11.4.0 |
| Tauri | CLI/API **2.11.2 / 2.11.0**, tauri crate 2.11.2 |
| GPU | RTX 5090 32GB (S-8 의 16GB 베이스라인은 의도적 모사) |

> ⚠️ **Rust 1.59 → 1.96 갱신이 S-1 의 첫 관문이었다.** v2 가 우려한 "툴체인이 막힘" 시나리오는 rustup 갱신으로 해소(되돌리기 가능). 1.59 그대로였다면 Tauri 2 는 컴파일 불가였다.

## 1. 게이트별 결과

### S-1. Tauri 빌드·실행 — ✅ PASS
- 빈 스캐폴드 `cargo build` (dev): **1m16s, exit 0**, `app.exe`(13MB) 산출.
- 트레이+알림+사이드카 추가 후 `cargo build`: **51.97s, exit 0** (증분).
- `tauri build` (release): **exit 0**, 설치본 2종 산출 —
  `bundle/nsis/LocalFit AI_0.1.0_x64-setup.exe` (**2.0MB**),
  `bundle/msi/LocalFit AI_0.1.0_x64_en-US.msi` (3.0MB), release `app.exe` 8.9MB.
  (cf. Electron 대비 1/50 수준. **단 Python 백엔드/모델은 미번들** — 사이드카 번들 후순위 §5.)
- Git `link.exe` 가 PATH 에서 MSVC 보다 앞서는 Windows 고질 이슈 → **무영향**(MSVC 링커로 정상 링크).
- 더블클릭 실행(installer): [사람 검증 대기]

### S-2. 기존 React UI 웹뷰 탑재 — ✅ PASS (실사용 확인)
- `ui/` 프로덕션 빌드 정상(366 모듈). `tauri.conf.json`: `frontendDist=../dist`, `devUrl=http://localhost:5173`.
- **실측**: webview2 창에서 사용자가 실제 코칭 세션 다수 구동 —
  모드 토글(C2C/C2S), 운동 제안(푸시업/스쿼트/플랭크), 카운팅 풀세션(스쿼트 3/3, reps=15) 정상.
  → 기존 React PWA 재작성 없이 그대로 탑재됨(no-go 가중치 컸던 항목, 깔끔 통과).

### S-3. 백엔드 WebSocket 연결 — ✅ 프로토콜 PASS, [웹뷰-출처 사람 검증]
- `/ws/voice?mode=C2C` 핸드셰이크 + **텍스트 라운드트립 성공**: "안녕" 송신 →
  코치 응답 `"오늘은 푸시업 10회 3세트, 휴식 30초로 갈까요?"` + `session_started` 프레임 수신.
  (JsonFrameSerializer + LLM 경로 전부 동작.)
- dev: Vite(5173) 가 `/ws` 를 `127.0.0.1:8000` 으로 프록시 → 웹뷰가 same-origin.
- prod: `ui/src/api/ws.ts` 가 `VITE_WS_BASE` override 지원 → `ws://127.0.0.1:8000` 직결 가능(프록시 불필요).
- 확인 필요: 웹뷰(채팅 모드)에서 직접 라운드트립.

> **통합 함정 1건 발견·해결**: `tauri dev` 가 Vite watcher EBUSY 로 죽음 — Vite 가
> `src-tauri/target/app_lib.dll` 을 감시하다 cargo 링크와 충돌. `vite.config.ts` 에
> `server.watch.ignored=["**/src-tauri/**"]` 추가로 해결(Tauri+Vite 표준 설정). no-go 아님.

### S-4. 마이크 캡처 + 오디오 출력 — 🟡 출력 PASS, 입력(마이크) [검증 대기]
- **오디오 출력 ✅**: webview2 에서 TTS 스트리밍 재생 정상 — `tts.first_chunk=370~597ms` 다수.
- **마이크 입력 ❓**: 사용자가 C2C/C2S(텍스트 입력) 위주로 테스트 → webview2 `getUserMedia` 권한
  프롬프트/캡처는 아직 미확인(명세 §5 최대 위험 지점). **S2S 모드로 별도 확인 필요.**

### S-5. Python 사이드카 — ✅ spawn PASS, [종료-정리 사람 검증]
- `src-tauri/src/lib.rs`: 앱 setup 에서 `uv run python -m app.main` (repo root, dev.bat 와 동일) spawn,
  `RunEvent::Exit` 및 트레이 "종료" 에서 `child.kill()` → 좀비 방지.
- **spawn 실측**: `tauri dev` 로그 `backend spawned pid=35720` → `/health` =
  `{"status":"ok","adapters":{"llm":true,"stt":true,"tts":true}}`. Tauri 가 띄운 백엔드가 전 모델 정상 로드.
- **정리 실측 ✅**: 앱 종료 직후 `/health` 무응답 + `tasklist` 에 python/uv **없음** → 좀비 프로세스 0.

### S-6. Native toast — 🟡 표시 PASS / 클릭 동작 [후속]
- **표시 ✅**(사용자): 트레이 "알림 테스트" → Windows toast 정상 표시.
- **클릭 무반응**: toast 클릭 시 앱 포커스 안 됨. → Tauri notification plugin 의 기본 `.show()` 는
  Windows 에서 클릭→액션 라우팅을 안 함. 능동 알림의 **핵심(표시)은 성립**, 클릭→세션진입은
  후속 과제(notification action/딥링크 배선, ADR-027 구현 phase). **no-go 아님.**

### S-7. 트레이 상주 — ✅ 상주 PASS / 종료-정리 버그 [수정함]
- **상주 ✅**(사용자): 창 X → 트레이 유지, 메뉴 복원 정상.
- **버그 발견·수정**: 트레이 "종료" 후 작업관리자에 **python 잔존**(사용자가 강제종료).
  - 원인: `uv run python` 은 `uv`(자식) → `python`(손자) 구조. `child.kill()` 이 uv 만 죽이고
    python(포트+VRAM 점유) 고아화. (내 초기 자동 체크의 "python 없음"은 PID 착시였음.)
  - 수정: `lib.rs` `kill_backend()` — Windows `taskkill /PID <id> /T /F` 로 **트리 전체 종료**,
    정리 3지점(트레이 종료·`RunEvent::Exit`·`stop_backend`) 일원화. 컴파일 exit 0.
  - 재검증 필요: 다음 실행 때 "종료" 후 python 잔존 0 (사용자 눈).

### S-8. on-demand 모델 로드/언로드 + VRAM 반환 — ✅ PASS (실측)
`scripts/spike_vram_lifecycle.py`, `config.llm.model=qwen3.5:9b`(측정 후 qwen3:8b 복원), device 32GB.

| 단계 | device used (MiB) | 비고 |
|---|---|---|
| baseline | 1615 | 모델 0 |
| STT 로드 | 3599 | +1984 (faster-whisper) |
| TTS 로드 | 8207 | +4608 (faster-qwen3-tts, torch 4303) |
| 추론 1회씩 | 8247 | STT 31ms, TTS first chunk 375ms |
| **언로드 +1s** | **1883** | **STT+TTS 즉시 반환**, 잔여 268 MiB (CUDA 컨텍스트 수준) |

- **LLM(Ollama, 별도 프로세스)**: 조합 스냅샷엔 미반영(프로세스 분리 타이밍). **단독 측정으로 확정** —
  `qwen3.5:9b` 로드 시 **5.6GB(100% GPU)**, `ollama stop`/`keep_alive=0` 후 **완전 반환**(9115→2211 MiB, `ollama ps` empty).
- **동시 세션 추정 = STT 2.0 + TTS 4.6 + LLM 5.6 ≈ 12.2GB** → **16GB 베이스라인에 여유**(ADR-030 "~13GB" 검증).
- **세션 밖 VRAM ≈ baseline** — 게임/타 앱 공존 가능(ADR-030 핵심 요구 충족).
- **콜드스타트(STT+TTS+LLM ready) = 30,046ms** — 대부분 **TTS CUDA graph 캡처**(warmup 6.5s + predictor/talker graph). 사용자 체감 "세션 시작 느림"과 일치 → ADR-030 "코치 준비 중" UX 필수.
- 부수: faster-qwen3-tts 가 `SoX not found` 경고 출력하나 **동작 무영향**(optional 경로).

## 1-1. 기타 관찰 (스파이크 게이트 밖 — v3 코칭 로직, webview 무관)

> 사용자 실사용 중 발견. **Tauri 채택 여부와 무관**(브라우저에서도 동일)하므로 게이트가 아니며,
> v4 구현 phase 백로그로 이관. 다만 회고 4-3(기록) 위해 박제.

- **세션 시작 느림**: "처음 안 되는 줄 알았는데 한참 기다리니 됨." → 콜드스타트 체감.
  ADR-030 의 "코치 준비 중" UX 필요성을 사용자 체감으로 재확인(S-8 와 연결).
- **음성탭 전환 지연**: 모드 전환이 한참 안 되다 갑자기 됨. → ws 재연결(`resolveUrl` disconnect→reconnect) 지연 의심. v4 UI phase 점검.
- **코치 멈춤 버튼 무동작**: 인터럽트/정지 미작동. v3 기능 버그 — v4 phase 에서 처리.

## 2. 콜드스타트 실측

- **STT+TTS+LLM(qwen3.5:9b) ready = 30,046 ms** (RTX 5090, baseline GPU ~1.6GB).
  - 내역(감각): faster-whisper ~2s, faster-qwen3-tts warmup+CUDA graph ~13s, Ollama 9b 로드 ~수 초.
  - 함의: ADR-030 의 "세션 시작 시 로드 + '코치 준비 중' UX" 가 필수(0초 콜드스타트 불가).
  - **이 콜드스타트는 v3 에도 있었음** — ADR-015 는 백엔드 시작 시 1회 로드 후 24h 상주라 *세션마다는*
    0초였을 뿐. ADR-030 이 "게임 VRAM 공존"을 위해 이 비용을 *세션마다*로 옮기는 의도된 트레이드오프.
  - **결정(2026-06-10)**: ADR-030 **유지**, 30s 는 **병렬 로드 + 앱-열림 prewarm + '준비 중' UX** 로 완화.
    상세는 ADR-030 §결정(콜드스타트 흡수). 실측·구현은 v4 구현 phase.

## 3. Go / No-Go 결정 — **GO** (2026-06-10 사용자 결정)

머신·사람 검증에서 **테스트한 모든 게이트가 통과**했고, native 채택의 핵심 가정(빌드·웹뷰 재사용·WS·사이드카·알림·트레이·VRAM lifecycle)이 전부 성립한다. v2 가 무너진 빌드/패키징 함정은 Tauri(Rust+webview2)에서 재현되지 않았다.

| 게이트 | 판정 |
|---|---|
| S-1 빌드/설치본 | ✅ PASS (dev+release, 설치본 2.0/3.0MB) |
| S-2 React 웹뷰 재사용 | ✅ PASS (실세션, 재작성 0) |
| S-3 WS 라운드트립 | ✅ PASS |
| S-4 오디오 출력 | ✅ PASS / **마이크 입력 = 미검증(보류)** |
| S-5 사이드카 spawn/정리 | ✅ spawn PASS, 정리 버그 **수정 완료**(재확인 1회 필요) |
| S-6 native toast | ✅ 표시 PASS / 클릭→포커스 후속 |
| S-7 트레이 상주 | ✅ PASS |
| S-8 VRAM lifecycle | ✅ PASS (반환 확인, 12.2GB, 콜드 30s) |

**GO 결정 근거**: 테스트한 7개 게이트 전부 통과. 유일 미검증인 **S-4 마이크 입력(webview2 getUserMedia)** 은 (a) 오디오 *출력* 은 이미 통과, (b) 마이크 입력 실패는 대개 webview2 권한/설정(미디어 권한 핸들러) 문제로 **fix 가능 영역**이지 native 아키텍처 자체를 막는 근본 장벽이 아님 → **GO 차단 사유로 보지 않고 후속 fix 항목으로 이월**(사용자 결정 2026-06-10).

### GO 후속 작업 (회고 4-4 "그만하기" — 더 파지 않음)
1. ADR-031(Tauri)·027(알림)·030(lifecycle) **Proposed → Accepted**, ADR-010/015 를 `Superseded by` 로 갱신, CLAUDE.md §3 의 "데스크탑 패키징 금지" 조항 수정. (004→029 는 이미 완료.)
2. v4 구현 phase 인덱스 작성. native 항목 우선순위: 콜드스타트 UX, 트레이 스케줄러, toast 클릭→세션 딥링크.
3. **후속 fix(비차단)**: S-4 마이크 입력(webview2 미디어 권한) + S-5 종료-정리 재확인(수정본). 집에서 마이크 가능할 때.

### 잔여 리스크 (GO 후에도 닫아야 할 것)
- S-4 마이크가 webview2 에서 끝내 불가면 → 음성 입력 모드(S2S/C2S) 영향. 우선 webview2 권한 설정으로 해결 시도, 정 안되면 그때 재평가(설계 전면 후퇴보다는 입력 경로 대안 검토).

## 4. 코드 산출물 (이 phase)
- `ui/src-tauri/**` — Tauri 2 셸(tray, notification, 사이드카 spawn/tree-kill).
- `ui/vite.config.ts` — `server.watch.ignored` (Tauri+Vite EBUSY 회피), `clearScreen:false`.
- `ui/package.json` — `@tauri-apps/cli|api` devDep.
- `scripts/spike_vram_lifecycle.py` — S-8 측정.
- 환경: Rust 1.59→1.96 (rustup stable).

## 5. 다음 세션 런북 (집에서 — 마이크 필요)

> 목표: **S-4 마이크 입력 + S-5 종료-정리(수정본)** 검증 → 통과 시 **완전 GO**.
> 준비 상태: S-5 tree-kill 수정은 이미 컴파일됨(`cargo build` exit 0). **재빌드 불필요**.

1. `cd ui && pnpm tauri dev` — 창 뜨고 백엔드 사이드카 자동 기동. `/health` ok 까지 **~30s 콜드스타트**(정상, 모델 로드).
2. **S-4 마이크(★ 최대 위험)**: S2S 음성 모드 전환 → 마이크 권한 프롬프트 → 허용 → 발화 → STT 인식 + 코치 음성 응답 확인.
   - 안 행복한 경로: 권한 **거부** 시 UI 안내가 뜨는지.
3. **S-5 종료-정리**: 트레이 우클릭 → "종료" → 작업관리자에서 **python/uv 완전 소멸** 확인(이전 고아 버그 재발 X).
4. **F3 겸사 — 9b 코칭 회귀**: C2C 채팅으로 운동 제안 받아 `propose_set`·확답 흐름이 qwen3.5:9b 에서도 정상인지(ADR-013 회귀).

- **통과 시** → ADR-031/027/030 Accepted 승격 + 010/015 Superseded + CLAUDE.md §3 수정 → v4 구현 phase 인덱스.
- **S-4 실패 시** → no-go 경로: PWA 후퇴 + ADR-010 유지(§3 참조).
