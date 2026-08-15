import os
import shutil
import sys
from pathlib import Path

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
WORKSPACE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", WORKSPACE)) / "Aizen Auto Editor" if getattr(sys, "frozen", False) else WORKSPACE
PROJECTS = DATA_ROOT / "projects"
CONFIG = ROOT / "config"
ASSETS = DATA_ROOT / "assets"


def ensure_user_data() -> None:
    """Keep writable projects and user assets outside Program Files."""
    PROJECTS.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    bundled_assets = ROOT / "assets"
    if bundled_assets.is_dir():
        for item in bundled_assets.iterdir():
            target = ASSETS / item.name
            if item.resolve() == target.resolve():
                continue
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            elif not target.exists():
                shutil.copy2(item, target)


ensure_user_data()
