# ADR-016: WSL2 미사용, Windows 네이티브 Python

- **상태**: Accepted
- **작성일**: 2026-05-21
- **관련 ADR**: ADR-014 (게임 워크플로우)

## 컨텍스트

Windows에서 Python AI 개발 시 WSL2 사용이 일반적이지만, NVIDIA GPU 직접 접근, 파일 시스템 성능, IDE 통합 등에서 trade-off가 있다. ADR-014의 게임 워크플로우(수동 스크립트)도 영향을 받는다.

## 결정

**Windows 네이티브 Python**을 사용한다. WSL2는 사용하지 않는다.

근거:
- Ollama, faster-whisper, PyTorch 모두 Windows + CUDA 직접 지원
- 게임 종료/재시작 스크립트가 .bat로 단순화 (WSL이면 wsl.exe 경유 복잡도 ↑)
- 파일 시스템 경로 일관성 (UI/백엔드 모두 Windows 경로)

## 결과

### 긍정
- 단순한 실행 환경 — 디버깅 단순
- 게임 워크플로우 스크립트 단순
- 한국어 경로 처리 직관적

### 부정
- 일부 Linux-only 도구 사용 시 대안 필요 (현재 식별된 것 없음)
- 패키징 시 Windows 종속 — 다른 OS 배포 시 P2에서 별도 작업

## 대안

| 후보 | 탈락 사유 |
|---|---|
| WSL2 (Ubuntu) | GPU 패스스루 오버헤드, .bat ↔ .sh 이중 관리 |
| Docker Desktop | 1인 부담 ↑, GPU 패스스루 복잡 |
| Hyper-V 가상머신 | 오버킬 |
