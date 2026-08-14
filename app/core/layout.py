"""Normalized Free Fire layout configuration, independent of resolution."""

from pathlib import Path

from .project import read_json, write_json

REGIONS = {"webcam", "scoreboard", "kill_feed", "hp", "minimap", "gameplay_center"}


def load_layout(project: Path) -> dict:
    return read_json(project / "layout.json", {"regions": {}})


def validate_layout(layout: dict) -> dict:
    regions = layout.get("regions", {})
    invalid = set(regions) - REGIONS
    if invalid:
        raise ValueError(f"Regiões inválidas: {', '.join(sorted(invalid))}")
    checked = {}
    for name, region in regions.items():
        required = {"x", "y", "width", "height"}
        if set(region) != required or any(not 0 <= float(region[key]) <= 1 for key in required):
            raise ValueError(f"Coordenadas normalizadas inválidas para {name}.")
        if float(region["x"]) + float(region["width"]) > 1 or float(region["y"]) + float(region["height"]) > 1:
            raise ValueError(f"A região {name} ultrapassa o frame.")
        checked[name] = {key: float(region[key]) for key in required}
    return {"regions": checked}


def save_layout(project: Path, layout: dict) -> dict:
    checked = validate_layout(layout)
    write_json(project / "layout.json", checked)
    return checked

