from pathlib import Path
from .probe import probe_video


def verify_render(path: Path, expected_fps: float, expected_duration: float | None = None) -> dict:
    if not path.exists() or path.stat().st_size == 0: return {"ok": False, "errors": ["Arquivo de saída vazio ou ausente."]}
    info = probe_video(path); errors = []
    if abs(info["fps"] - expected_fps) > 0.02: errors.append(f"FPS incorreto: {info['fps']} (esperado {expected_fps})")
    if not info["audio"]: errors.append("Saída sem áudio.")
    if expected_duration is not None and abs(info["duration"] - expected_duration) > .75:
        errors.append(f"Duração incompatível: {info['duration']:.2f}s (esperado aproximadamente {expected_duration:.2f}s)")
    return {"ok": not errors, "errors": errors, "info": info}


def expected_edl_duration(edl: dict) -> float:
    """Expected output time after the deliberately duration-changing effects."""
    total = 0.0
    for segment in edl.get("segments", []):
        duration = float(segment["end"]) - float(segment["start"])
        kinds = {effect.get("type") for effect in segment.get("effects", [])}
        if "slow_motion" in kinds:
            duration *= 1.5
        if "freeze_frame" in kinds:
            duration += .5
        total += duration
    return total
