from pathlib import Path

import cv2


def normalized_to_pixels(region: dict, width: int, height: int) -> dict:
    return {"x": round(region["x"] * width), "y": round(region["y"] * height), "width": round(region["width"] * width), "height": round(region["height"] * height)}


def analyze_gameplay(path: Path, sample_seconds: float = 1.0) -> list[dict]:
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_step = max(1, round(fps * sample_seconds))
    index, previous, scores = 0, None, []
    while True:
        ok, frame = cap.read()
        if not ok: break
        if index % frame_step == 0:
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90))
            motion = 0.0 if previous is None else float(cv2.absdiff(small, previous).mean() / 255.0)
            scores.append({"time": round(index / fps, 3), "motion": round(min(motion * 7, 1.0), 4)})
            previous = small
        index += 1
    cap.release()
    return scores


def detect_events(visual: list[dict], audio: list[dict], threshold: float = 0.55) -> list[dict]:
    audio_by_time = {round(item["time"]): item["energy"] for item in audio}
    events = []
    for point in visual:
        sound = audio_by_time.get(round(point["time"]), 0.0)
        combat = 0.65 * point["motion"] + 0.35 * sound
        if combat >= threshold:
            events.append({"start": point["time"], "end": point["time"] + 1.0, "type": "combat", "confidence": round(combat, 3), "signals": {"motion": point["motion"], "audio": sound, "speech": 0.0}})
        elif combat < 0.08:
            events.append({"start": point["time"], "end": point["time"] + 1.0, "type": "idle", "confidence": round(1 - combat, 3), "signals": {"motion": point["motion"], "audio": sound, "speech": 0.0}})
    return events

