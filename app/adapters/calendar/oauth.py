"""OAuth2 Desktop 흐름 + 토큰 안전 저장 (ADR-022 §9-1).

최초 1회 브라우저 동의로 refresh token 을 받아 **OS 자격증명 저장소(keyring =
Windows Credential Manager)** 에 저장한다 — 평문 파일 금지(ADR-022 부정 항목). 이후
호출은 저장된 토큰을 자동 갱신(refresh)해서 쓴다.

단일 사용자 본인 계정 1개(ADR-002)라 다계정 분기·account 선택 코드는 없다. 토큰 키도
고정 단일 키(``_TOKEN_KEY``)다.

google 라이브러리는 모듈 import 시점이 아니라 함수 안에서 lazy import 한다 — 라이브러리
미설치/미연동 환경에서도 이 모듈 import 자체는 깨지지 않게(상위 계층의 graceful degrade).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    # 타입 힌트 전용 — 런타임 top-level google import 회피(미설치/미연동 degrade 보존).
    from google.oauth2.credentials import Credentials

# Google Calendar read/write. 단일 사용자 본인 캘린더만 — 최소 권한.
SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar"]

# keyring 의 (service, username) 좌표. 단일 사용자라 고정 단일 키.
_KEYRING_SERVICE = "localfit-ai"
_TOKEN_KEY = "gcal_token"


class CalendarAuthError(Exception):
    """OAuth/토큰 관련 복구 불가 오류 — 상위에서 사용자 안내로 변환(ADR-018)."""


def _load_token_json() -> str | None:
    """keyring 에서 저장된 토큰 JSON. 없거나 백엔드 오류면 None(미연동 취급)."""
    try:
        import keyring

        return keyring.get_password(_KEYRING_SERVICE, _TOKEN_KEY)
    except Exception as e:  # noqa: BLE001 — keyring 백엔드 부재 등 → 미연동으로 degrade
        logger.warning("keyring read failed (treating as disconnected): {}", e)
        return None


def _save_token_json(token_json: str) -> None:
    """토큰 JSON 을 keyring 에 저장(평문 파일 X)."""
    import keyring

    keyring.set_password(_KEYRING_SERVICE, _TOKEN_KEY, token_json)


def disconnect() -> None:
    """저장된 토큰 삭제 — 연동 해제. 없으면 조용히 통과."""
    try:
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, _TOKEN_KEY)
        logger.info("gcal token cleared from keyring")
    except Exception as e:  # noqa: BLE001 — 이미 없거나 백엔드 부재
        logger.debug("gcal disconnect: nothing to clear or backend error: {}", e)


def _credentials_from_store() -> Credentials | None:
    """저장된 토큰으로 ``Credentials`` 복원 + 만료 시 자동 갱신. 미연동/실패면 None.

    갱신에 성공하면 갱신된 토큰을 다시 저장한다(refresh token 회전 대비).
    """
    token_json = _load_token_json()
    if not token_json:
        return None
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_info(_safe_json(token_json), SCOPES)
    except Exception as e:  # noqa: BLE001 — 손상된 토큰
        logger.error("stored gcal token is invalid: {}", e)
        return None

    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token_json(creds.to_json())
            logger.info("gcal token refreshed")
            return creds
        except Exception as e:  # noqa: BLE001 — 오프라인/취소된 동의 등
            logger.error("gcal token refresh failed (offline or revoked): {}", e)
            return None
    return None


def _safe_json(raw: str) -> dict:
    import json

    return json.loads(raw)


def is_connected() -> bool:
    """저장된 토큰으로 유효한 자격증명을 만들 수 있으면 True(미연동/오프라인이면 False).

    네트워크 없이도 토큰이 아직 유효하면 True. 만료됐는데 갱신이 안 되면(오프라인)
    False — 호출부는 로컬 fallback 으로 degrade 한다(ADR-022 안 행복한 경로).
    """
    return _credentials_from_store() is not None


def get_credentials() -> Credentials | None:
    """현재 유효한 ``Credentials`` 또는 None(미연동/갱신 실패). 클라이언트 빌드에 쓴다."""
    return _credentials_from_store()


def run_desktop_flow(credentials_path: str | Path) -> bool:
    """OAuth2 Desktop 동의 흐름을 1회 실행 → 토큰 저장. 성공 True.

    로컬 브라우저를 열어 사용자 동의를 받는다(``run_local_server``, 127.0.0.1 콜백 —
    ADR-002 외부 노출 0). client secret JSON 이 없으면 ``CalendarAuthError``.
    데스크탑 셸(Tauri)/로컬에서 사용자가 명시적으로 "연동" 을 눌렀을 때만 호출한다.
    """
    path = Path(credentials_path)
    if not path.exists():
        raise CalendarAuthError(
            f"OAuth client secret not found: {path} — "
            "Google Cloud Console 에서 OAuth Desktop client 를 발급해 이 경로에 두세요."
        )
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
        # port=0 → 임의 빈 포트의 127.0.0.1 콜백. 동의 후 브라우저가 자동 리다이렉트.
        creds = flow.run_local_server(port=0)
    except Exception as e:  # noqa: BLE001 — 사용자가 동의 취소/네트워크 오류
        logger.error("OAuth desktop flow failed: {}", e)
        raise CalendarAuthError(f"OAuth 동의에 실패했습니다: {e}") from e

    _save_token_json(creds.to_json())
    logger.info("gcal connected — token stored in keyring")
    return True
