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
    scored = []
    for point in visual:
        sound = audio_by_time.get(round(point["time"]), 0.0)
        hud = point.get("hud", {})
        scored.append(.6 * point["motion"] + .3 * sound + .1 * max(hud.values(), default=0.0))
    # Recordings, capture cards and microphones have very different ranges. Use
    # the upper activity band of this recording while keeping a conservative
    # floor so a uniformly quiet menu is not mislabeled as combat.
    ordered = sorted(scored)
    upper_band = ordered[min(len(ordered) - 1, int(len(ordered) * .82))] if ordered else threshold
    adaptive_threshold = min(threshold, max(threshold * .45, upper_band))
    events = []
    for point, combat in zip(visual, scored):
        sound = audio_by_time.get(round(point["time"]), 0.0)
        hud = point.get("hud", {})
        visual_confirmation = point["motion"] >= .075 or max(hud.values(), default=0.0) >= .12
        if combat >= adaptive_threshold and visual_confirmation:
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


def save_debug_frames(path: Path, events: list[dict], directory: Path, maximum: int = 30) -> list[str]:
    """Save a small, inspectable sample of visual detector candidates.

    These are diagnostic artifacts only: labels say *candidate* and never turn a
    heuristic into a confirmed kill/death event.
    """
    candidates = [event for event in events if event["type"] in {"combat", "kill_candidate", "death_candidate"}]
    if not candidates:
        return []
    directory.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(path)); saved = []
    try:
        for index, event in enumerate(candidates[:maximum], 1):
            moment = (float(event["start"]) + float(event["end"])) / 2
            capture.set(cv2.CAP_PROP_POS_MSEC, moment * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            label = f"{event['type']} candidate | {moment:.1f}s | conf {event['confidence']:.2f}"
            cv2.rectangle(frame, (12, 12), (min(frame.shape[1] - 12, 760), 58), (0, 0, 0), -1)
            cv2.putText(frame, label, (22, 43), cv2.FONT_HERSHEY_SIMPLEX, .62, (0, 220, 255), 2, cv2.LINE_AA)
            filename = f"{index:03}_{event['type']}_{moment:.1f}s.jpg"
            if cv2.imwrite(str(directory / filename), frame):
                saved.append(filename)
    finally:
        capture.release()
    return saved


def build_activity_score(visual: list[dict], audio: list[dict], transcript: dict) -> list[dict]:
    """Join lightweight per-second signals without decoding all video frames."""
    audio_by_time = {round(point["time"]): point["energy"] for point in audio}
    result = []
    for point in visual:
        time = point["time"]
        speech = any(float(segment["start"]) <= time <= float(segment["end"]) for segment in transcript.get("segments", []))
        sound = audio_by_time.get(round(time), 0.0)
        activity = min(1.0, .5 * point["motion"] + .3 * sound + .2 * float(speech))
        item = {"time": time, "activity": round(activity, 4), "motion": point["motion"], "audio": sound, "speech": float(speech)}
        if point.get("hud"): item["hud"] = max(point["hud"].values(), default=0.0)
        result.append(item)
    return result


def detect_dead_zones(activity: list[dict], settings: dict) -> list[dict]:
    """Detect sustained inactivity using image, audio, speech and calibrated HUD.

    Silence alone is deliberately insufficient: a silent fight with movement or
    HUD changes must never become a dead zone.
    """
    if not activity: return []
    ordered = sorted(activity, key=lambda point: point["time"])
    gaps = [b["time"] - a["time"] for a, b in zip(ordered, ordered[1:]) if b["time"] > a["time"]]
    sample = sorted(gaps)[len(gaps) // 2] if gaps else 1.0
    maximum_gap = sample * 1.5
    runs, current = [], []
    for point in ordered:
        quiet = (point.get("activity", 1) <= settings["max_activity"] and point.get("motion", 1) <= settings["max_motion"] and point.get("audio", 1) <= settings["max_audio"] and point.get("speech", 0) == 0 and point.get("hud", 0) <= settings.get("max_hud", .12))
        contiguous = not current or point["time"] - current[-1]["time"] <= maximum_gap
        if quiet and contiguous: current.append(point)
        else:
            if current: runs.append(current)
            current = [point] if quiet else []
    if current: runs.append(current)
    zones = []
    for run in runs:
        start, end = run[0]["time"], run[-1]["time"] + sample
        if end - start < settings["minimum_seconds"]: continue
        mean_activity = sum(point["activity"] for point in run) / len(run)
        zones.append({"start": round(start, 3), "end": round(end, 3), "type": "dead_zone", "confidence": round(1 - mean_activity, 3), "signals": {"motion": round(sum(point["motion"] for point in run) / len(run), 3), "audio": round(sum(point["audio"] for point in run) / len(run), 3), "speech": 0.0}, "reason": "baixa atividade visual e sonora, sem fala ou mudança de HUD"})
    return zones
