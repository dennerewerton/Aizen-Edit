def make_edl(source: str, highlights: list[dict], fps_rational: str) -> dict:
    segments = [{"source": source, "start": h["start"], "end": h["end"], "reason": h["reason"], "score": h["score"], "highlight_id": h["id"]} for h in highlights if h.get("selected", True)]
    return {"version": 1, "fps_rational": fps_rational, "segments": segments, "total_duration": edl_duration(segments)}


def edl_duration(segments: list[dict]) -> float:
    return round(sum(max(0, s["end"] - s["start"]) for s in segments), 3)

