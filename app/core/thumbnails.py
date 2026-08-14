import subprocess
from pathlib import Path


def create_frame(video: Path, timestamp: float, output: Path, width: int = 320) -> bool:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["ffmpeg", "-y", "-ss", str(max(0, timestamp)), "-i", str(video), "-frames:v", "1", "-vf", f"scale={width}:-2", str(output)], capture_output=True, text=True)
    return result.returncode == 0 and output.exists()


def create_thumbnail(video: Path, timestamp: float, output: Path) -> bool:
    return create_frame(video, timestamp, output, 320)
