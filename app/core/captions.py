"""Build output-timeline SRT captions from local transcript timestamps."""
import re
from pathlib import Path


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def build_srt(transcript: dict, segments: list[dict], output: Path, mode: str) -> int:
    """Write short, readable captions for every spoken phrase in selected cuts."""
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
            for chunk_start, chunk_end, chunk_text in _caption_chunks(phrase, edit["start"], edit["end"]):
                output_start = offset + chunk_start - edit["start"]
                output_end = offset + chunk_end - edit["start"]
                if output_end - output_start < .08: continue
                entries.append(f"{index}\n{srt_timestamp(output_start)} --> {srt_timestamp(output_end)}\n{chunk_text}\n")
                index += 1
        offset += duration
    if not entries:
        output.unlink(missing_ok=True)
        return 0
    output.write_text("\n".join(entries), encoding="utf-8")
    return len(entries)


def write_manual_srt(entries: list[dict], output: Path) -> int:
    """Persist user-edited captions on the assembled (not source) timeline."""
    blocks = []
    for index, entry in enumerate(entries, 1):
        start, end = float(entry["start"]), float(entry["end"])
        text = str(entry["text"]).strip()
        if start < 0 or end <= start or not text:
            raise ValueError("Cada legenda precisa ter texto e um intervalo válido.")
        blocks.append(f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{text}\n")
    if not blocks:
        output.unlink(missing_ok=True)
        return 0
    output.write_text("\n".join(blocks), encoding="utf-8")
    return len(blocks)


def read_srt_entries(path: Path) -> list[dict]:
    """Read our compact SRT format back into editable timeline entries."""
    if not path.is_file():
        return []
    entries = []
    for block in path.read_text(encoding="utf-8-sig").strip().split("\n\n"):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            continue
        try:
            start, end = (_parse_timestamp(value) for value in lines[1].split(" --> "))
        except ValueError:
            continue
        entries.append({"start": start, "end": end, "text": "\n".join(lines[2:]).strip()})
    return entries


def _parse_timestamp(value: str) -> float:
    hours, minutes, seconds = value.strip().replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _caption_chunks(phrase: dict, clip_start: float, clip_end: float) -> list[tuple[float, float, str]]:
    phrase_start, phrase_end = max(float(phrase["start"]), clip_start), min(float(phrase["end"]), clip_end)
    tokens = []
    for word in phrase.get("words", []):
        try: start, end = float(word["start"]), float(word["end"])
        except (KeyError, TypeError, ValueError): continue
        if end <= clip_start or start >= clip_end: continue
        text = str(word.get("word", "")).strip()
        if text: tokens.append({"start": max(start, clip_start), "end": min(end, clip_end), "text": text})
    if not tokens:
        words = phrase.get("text", "").strip().split()
        if not words or phrase_end <= phrase_start: return []
        step = (phrase_end - phrase_start) / len(words)
        tokens = [{"start": phrase_start + index * step, "end": phrase_start + (index + 1) * step, "text": word} for index, word in enumerate(words)]
    groups, current = [], []
    for token in tokens:
        projected = " ".join([item["text"] for item in current] + [token["text"]])
        too_long = current and (len(current) >= 5 or len(projected) > 32 or token["end"] - current[0]["start"] > 2.4)
        if too_long: groups.append(current); current = []
        current.append(token)
        if len(current) >= 2 and re.search(r"[.!?]$", token["text"]): groups.append(current); current = []
    if current: groups.append(current)
    result = []
    for group in groups:
        start = group[0]["start"]
        end = min(clip_end, start + 2.4, max(group[-1]["end"], start + .45))
        text = re.sub(r"\s+([,.;:!?])", r"\1", " ".join(item["text"] for item in group))
        result.append((start, end, _two_lines(text)))
    return result


def _two_lines(text: str, width: int = 22) -> str:
    if len(text) <= width: return text
    words = text.split()
    if len(words) < 2: return text
    best = min(range(1, len(words)), key=lambda index: abs(len(" ".join(words[:index])) - len(" ".join(words[index:]))))
    return " ".join(words[:best]) + "\n" + " ".join(words[best:])
