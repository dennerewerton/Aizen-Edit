from .ranking import score_event


def group_events(events: list[dict], gap: float = 5.0) -> list[list[dict]]:
    interesting = [e for e in events if e["type"] != "idle"]
    groups: list[list[dict]] = []
    for event in sorted(interesting, key=lambda x: x["start"]):
        if groups and event["start"] - groups[-1][-1]["end"] <= gap: groups[-1].append(event)
        else: groups.append([event])
    return groups


def build_highlights(events: list[dict], weights: dict, settings: dict, duration: float | None = None) -> list[dict]:
    result = []
    for group in group_events(events, settings["merge_gap_seconds"]):
        score = sum(score_event(event, weights) for event in group)
        if score < settings["minimum_score"]: continue
        types = list(dict.fromkeys(event["type"] for event in group))
        start = max(0, group[0]["start"] - settings["pre_context_seconds"])
        end = group[-1]["end"] + settings["post_context_seconds"]
        if duration is not None: end = min(end, duration)
        if end <= start: continue
        result.append({"id": f"highlight-{len(result)+1:03}", "start": start, "end": end, "score": round(score, 2), "events": types, "reason": " + ".join(types), "selected": True, "favorite": False})
    return sorted(result, key=lambda x: x["score"], reverse=True)
