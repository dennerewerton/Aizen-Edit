from pathlib import Path
from .probe import probe_video


def verify_render(path: Path, expected_fps: float) -> dict:
    if not path.exists() or path.stat().st_size == 0: return {"ok": False, "errors": ["Arquivo de saída vazio ou ausente."]}
    info = probe_video(path); errors = []
    if abs(info["fps"] - expected_fps) > 0.02: errors.append(f"FPS incorreto: {info['fps']} (esperado {expected_fps})")
    if not info["audio"]: errors.append("Saída sem áudio.")
    return {"ok": not errors, "errors": errors, "info": info}

