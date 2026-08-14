def make_edl(source: str, highlights: list[dict], fps_rational: str, subtitles: str | None = None, target_duration: float | None = None) -> dict:
    selected = [highlight for highlight in highlights if highlight.get("selected", True)]
    if target_duration and target_duration > 0:
        picked, used = [], 0.0
        for highlight in sorted(selected, key=lambda item: item["score"], reverse=True):
            duration = max(0, highlight["end"] - highlight["start"])
            remaining = target_duration - used
            if remaining <= 0: break
            if duration <= remaining:
                picked.append(highlight); used += duration
            elif remaining >= .5:
                clipped = dict(highlight); middle = (highlight["start"] + highlight["end"]) / 2
                clipped["start"], clipped["end"] = middle - remaining / 2, middle + remaining / 2
                picked.append(clipped); used += remaining
        selected = picked
    segments = [{"source": source, "start": h["start"], "end": h["end"], "reason": h["reason"], "score": h["score"], "highlight_id": h["id"], "effects": h.get("effects", []), "sfx": h.get("sfx")} for h in sorted(selected, key=lambda item: item["start"])]
    return {"version": 1, "fps_rational": fps_rational, "segments": segments, "subtitles": subtitles, "total_duration": edl_duration(segments)}


def edl_duration(segments: list[dict]) -> float:
    return round(sum(max(0, s["end"] - s["start"]) for s in segments), 3)


def automatic_target_duration(source_duration: float, settings: dict) -> float | None:
    """Keep a short source as a short edit instead of expanding it by default."""
    if source_duration <= settings.get("short_video_max_seconds", 0):
        return max(settings.get("short_video_min_target_seconds", 2.0), source_duration * settings.get("short_video_target_ratio", .6))
    return None


def validate_highlights(highlights: list[dict], source_duration: float) -> None:
    for highlight in highlights:
        if not highlight.get("selected", True): continue
        start, end = float(highlight["start"]), float(highlight["end"])
        if start < 0 or end > source_duration + .001 or end <= start:
            raise ValueError(f"Highlight {highlight.get('id', '?')} possui intervalo inválido.")
