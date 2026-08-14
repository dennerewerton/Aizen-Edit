"""Declarative, opt-in effects attached to timeline events.

The renderer deliberately ignores an effect until a reviewed highlight explicitly
contains it. This prevents random visual changes in the MVP.
"""

SUPPORTED_EFFECTS = {"punch_zoom", "webcam_punch_in", "freeze_frame", "slow_motion", "text"}


def validate_effect(effect: dict) -> dict:
    kind = effect.get("type")
    if kind not in SUPPORTED_EFFECTS:
        raise ValueError(f"Efeito não suportado: {kind}")
    start, end = float(effect.get("start", 0)), float(effect.get("end", 0))
    if end <= start:
        raise ValueError("O efeito precisa ter duração positiva.")
    return {**effect, "type": kind, "start": start, "end": end}

