import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .paths import PROJECTS


def source_signature(path: Path) -> dict:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        digest.update(stream.read(1024 * 1024))
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "head_sha256": digest.hexdigest()}


def project_dir(video: Path) -> Path:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", video.stem).strip("-") or "video"
    identity = hashlib.sha1(str(video.resolve()).encode()).hexdigest()[:8]
    return PROJECTS / f"{clean}-{identity}"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def create_project(video: Path, source: dict, settings: dict) -> Path:
    folder = project_dir(video)
    for name in ("thumbnails", "debug"):
        (folder / name).mkdir(parents=True, exist_ok=True)
    write_json(folder / "source.json", source)
    write_json(folder / "settings.json", settings)
    write_json(folder / "project.json", {"source_signature": source_signature(video), "created_at": datetime.now().isoformat(), "status": "loaded"})
    return folder

