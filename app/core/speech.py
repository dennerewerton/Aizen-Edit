"""Deterministic transcript signals used when no optional local LLM exists."""
import re

REACTION = re.compile(r"\b(kkk+|haha+|risos?|laugh(?:s|ter)?|grit[oa]|caralh[oa]|nossa|meu deus)\b", re.I)
TRASH_TALK = re.compile(r"\b(noob|lixo|ruim|amass[aei]|perdeu|chor[ae]|fraco|bot)\b", re.I)


def transcript_events(transcript: dict, pause_seconds: float = 1.5) -> list[dict]:
    events: list[dict] = []
    previous_end = None
    for segment in transcript.get("segments", []):
        start, end = float(segment["start"]), float(segment["end"])
        text = segment.get("text", "").strip()
        if previous_end is not None and start - previous_end >= pause_seconds:
            events.append(_event(previous_end, start, "idle", min(1, (start - previous_end) / 5), {"speech": 0.0}))
        if text:
            normalized = text.lower()
            if REACTION.search(normalized) or text.count("!") >= 2:
                kind, confidence = "reaction", .72
            elif TRASH_TALK.search(normalized):
                kind, confidence = "trash_talk", .68
            elif "?" in text:
                kind, confidence = "conversation", .48
            else:
                kind, confidence = "conversation", .35
            events.append(_event(start, end, kind, confidence, {"speech": 1.0, "motion": 0.0, "audio": 0.0}, text))
        previous_end = end
    return events


def _event(start: float, end: float, kind: str, confidence: float, signals: dict, text: str | None = None) -> dict:
    result = {"start": round(start, 3), "end": round(end, 3), "type": kind, "confidence": confidence, "signals": signals}
    if text: result["text"] = text
    return result
