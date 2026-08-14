from .ranking import score_event


def style_highlight_settings(settings: dict, edit_type: str) -> dict:
    """Adapt context and threshold without scattering editorial policy in web code."""
    result = dict(settings)
    style = str(edit_type).strip().lower()
    if style in {"mais dinâmica", "mais dinamica", "dynamic"}:
        result.update(pre_context_seconds=1.5, post_context_seconds=2.0, merge_gap_seconds=3.0)
    elif style in {"mais natural", "natural"}:
        result.update(pre_context_seconds=4.0, post_context_seconds=4.0, merge_gap_seconds=7.0, minimum_score=max(0, float(settings["minimum_score"]) - .5))
    elif style in {"só melhores momentos", "so melhores momentos", "best"}:
        result.update(pre_context_seconds=2.0, post_context_seconds=2.0, merge_gap_seconds=3.0, minimum_score=float(settings["minimum_score"]) + 2.0)
    return result


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
