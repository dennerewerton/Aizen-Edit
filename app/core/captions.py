"""Build output-timeline SRT captions from local transcript timestamps."""
from pathlib import Path


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def build_srt(transcript: dict, segments: list[dict], output: Path, mode: str) -> int:
    """Write text only where a transcript phrase overlaps selected EDL segments."""
    if mode in {"none", "Nenhuma"}:
        output.unlink(missing_ok=True); return 0
    entries, index, offset = [], 1, 0.0
    for edit in segments:
        duration = edit["end"] - edit["start"]
        for phrase in transcript.get("segments", []):
            start, end = float(phrase["start"]), float(phrase["end"])
            if end <= edit["start"] or start >= edit["end"]: continue
            text = phrase.get("text", "").strip()
            if not text: continue
            # Important-only keeps emphatic/reaction-like lines without an LLM.
            if mode in {"important", "Apenas momentos importantes"} and not _important(text): continue
            clipped_start, clipped_end = max(start, edit["start"]), min(end, edit["end"])
            output_start = offset + clipped_start - edit["start"]
            output_end = offset + clipped_end - edit["start"]
            if output_end - output_start < .08: continue
            entries.append(f"{index}\n{srt_timestamp(output_start)} --> {srt_timestamp(output_end)}\n{text}\n")
            index += 1
        offset += duration
    if not entries:
        output.unlink(missing_ok=True)
        return 0
    output.write_text("\n".join(entries), encoding="utf-8")
    return len(entries)


def _important(text: str) -> bool:
    lower = text.lower()
    return "!" in text or "?" in text or any(token in lower for token in ("kkk", "haha", "nossa", "meu deus", "noob", "lixo", "perdeu"))
