"""Safe GitHub Release update checks for the installed Windows app."""
from __future__ import annotations

import json
import hashlib
import subprocess
import tempfile
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .version import VERSION


def _version(value: str) -> tuple[int, ...]:
    cleaned = value.strip().lstrip("vV").split("-")[0]
    try:
        return tuple(int(part) for part in cleaned.split("."))
    except ValueError:
        return (0,)


def check_for_update(settings: dict) -> dict:
    repository = str(settings.get("github_repository", "")).strip()
    if not repository:
        return {"configured": False, "current_version": VERSION, "available": False}
    url = f"https://api.github.com/repos/{repository}/releases/latest"
    try:
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Aizen-Auto-Editor"})
        with urlopen(request, timeout=5) as response:
            release = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 404:
            return {"configured": True, "current_version": VERSION, "available": False, "status": "Nenhuma atualização publicada ainda."}
        return {"configured": True, "current_version": VERSION, "available": False, "status": "Não foi possível verificar atualizações agora."}
    except Exception:
        return {"configured": True, "current_version": VERSION, "available": False, "status": "Não foi possível verificar atualizações agora."}
    latest = str(release.get("tag_name", "")).lstrip("v")
    asset_name = str(settings.get("installer_asset", ""))
    asset = next((item for item in release.get("assets", []) if item.get("name") == asset_name), None)
    available = bool(asset and _version(latest) > _version(VERSION))
    return {"configured": True, "current_version": VERSION, "latest_version": latest or VERSION, "available": available, "status": "Atualização disponível." if available else "Seu Aizen Auto Editor está atualizado.", "download_url": asset.get("browser_download_url") if available else None, "sha256": str(asset.get("digest", "")).removeprefix("sha256:") if available else None}


def _download_installer(download_url: str, expected_sha256: str | None = None) -> Path:
    destination = Path(tempfile.gettempdir()) / "AizenAutoEditor" / Path(download_url.split("?")[0]).name
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = Request(download_url, headers={"User-Agent": "Aizen-Auto-Editor"})
    digest = hashlib.sha256()
    with urlopen(request, timeout=30) as response, temporary.open("wb") as output:
        while block := response.read(1024 * 1024):
            digest.update(block)
            output.write(block)
    if expected_sha256 and digest.hexdigest().lower() != expected_sha256.lower():
        temporary.unlink(missing_ok=True)
        raise ValueError("A verificação de segurança da atualização falhou.")
    temporary.replace(destination)
    return destination


def _run_installer(installer: Path) -> None:
    subprocess.Popen([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"], close_fds=True)


def install_update(download_url: str, expected_sha256: str | None = None) -> None:
    """Download a verified release installer outside the app, then run it silently."""

    def work() -> None:
        _run_installer(_download_installer(download_url, expected_sha256))

    Thread(target=work, daemon=True).start()


def install_update_before_start(settings: dict) -> bool:
    """Apply a verified GitHub update before the window is created."""
    if not settings.get("auto_install", False):
        return False
    update = check_for_update(settings)
    if not update.get("available"):
        return False
    try:
        _run_installer(_download_installer(update["download_url"], update.get("sha256")))
        return True
    except Exception:
        return False
