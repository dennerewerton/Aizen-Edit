import subprocess
from pathlib import Path


def create_thumbnail(video: Path, timestamp: float, output: Path) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["ffmpeg", "-y", "-ss", str(max(0, timestamp)), "-i", str(video), "-frames:v", "1", "-vf", "scale=320:-2", str(output)], capture_output=True, text=True)
    return result.returncode == 0 and output.exists()

