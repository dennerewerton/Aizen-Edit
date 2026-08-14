import json
import subprocess
from fractions import Fraction
from pathlib import Path


def _ratio(value: str) -> float:
    return float(Fraction(value)) if value and value != "0/0" else 0.0


def probe_video(path: Path) -> dict:
    command = ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    raw = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    data = json.loads(raw)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    audio = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    if not video:
        raise ValueError("O arquivo não possui stream de vídeo.")
    fps_raw = video.get("avg_frame_rate") or video.get("r_frame_rate", "0/0")
    return {"path": str(path.resolve()), "name": path.name, "duration": float(data["format"].get("duration", 0)),
            "size": path.stat().st_size, "width": int(video["width"]), "height": int(video["height"]),
            "fps": _ratio(fps_raw), "fps_rational": fps_raw, "codec": video.get("codec_name"),
            "bitrate": int(data["format"].get("bit_rate", 0) or 0), "pixel_format": video.get("pix_fmt"),
            "time_base": video.get("time_base"), "audio": None if not audio else {"codec": audio.get("codec_name"), "sample_rate": int(audio.get("sample_rate", 0)), "channels": audio.get("channels")}}

