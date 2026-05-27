# ADR-014: 프로세스 라이프사이클 및 게임 워크플로우

- **상태**: Accepted
- **작성일**: 2026-05-21
- **관련 ADR**: ADR-003 (Ollama), ADR-011 (동시 실행)

## 컨텍스트

사용자(개발자)는 고사양 게임을 한다. LocalFit이 ~8GB VRAM을 점유한 상태에서 4K 게임 실행 시 충돌 가능하다. 사용자는 **수동 종료/재시작 스크립트**로 대응하기로 결정했다.

또한 Windows 업데이트 재부팅, Python 예외 등으로 백엔드가 죽었을 때 복구 방안이 필요하다.

## 결정

### 1. 운영 스크립트 3종

`scripts/start.bat`:
- Ollama 데몬 시작 (이미 떠 있으면 skip)
- Python 백엔드 시작 (`uvicorn app.main:app --host 127.0.0.1 --port 8000`)
- 두 프로세스의 PID를 `%LOCALAPPDATA%\localfit\run\*.pid`에 기록

`scripts/stop.bat`:
- PID 파일 읽어서 `taskkill /F /PID ...` 또는 `taskkill /F /IM ollama.exe`
- GPU VRAM 완전 회수 확인

`scripts/restart.bat`: stop → start

### 2. 헬스 체크 엔드포인트

`GET /health`:
- 백엔드 상태, LLM·STT·TTS 어댑터 각각 `health()` 호출 결과 반환
- UI에서 1분 주기로 폴링, 실패 시 사용자 알림
- 응답 시간 100ms 이내 유지

### 3. 자동 시작
Windows 시작 프로그램에 `start.bat` 등록 (수동 설정, 사용자 선택). MVP에서는 서비스 등록 안 함.

### 4. 오디오 디바이스 모니터링 (P0 후반)
PRD 2-3절 "헤드폰 빠질 가능성 대비"를 위해 오디오 출력 디바이스 변경 이벤트 핸들러 추가.

### 5. P1 진입 시
폰 PWA에 "백엔드 깨우기" 버튼 → WoL → 부팅 후 자동 실행 → 모델 로딩 대기.

## 결과

### 긍정
- 게임 시 30초 안에 LocalFit 정리 가능
- 헬스 체크로 백엔드 사망 즉시 감지
- 단순 .bat 스크립트로 자동화

### 부정
- Windows 서비스가 아니라 일반 사용자 프로세스 — 로그인 세션 종료 시 함께 종료 (MVP OK)
- PID 파일 stale 문제 — start.bat 시작 시 기존 PID 유효성 검사 필요

## 대안

| 후보 | 탈락 사유 |
|---|---|
| Windows Service로 등록 | NVIDIA GPU 접근 제약, 게임 워크플로우와 충돌 |
| 자동 재시작 (supervisor) | 1인 프로젝트 오버킬 |
| NSSM으로 init화 | 복잡도 ↑ |
| Task Scheduler 기반 | 디버깅 어려움 |
