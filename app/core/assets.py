"""Safe discovery of optional, user-owned local assets."""
from pathlib import Path

from .paths import ASSETS

SFX_DIRECTORY = ASSETS / "sfx"
SFX_EXTENSIONS = {".wav", ".mp3", ".aac", ".m4a", ".ogg", ".flac"}


def list_sfx() -> list[str]:
    SFX_DIRECTORY.mkdir(parents=True, exist_ok=True)
    return sorted(item.name for item in SFX_DIRECTORY.iterdir() if item.is_file() and item.suffix.lower() in SFX_EXTENSIONS)


def sfx_path(name: str | None) -> Path | None:
    if not name: return None
    candidate = (SFX_DIRECTORY / Path(name).name).resolve()
    if candidate.parent != SFX_DIRECTORY.resolve() or not candidate.is_file() or candidate.suffix.lower() not in SFX_EXTENSIONS:
        raise ValueError("SFX local inválido. Escolha um arquivo em assets/sfx.")
    return candidate
