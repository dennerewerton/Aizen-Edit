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


def append_log(folder: Path, message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    with (folder / "log.txt").open("a", encoding="utf-8") as output:
        output.write(f"[{timestamp}] {message}\n")


def create_project(video: Path, source: dict, settings: dict) -> Path:
    folder = project_dir(video)
    for name in ("thumbnails", "debug"):
        (folder / name).mkdir(parents=True, exist_ok=True)
    signature = source_signature(video)
    previous = read_json(folder / "project.json", {})
    if previous.get("source_signature") not in (None, signature):
        # Reusing a path for a modified recording must not reuse old analytics.
        # Layout is intentionally retained because it belongs to the creator.
        generated = ("transcript.json", "transcript.txt", "audio_features.json", "visual_features.json", "activity_score.json", "gameplay_events.json", "highlights.json", "edl.json", "preview.mp4", "final.mp4", "preview_verify.json", "final_verify.json", "feedback.jsonl")
        for name in generated:
            (folder / name).unlink(missing_ok=True)
        for thumbnail in (folder / "thumbnails").glob("*"):
            if thumbnail.is_file(): thumbnail.unlink()
    write_json(folder / "source.json", source)
    write_json(folder / "settings.json", settings)
    write_json(folder / "project.json", {"source_signature": signature, "created_at": previous.get("created_at", datetime.now().isoformat()), "updated_at": datetime.now().isoformat(), "status": "loaded"})
    append_log(folder, f"Vídeo carregado: {video.name} ({source.get('fps_rational', '?')} FPS)")
    return folder


def recent_projects(limit: int = 12) -> list[dict]:
    """Return lightweight resumable project metadata without reading media."""
    if not PROJECTS.exists(): return []
    items = []
    for project in PROJECTS.iterdir():
        if not project.is_dir(): continue
        source = read_json(project / "source.json")
        state = read_json(project / "project.json", {})
        if source:
            items.append({"project": str(project.resolve()), "name": source.get("name", project.name), "updated_at": state.get("updated_at", ""), "has_highlights": (project / "highlights.json").exists(), "has_edl": (project / "edl.json").exists()})
    return sorted(items, key=lambda item: item["updated_at"], reverse=True)[:limit]
