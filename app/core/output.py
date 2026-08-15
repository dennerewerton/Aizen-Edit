"""Output format and normalized crop settings for horizontal and vertical edits."""

FORMATS = {"16:9", "9:16"}
VERTICAL_MODES = {"full", "top_split"}


def default_output_settings() -> dict:
    return {
        "output_format": "16:9",
        "vertical_mode": "full",
        "crops": {
            "gameplay": {"x": .219, "y": 0.0, "width": .562, "height": 1.0},
            "webcam": {"x": .10, "y": .05, "width": .80, "height": .45},
        },
    }


def _crop(value: dict, fallback: dict) -> dict:
    candidate = value if isinstance(value, dict) else fallback
    keys = {"x", "y", "width", "height"}
    if set(candidate) != keys:
        raise ValueError("Cada quadro de corte precisa ter x, y, largura e altura.")
    result = {key: float(candidate[key]) for key in keys}
    if any(number < 0 or number > 1 for number in result.values()) or result["width"] <= 0 or result["height"] <= 0:
        raise ValueError("O quadro de corte precisa ficar dentro do vídeo.")
    if result["x"] + result["width"] > 1 or result["y"] + result["height"] > 1:
        raise ValueError("O quadro de corte ultrapassa o vídeo.")
    return result


def normalize_output_settings(value: dict | None) -> dict:
    defaults = default_output_settings()
    value = value or {}
    output_format = str(value.get("output_format", defaults["output_format"]))
    vertical_mode = str(value.get("vertical_mode", defaults["vertical_mode"]))
    if output_format not in FORMATS:
        raise ValueError("Formato de vídeo inválido.")
    if vertical_mode not in VERTICAL_MODES:
        raise ValueError("Modo vertical inválido.")
    supplied = value.get("crops", {})
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict):
        raise ValueError("Cortes inválidos.")
    return {
        "output_format": output_format,
        "vertical_mode": vertical_mode,
        "crops": {name: _crop(supplied.get(name), default) for name, default in defaults["crops"].items()},
    }


def output_size(source: dict, settings: dict) -> tuple[int, int]:
    if settings.get("output_format") == "9:16":
        return 1080, 1920
    return int(source["width"]), int(source["height"])
