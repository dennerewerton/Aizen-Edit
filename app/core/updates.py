"""Safe GitHub Release update checks for the installed Windows app."""
from __future__ import annotations

import json
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
    return {"configured": True, "current_version": VERSION, "latest_version": latest or VERSION, "available": available, "status": "Atualização disponível." if available else "Seu Aizen Auto Editor está atualizado.", "download_url": asset.get("browser_download_url") if available else None}


def install_update(download_url: str) -> None:
    """Download the signed release installer outside the app, then run it silently."""
    destination = Path(tempfile.gettempdir()) / "AizenAutoEditor" / Path(download_url.split("?")[0]).name
    destination.parent.mkdir(parents=True, exist_ok=True)

    def work() -> None:
        request = Request(download_url, headers={"User-Agent": "Aizen-Auto-Editor"})
        with urlopen(request, timeout=30) as response:
            destination.write_bytes(response.read())
        subprocess.Popen([str(destination), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"], close_fds=True)

    Thread(target=work, daemon=True).start()
