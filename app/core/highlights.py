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


def group_events(events: list[dict], gap: float = 5.0, dead_zones: list[dict] | None = None, max_span: float | None = None) -> list[list[dict]]:
    interesting = [e for e in events if e["type"] not in {"idle", "dead_zone"}]
    groups: list[list[dict]] = []
    for event in sorted(interesting, key=lambda x: x["start"]):
        separated_by_dead_zone = groups and any(zone["start"] < event["start"] and zone["end"] > groups[-1][-1]["end"] for zone in (dead_zones or []))
        exceeds_maximum = groups and max_span and event["end"] - groups[-1][0]["start"] > max_span
        if groups and not separated_by_dead_zone and not exceeds_maximum and event["start"] - groups[-1][-1]["end"] <= gap: groups[-1].append(event)
        else: groups.append([event])
    return groups


def build_highlights(events: list[dict], weights: dict, settings: dict, duration: float | None = None, dead_zones: list[dict] | None = None) -> list[dict]:
    result = []
    pre_context, post_context = settings["pre_context_seconds"], settings["post_context_seconds"]
    if duration is not None and duration <= settings.get("short_video_max_seconds", 0):
        pre_context = min(pre_context, max(.25, duration * settings.get("short_video_context_ratio", .12)))
        post_context = min(post_context, max(.25, duration * settings.get("short_video_context_ratio", .12)))
    for group in group_events(events, settings["merge_gap_seconds"], dead_zones, settings.get("max_highlight_event_span_seconds")):
        regular_scores = [score_event(event, weights) for event in group if event["type"] != "conversation"]
        conversation_scores = sorted((score_event(event, weights) for event in group if event["type"] == "conversation"), reverse=True)
        # Several ordinary sentences must not manufacture a highlight merely by
        # accumulating score. Strong reactions and gameplay events stay uncapped.
        score = sum(regular_scores) + sum(conversation_scores[:settings.get("max_conversation_events", 3)])
        action_types = {"combat", "combat_peak", "round_end", "kill", "kill_candidate", "death", "death_candidate", "reaction", "trash_talk"}
        minimum = settings["minimum_score"] if any(event["type"] in action_types for event in group) else settings.get("conversation_minimum_score", settings["minimum_score"])
        if score < minimum: continue
        types = list(dict.fromkeys(event["type"] for event in group))
        group_pre_context = pre_context
        if "round_end" in types:
            group_pre_context = max(group_pre_context, settings.get("round_end_pre_context_seconds", 5.0))
        start = max(0, group[0]["start"] - group_pre_context)
        end = group[-1]["end"] + post_context
        before = [zone["end"] for zone in (dead_zones or []) if start < zone["end"] <= group[0]["start"]]
        after = [zone["start"] for zone in (dead_zones or []) if group[-1]["end"] <= zone["start"] < end]
        if before: start = max(start, max(before))
        if after: end = min(end, min(after))
        if duration is not None: end = min(end, duration)
        if end <= start: continue
        result.append({"id": f"highlight-{len(result)+1:03}", "start": start, "end": end, "score": round(score, 2), "events": types, "reason": " + ".join(types), "selected": True, "favorite": False})
    # Context before/after adjacent highlights can overlap. Split that overlap at
    # its midpoint so the same frames are never rendered twice in the final cut.
    for previous, current in zip(result, result[1:]):
        if current["start"] < previous["end"]:
            boundary = round((current["start"] + previous["end"]) / 2, 3)
            previous["end"], current["start"] = boundary, boundary
    return sorted(result, key=lambda x: x["score"], reverse=True)
