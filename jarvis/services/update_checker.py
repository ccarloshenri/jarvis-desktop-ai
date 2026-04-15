from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    name: str
    body: str
    html_url: str
    assets: tuple[ReleaseAsset, ...] = field(default_factory=tuple)

    def first_windows_installer(self) -> ReleaseAsset | None:
        for asset in self.assets:
            lower = asset.name.lower()
            if lower.endswith((".exe", ".msi")):
                return asset
        return None


_SEMVER_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _parse_version(value: str) -> tuple[int, int, int] | None:
    if not value:
        return None
    cleaned = value.strip().lstrip("vV")
    match = _SEMVER_RE.match(cleaned)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return (int(major), int(minor or 0), int(patch or 0))


def is_newer(remote: str, local: str) -> bool:
    remote_tuple = _parse_version(remote)
    local_tuple = _parse_version(local)
    if remote_tuple is None or local_tuple is None:
        return False
    return remote_tuple > local_tuple


class UpdateChecker:
    """Queries GitHub's `releases/latest` endpoint and returns a ReleaseInfo
    when the remote version is newer than the local one.

    Network errors are swallowed and logged — the app must continue to start
    even when offline or when GitHub is unreachable."""

    _API_TEMPLATE = "https://api.github.com/repos/{repo}/releases/latest"
    _TIMEOUT_SECONDS = 6.0

    def __init__(self, repo: str, current_version: str) -> None:
        if "/" not in repo:
            raise ValueError(f"repo must be 'owner/name', got: {repo!r}")
        self._repo = repo
        self._current_version = current_version

    @property
    def current_version(self) -> str:
        return self._current_version

    def check(self) -> ReleaseInfo | None:
        payload = self._fetch_latest_release()
        if payload is None:
            return None
        release = self._parse_release(payload)
        if release is None:
            return None
        if not is_newer(release.version, self._current_version):
            LOGGER.info(
                "update_check_up_to_date",
                extra={"event_data": {"local": self._current_version, "remote": release.version}},
            )
            return None
        LOGGER.info(
            "update_available",
            extra={"event_data": {"local": self._current_version, "remote": release.version}},
        )
        return release

    def _fetch_latest_release(self) -> dict | None:
        url = self._API_TEMPLATE.format(repo=self._repo)
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "jarvis-desktop-ai-update-checker",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            LOGGER.warning(
                "update_check_http_error",
                extra={"event_data": {"status": exc.code, "reason": str(exc.reason)}},
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            LOGGER.info(
                "update_check_network_unavailable",
                extra={"event_data": {"error": str(exc)}},
            )
        except (json.JSONDecodeError, ValueError) as exc:
            LOGGER.warning("update_check_invalid_payload", extra={"event_data": {"error": str(exc)}})
        return None

    @staticmethod
    def _parse_release(payload: dict) -> ReleaseInfo | None:
        tag = (payload.get("tag_name") or "").strip()
        version = tag.lstrip("vV") if tag else ""
        if not version:
            return None
        assets_raw = payload.get("assets") or []
        assets = tuple(
            ReleaseAsset(
                name=item.get("name", ""),
                download_url=item.get("browser_download_url", ""),
                size=int(item.get("size") or 0),
            )
            for item in assets_raw
            if item.get("browser_download_url")
        )
        return ReleaseInfo(
            version=version,
            tag=tag,
            name=payload.get("name") or tag,
            body=payload.get("body") or "",
            html_url=payload.get("html_url") or "",
            assets=assets,
        )
