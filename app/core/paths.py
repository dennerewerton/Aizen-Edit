import sys
from pathlib import Path

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
WORKSPACE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else ROOT
PROJECTS = WORKSPACE / "projects"
CONFIG = ROOT / "config"
ASSETS = WORKSPACE / "assets"
