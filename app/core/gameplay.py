from pathlib import Path

import cv2


def normalized_to_pixels(region: dict, width: int, height: int) -> dict:
    return {"x": round(region["x"] * width), "y": round(region["y"] * height), "width": round(region["width"] * width), "height": round(region["height"] * height)}


def analyze_gameplay(path: Path, sample_seconds: float = 1.0, layout: dict | None = None) -> list[dict]:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_step = max(1, round(fps * sample_seconds))
    index, previous, previous_rois, scores = 0, None, {}, []
    while True:
        ok, frame = cap.read()
        if not ok: break
        if index % frame_step == 0:
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90))
            motion = 0.0 if previous is None else float(cv2.absdiff(small, previous).mean() / 255.0)
            point = {"time": round(index / fps, 3), "motion": round(min(motion * 7, 1.0), 4)}
            hud, current_rois = _hud_changes(small, previous_rois, (layout or {}).get("regions", {}))
            if hud: point["hud"] = hud
            previous_rois = current_rois
            scores.append(point)
            previous = small
        index += 1
    cap.release()
    return scores


def _hud_changes(frame, previous: dict, regions: dict) -> tuple[dict, dict]:
    changes, current = {}, {}
    height, width = frame.shape
    for name in ("kill_feed", "hp"):
        region = regions.get(name)
        if not region: continue
        x, y = int(region["x"] * width), int(region["y"] * height)
        w, h = max(1, int(region["width"] * width)), max(1, int(region["height"] * height))
        roi = frame[y:min(height, y + h), x:min(width, x + w)]
        if roi.size == 0: continue
        current[name] = roi
        if name in previous and previous[name].shape == roi.shape:
            changes[name] = round(min(float(cv2.absdiff(roi, previous[name]).mean() / 255.0) * 10, 1.0), 4)
    return changes, current


def detect_events(visual: list[dict], audio: list[dict], threshold: float = 0.55) -> list[dict]:
    audio_by_time = {round(item["time"]): item["energy"] for item in audio}
    events = []
    for point in visual:
        sound = audio_by_time.get(round(point["time"]), 0.0)
        combat = 0.65 * point["motion"] + 0.35 * sound
        hud = point.get("hud", {})
        if combat >= threshold:
            events.append({"start": point["time"], "end": point["time"] + 1.0, "type": "combat", "confidence": round(combat, 3), "signals": {"motion": point["motion"], "audio": sound, "speech": 0.0, "kill_feed": hud.get("kill_feed", 0.0), "hp": hud.get("hp", 0.0)}})
        elif combat < 0.08:
            events.append({"start": point["time"], "end": point["time"] + 1.0, "type": "idle", "confidence": round(1 - combat, 3), "signals": {"motion": point["motion"], "audio": sound, "speech": 0.0, "kill_feed": hud.get("kill_feed", 0.0), "hp": hud.get("hp", 0.0)}})
    return events


def detect_outcome_candidates(events: list[dict]) -> list[dict]:
    """Conservative v1 candidates: calibrated HUD change is mandatory."""
    candidates = []
    for event in events:
        if event["type"] != "combat": continue
        signals = event["signals"]
        kill_feed, hp = signals.get("kill_feed", 0.0), signals.get("hp", 0.0)
        if kill_feed >= .15 and signals["motion"] >= .2 and signals["audio"] >= .15:
            confidence = min(1.0, .45 * kill_feed + .3 * signals["motion"] + .25 * signals["audio"])
            candidates.append({"start": event["start"], "end": event["end"], "type": "kill_candidate", "confidence": round(confidence, 3), "signals": signals, "reason": "mudança no kill feed durante combate"})
        if hp >= .18 and signals["motion"] >= .15 and signals["audio"] >= .1:
            confidence = min(1.0, .5 * hp + .25 * signals["motion"] + .25 * signals["audio"])
            candidates.append({"start": event["start"], "end": event["end"], "type": "death_candidate", "confidence": round(confidence, 3), "signals": signals, "reason": "mudança forte de HP durante combate"})
    return candidates


def build_activity_score(visual: list[dict], audio: list[dict], transcript: dict) -> list[dict]:
    """Join lightweight per-second signals without decoding all video frames."""
    audio_by_time = {round(point["time"]): point["energy"] for point in audio}
    result = []
    for point in visual:
        time = point["time"]
        speech = any(float(segment["start"]) <= time <= float(segment["end"]) for segment in transcript.get("segments", []))
        sound = audio_by_time.get(round(time), 0.0)
        activity = min(1.0, .5 * point["motion"] + .3 * sound + .2 * float(speech))
        result.append({"time": time, "activity": round(activity, 4), "motion": point["motion"], "audio": sound, "speech": float(speech)})
    return result
