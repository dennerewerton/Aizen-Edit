"""Declarative, opt-in effects attached to timeline events.

The renderer deliberately ignores an effect until a reviewed highlight explicitly
contains it. This prevents random visual changes in the MVP.
"""

SUPPORTED_EFFECTS = {"punch_zoom", "webcam_punch_in", "freeze_frame", "slow_motion", "text"}


def validate_effect(effect: dict) -> dict:
    kind = effect.get("type")
    if kind not in SUPPORTED_EFFECTS:
        raise ValueError(f"Efeito não suportado: {kind}")
    start, end = float(effect.get("start", 0)), float(effect.get("end", 0))
    if end <= start:
        raise ValueError("O efeito precisa ter duração positiva.")
    return {**effect, "type": kind, "start": start, "end": end}


def filters_for_effects(effects: list[dict], layout: dict | None = None, output_size: tuple[int, int] | None = None) -> tuple[list[str], list[str]]:
    """Return FFmpeg video/audio filters for opt-in effects on one EDL segment."""
    video, audio = [], []
    target = f"{output_size[0]}:{output_size[1]}" if output_size else "iw:ih"
    for effect in effects:
        kind = effect["type"]
        if kind == "punch_zoom":
            # Implemented through an overlay graph below, because crop itself
            # has no timeline support in the Windows FFmpeg build.
            continue
        elif kind == "webcam_punch_in":
            region = (layout or {}).get("regions", {}).get("webcam")
            if not region: raise ValueError("Configure a webcam antes de usar Webcam Punch-In.")
            continue
        elif kind == "freeze_frame":
            video.append("tpad=stop_mode=clone:stop_duration=0.5")
            audio.append("apad=pad_dur=0.5")
        elif kind == "slow_motion":
            video.append("setpts=1.5*PTS")
            audio.append("atempo=0.666667")
        elif kind == "text":
            message = str(effect.get("text", ""))
            if not message: raise ValueError("O efeito de texto precisa de uma mensagem.")
            safe = message.replace("'", r"\'").replace(":", r"\:")
            video.append(f"drawtext=text='{safe}':x=(w-text_w)/2:y=h*0.12:fontsize=h/18:fontcolor=white:borderw=3:bordercolor=black:enable='between(t,{effect['start']},{effect['end']})'")
    return video, audio


def windowed_video_filtergraph(effects: list[dict], layout: dict | None, fps: str, preview_height: int | None) -> str | None:
    """Build a timeline-compatible graph for crop-based effects.

    FFmpeg's crop filter cannot be enabled only for a time interval.  We create
    an enlarged branch and overlay it on the untouched branch only in the
    selected interval instead.
    """
    crop_effects = [effect for effect in effects if effect["type"] in {"punch_zoom", "webcam_punch_in"}]
    if not crop_effects:
        return None
    graph, current = [], "[0:v]"
    for index, effect in enumerate(crop_effects):
        base, branch, zoomed, output = f"[base{index}]", f"[branch{index}]", f"[zoomed{index}]", f"[video{index}]"
        graph.append(f"{current}split=2{base}{branch}")
        if effect["type"] == "punch_zoom":
            graph.append(f"{branch}crop=trunc(iw/1.12/2)*2:trunc(ih/1.12/2)*2:(iw-ow)/2:(ih-oh),scale=trunc(iw*1.12/2)*2:trunc(ih*1.12/2)*2{zoomed}")
        else:
            region = (layout or {}).get("regions", {}).get("webcam")
            if not region:
                raise ValueError("Configure a webcam antes de usar Webcam Punch-In.")
            graph.append(f"{branch}crop=trunc(iw*{region['width']}/2)*2:trunc(ih*{region['height']}/2)*2:iw*{region['x']}:ih*{region['y']},scale=trunc(iw/{region['width']}/2)*2:trunc(ih/{region['height']}/2)*2{zoomed}")
        graph.append(f"{base}{zoomed}overlay=0:0:enable='between(t,{effect['start']},{effect['end']})'{output}")
        current = output
    tail = f"fps={fps}" + (f",scale=-2:{preview_height}" if preview_height else "")
    graph.append(f"{current}{tail}[vout]")
    return ";".join(graph)
