"""Deterministic transcript signals used when no optional local LLM exists."""
import re

REACTION = re.compile(r"\b(kkk+|haha+|risos?|laugh(?:s|ter)?|grit[oa]|caralh[oa]|nossa|meu deus|eita|vish|boa|toma|capa|matei|derrubei)\b", re.I)
TRASH_TALK = re.compile(r"\b(noob|lixo|ruim|amass[aei]|perdeu|chor[ae]|fraco|bot)\b", re.I)
GAMEPLAY_CALLOUT = re.compile(r"\b(t[aá]\s+ali|ali|atr[aá]s|direita|esquerda|rush|safe|gelo|granada|inimigo|revive|loot|drop|tiro|bala)\b", re.I)


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
            words = re.findall(r"\w+", normalized, re.UNICODE)
            repeated_callout = len(words) >= 2 and len(set(words)) <= max(1, len(words) // 2)
            if REACTION.search(normalized) or text.count("!") >= 2:
                kind, confidence, interest = "reaction", .72, .9
            elif TRASH_TALK.search(normalized):
                kind, confidence, interest = "trash_talk", .68, .85
            elif GAMEPLAY_CALLOUT.search(normalized) and (repeated_callout or len(words) <= 5):
                kind, confidence, interest = "reaction", .62, .8
            elif "?" in text:
                kind, confidence, interest = "conversation", .5, .65
            else:
                confidence = .38 if len(words) >= 9 else (.28 if len(words) >= 5 else .18)
                kind, interest = "conversation", min(.55, .12 + len(words) * .035)
            events.append(_event(start, end, kind, confidence, {"speech": 1.0, "speech_interest": round(interest, 3), "motion": 0.0, "audio": 0.0}, text))
        previous_end = end
    return events


def _event(start: float, end: float, kind: str, confidence: float, signals: dict, text: str | None = None) -> dict:
    result = {"start": round(start, 3), "end": round(end, 3), "type": kind, "confidence": confidence, "signals": signals}
    if text: result["text"] = text
    return result
