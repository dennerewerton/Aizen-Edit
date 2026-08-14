def score_event(event: dict, weights: dict) -> float:
    signals = event.get("signals", {})
    return round(weights.get(event["type"], 0) * event.get("confidence", 0) + weights.get("motion", 0) * signals.get("motion", 0) + weights.get("audio", 0) * signals.get("audio", 0) + weights.get("confidence", 0) * event.get("confidence", 0), 3)

