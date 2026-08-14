def make_edl(source: str, highlights: list[dict], fps_rational: str, subtitles: str | None = None, target_duration: float | None = None) -> dict:
    selected = [highlight for highlight in highlights if highlight.get("selected", True)]
    if target_duration and target_duration > 0:
        picked, used = [], 0.0
        for highlight in sorted(selected, key=lambda item: item["score"], reverse=True):
            duration = max(0, highlight["end"] - highlight["start"])
            if not picked or used + duration <= target_duration:
                picked.append(highlight); used += duration
        selected = picked
    segments = [{"source": source, "start": h["start"], "end": h["end"], "reason": h["reason"], "score": h["score"], "highlight_id": h["id"], "effects": h.get("effects", [])} for h in sorted(selected, key=lambda item: item["start"])]
    return {"version": 1, "fps_rational": fps_rational, "segments": segments, "subtitles": subtitles, "total_duration": edl_duration(segments)}


def edl_duration(segments: list[dict]) -> float:
    return round(sum(max(0, s["end"] - s["start"]) for s in segments), 3)
