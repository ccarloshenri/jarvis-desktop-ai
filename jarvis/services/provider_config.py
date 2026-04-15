from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from jarvis.enums.llm_provider import LLMProvider

LOGGER = logging.getLogger(__name__)


def _default_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "JarvisDesktopAI" / "config.json"


class ProviderConfig:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_config_path()

    @property
    def path(self) -> Path:
        return self._path

    def load_active_provider(self) -> LLMProvider | None:
        data = self._read()
        raw = str(data.get("active_provider", "")).strip().lower()
        if not raw:
            return None
        try:
            return LLMProvider(raw)
        except ValueError:
            LOGGER.warning("provider_config_invalid_value", extra={"event_data": {"value": raw}})
            return None

    def save_active_provider(self, provider: LLMProvider) -> None:
        data = self._read()
        data["active_provider"] = provider.value
        self._write(data)

    def clear(self) -> None:
        self._write({})

    def _read(self) -> dict[str, object]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("provider_config_read_failed", extra={"event_data": {"error": str(exc)}})
            return {}

    def _write(self, data: dict[str, object]) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as exc:
            LOGGER.warning("provider_config_write_failed", extra={"event_data": {"error": str(exc)}})
