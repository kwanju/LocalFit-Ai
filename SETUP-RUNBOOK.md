# LocalFit AI — 셋업 런북 (Path A: Windows 네이티브)

> Claude Code를 처음 쓰는 사람을 위한 A→Z 가이드.
> 환경 결정: **Windows 10 네이티브 + RTX 5090, WSL2 미사용 (ADR-016).**
> 이 문서는 "Claude Code 사용법"이고, 제품 요구사항은 `docs/prd-v3.2.md`, 설계는 `docs/architecture/adr/` 가 단일 진실 소스다.

---

## 0. 먼저 이해할 것 — AI가 둘이다

- **Claude Code** = 클라우드의 Claude. 내 터미널에서 *코드를 대신 짜주는 개발 도구*. 인터넷으로 Anthropic에 붙는다.
- **Ollama + Qwen/Gemma** = 내가 만드는 앱이 실행 중에 쓰는 *로컬 LLM*. 내 5090 GPU에서 돈다.

→ **Claude Code가 코드를 짜고, 그 코드가 Ollama를 호출한다.** 둘은 별개다.

전체 흐름: 환경 세팅 → Claude Code 설치 → **Phase 0(내가 직접 환경 검증)** → Phase 1A~6(Claude Code가 한 단계씩 구현, 내가 검토·커밋).

---

## 1. 준비물

- **Claude 구독** — Claude Code는 클라우드 Claude를 쓴다. Pro($20/월)가 실질적 진입점. 사용량이 많으면 상위 티어 고려.
- **Git for Windows** — Claude Code가 Windows에서 Git Bash 위에서 동작하므로 필수. https://git-scm.com 에서 설치.
- **uv / pnpm / Ollama** — 앱이 쓰는 도구. Phase 0 문서에 설치 명령이 있으니 그때 깔아도 된다.

---

## 2. Claude Code 설치 (Windows 네이티브)

PowerShell을 열고(관리자 권한 불필요):

```powershell
irm https://claude.ai/install.ps1 | iex
```

확인:

```powershell
claude --version   # 버전이 뜨면 성공
claude doctor      # 환경 점검
```

`claude` 가 인식 안 되면(`not recognized`): 터미널을 껐다 새로 연다. 그래도 안 되면 `%USERPROFILE%\.local\bin` 을 PATH에 추가.
(npm 설치 방식은 비권장이니 쓰지 말 것.)

---

## 3. 이 폴더 쓰기 + Git 시작

1. 이 폴더(`localfit-ai`)를 작업 위치에 둔다 (예: `C:\dev\localfit-ai`).
2. Git Bash 또는 PowerShell에서:

```bash
cd /c/dev/localfit-ai      # PowerShell이면: cd C:\dev\localfit-ai
git init
git add .
git commit -m "chore: 하네스 + PRD v3.2 + Claude Code 설정 초기화"
```

> `.gitignore` 는 Phase 1A에서 생성된다. 그 전 첫 커밋엔 전체가 들어가지만 문제없다.

---

## 4. Claude Code 첫 실행 & 기본 조작

프로젝트 폴더 **안에서** 실행해야 `CLAUDE.md` 를 자동으로 읽는다.

```bash
cd /c/dev/localfit-ai
claude
```

처음엔 브라우저 로그인이 뜬다(구독 계정). 그다음 한국어로 그냥 말하면 된다.

초보 필수 조작:

| 동작 | 방법 |
|---|---|
| **Plan Mode (강력 추천)** | `Shift+Tab` 으로 전환. 코드 짜기 전에 *계획부터* 세우게 함 |
| **권한 승인** | 파일 수정/명령 실행 전 물어봄 — **처음엔 전부 눈으로 보고 승인** |
| 명령어 목록 | `/help` |
| 컨텍스트 비우기 | `/clear` (작업이 바뀔 때) |
| 컨텍스트 압축 | `/compact` (한 작업이 길어질 때) |
| 사용량 확인 | `/cost` |
| 종료 | `/exit` 또는 Ctrl+C 두 번 |

**첫 연습(안전):** "CLAUDE.md와 docs 구조를 읽고 이 프로젝트가 뭘 만드는지 3줄로 요약해줘." → 하네스를 제대로 읽는지 확인.

---

## 5. Phase 0 — 이건 Claude Code가 아니라 "내가 직접"

`docs/agent-tasks/phase-0-poc.md` 대로 5090 + CUDA + Ollama + Qwen 한국어 응답을 **내 손으로** 검증(1~3시간). 하드웨어 검증이라 Claude Code가 대신 못 한다.

