"""MeloTTSClient unit tests — config validation only (GPU/model load skipped)."""

from unittest.mock import MagicMock

import pytest


class TestMeloTTSClientConfigValidation:
    def _make_config(self, melo: dict | None) -> MagicMock:
        cfg = MagicMock()
        cfg.tts.melo = melo if melo is not None else {}
        return cfg

    def test_missing_melo_section_raises(self) -> None:
        from app.adapters.tts.melo_client import MeloTTSClient

        cfg = self._make_config(None)
        with pytest.raises(ValueError, match="tts.melo"):
            MeloTTSClient(cfg)
