import subprocess
from pathlib import Path


def analyze_audio(path: Path, duration: float, step: float = 1.0) -> list[dict]:
    """Use FFmpeg's streamed RMS metadata; falls back to no signal when audio is absent."""
    # `reset` counts decoded audio frames. About 50 AAC frames is roughly one
    # second, keeping long recordings bounded instead of emitting every frame.
    reset_frames = max(1, round(50 * step))
    command = ["ffmpeg", "-hide_banner", "-i", str(path), "-af", f"astats=metadata=1:reset={reset_frames},ametadata=print:key=lavfi.astats.Overall.RMS_level", "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True)
    values = []
    for line in result.stderr.splitlines():
        if "RMS_level=" in line:
            try: values.append(float(line.rsplit("=", 1)[1]))
            except ValueError: pass
    if not values: return [{"time": round(t, 3), "energy": 0.0} for t in _times(duration, step)]
    floor, ceiling = min(values), max(values)
    scale = max(ceiling - floor, 1.0)
    return [{"time": round(i * step, 3), "energy": round((v - floor) / scale, 4)} for i, v in enumerate(values)]


def _times(duration: float, step: float):
    t = 0.0
    while t < duration:
        yield t; t += step
