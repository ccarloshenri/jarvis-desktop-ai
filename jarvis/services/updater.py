from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from jarvis.services.update_checker import ReleaseAsset, ReleaseInfo

LOGGER = logging.getLogger(__name__)


class UpdateError(RuntimeError):
    pass


class Updater:
    """Downloads a release asset and launches the installer.

    Windows strategy:
        1. Pick the first .exe/.msi asset from the release.
        2. Download it to the user's temp directory.
        3. Launch it with `DETACHED_PROCESS` so it survives the app shutdown.
        4. Ask the app to quit — the installer then closes any file locks,
           replaces the binaries, and relaunches Jarvis on completion.

    Make the installer itself (Inno Setup / NSIS) responsible for:
        - waiting for the running Jarvis process to exit,
        - replacing files,
        - restarting Jarvis once done.
    That keeps this Updater trivial and avoids fragile file-swap logic in
    Python."""

    _CHUNK_SIZE = 64 * 1024

    def __init__(self, download_dir: Path | None = None) -> None:
        self._download_dir = download_dir or Path(tempfile.gettempdir()) / "jarvis-updates"
        self._download_dir.mkdir(parents=True, exist_ok=True)

    @property
    def download_dir(self) -> Path:
        return self._download_dir

    def pick_asset(self, release: ReleaseInfo) -> ReleaseAsset:
        asset = release.first_windows_installer()
        if asset is None:
            raise UpdateError(
                f"release {release.tag} has no .exe/.msi asset — "
                f"publish a Windows installer first"
            )
        return asset

    def download_asset(self, asset: ReleaseAsset) -> Path:
        destination = self._download_dir / asset.name
        LOGGER.info(
            "update_download_started",
            extra={"event_data": {"url": asset.download_url, "dest": str(destination)}},
        )
        request = urllib.request.Request(
            asset.download_url,
            headers={"User-Agent": "jarvis-desktop-ai-updater"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30.0) as response, destination.open("wb") as out:
                while chunk := response.read(self._CHUNK_SIZE):
                    out.write(chunk)
        except Exception as exc:
            LOGGER.exception("update_download_failed")
            raise UpdateError(f"failed to download update: {exc}") from exc
        LOGGER.info("update_download_completed", extra={"event_data": {"dest": str(destination)}})
        return destination

    def launch_installer(self, installer_path: Path) -> None:
        if not installer_path.exists():
            raise UpdateError(f"installer not found: {installer_path}")
        if sys.platform != "win32":
            raise UpdateError("automatic install is only supported on Windows")
        LOGGER.info("update_installer_launching", extra={"event_data": {"path": str(installer_path)}})
        creationflags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [str(installer_path)],
            close_fds=True,
            creationflags=creationflags,
            cwd=os.path.dirname(str(installer_path)),
        )

    def apply(self, release: ReleaseInfo) -> Path:
        asset = self.pick_asset(release)
        installer_path = self.download_asset(asset)
        self.launch_installer(installer_path)
        return installer_path