- 통과 기준: 5090 인식, Qwen 한국어 응답 자연스러움, Python에서 ollama 호출 성공.
- **모델 태그 주의:** `qwen3.5:9b`(대화 기본), `qwen3.5:4b`(경량 fallback), `gemma4:e4b`(Gemma 태그는 미검증) 가 실제 Ollama 레지스트리 이름과 다를 수 있다. 반드시 `ollama list` 로 확인. 다르면 Phase 0 문서의 "실패 시" 절차대로 처리하고, 그 갱신은 Claude Code에 시키면 된다: *"Phase 0에서 실제 모델 태그가 X였어. ADR-004와 013을 이에 맞게 갱신해줘."*

---

## 6. Phase 1A부터 — 에이전트 루프 (슬래시 커맨드로 간단하게)

각 Phase마다 이 5단계를 반복한다. 미리 만들어 둔 슬래시 커맨드를 쓰면 한 줄이면 된다.

1. **새 세션 정리** — `/clear`
2. **작업 실행** — 예: `/phase-1a` (입력창에 `/` 치면 목록이 뜬다)
3. **계획 검토** — Plan Mode면 계획을 먼저 보여준다. ADR/PRD에 맞는지 확인 후 실행 승인.
4. **검증** — `/review` (변경분을 코드리뷰 체크리스트로 자가 점검)
5. **커밋** — 통과 시 `feat: phase-1a scaffold` 식으로. 그리고 다음 Phase.

**진행 순서(의존성 — 반드시 지킬 것):**

```
/phase-1a → /phase-1b → (/phase-2a · /phase-2b · /phase-2c 병렬 가능) →
/phase-3 → /phase-4a → /phase-4b → /phase-5 → /phase-6
```

> 사용 가능한 커맨드: `/phase-1a`~`/phase-6`, `/review`. (Phase 0은 수동이라 커맨드 없음.)

---

## 7. 토큰 절약 습관 (이미 설정된 것 + 내가 할 것)

**이미 설정됨 (`.claude/settings.json`):**
- 무거운 경로(`.venv`, `node_modules`, `models`, `*.gguf`, `*.db`, `ui/dist`)를 읽기 차단 → 컨텍스트 폭증 방지.
- `.env`/`secrets` 읽기 차단 → 비밀정보 보호.
- 안전한 읽기·git 조회·pytest 는 자동 허용 → 승인 클릭 줄임.

**내가 들일 습관:**
- **Phase가 바뀌면 `/clear`** — 가장 효과 큰 절약(+품질 향상). 컨텍스트가 길어지면 비용도, 품질도 나빠진다.
- 한 세션에 한 작업만. (이 하네스는 "한 Phase = 한 세션"이라 이미 잘 맞음.)
- 프롬프트는 구체적으로. 모호하면 토큰만 낭비된다.
- 모델은 일상 작업엔 Sonnet, 어려운 설계에만 Opus. (`/model` 로 전환)

> 참고: 예전엔 `.claudeignore` 를 권했지만, 지금은 `settings.json` 의 `permissions.deny` 로 처리하는 게 공식 방식이라 그쪽에 넣어 뒀다.

---

## 8. (Phase 1A 이후) 아키텍처 규칙 자동 검사 — 선택

CLAUDE.md 6번 "방향성 규칙"(`core`는 `adapters`/FastAPI/Ollama를 import하지 않음)을 사람이 매번 확인하기 번거로우면, Phase 1A로 `app/` 구조가 생긴 뒤 아래 테스트를 추가하라고 Claude Code에 시키면 된다. 모델 지시보다 확실한 강제 장치다.

> Claude Code에 시킬 말:
> *"`tests/test_architecture.py` 를 만들어줘. `app/core/` 아래 모든 .py 파일이 `app.adapters`, `fastapi`, `ollama`, `faster_whisper`, `sqlmodel` 을 import하지 않는지 검사하는 pytest 테스트. import 발견 시 어느 파일·어느 줄인지 알려주고 실패하게. 파일을 실제 import하지 말고 텍스트로 스캔해서 오탐을 줄여라."*

이러면 `uv run pytest` 돌릴 때마다 아키텍처 규칙이 자동으로 지켜진다.

---

## 9. 막히면 / 안전수칙

- **한 번에 한 Phase만.** "전부 다 만들어줘"는 통제 불능을 부른다. 13~17일은 원래 한 단계씩 가는 일정이다.
- **승인 전에 diff를 눈으로 본다.** 안 보고 누르는 습관이 들면 나중에 전부 뜯게 된다.
- **커밋을 자주.** Phase마다 커밋하면 잘못돼도 git으로 되돌릴 수 있다.
- 설계와 충돌하거나 모호하면 Claude가 멈추고 묻도록 CLAUDE.md에 이미 지시돼 있다. 멈추면 직접 판단해서 답해준다.
