import subprocess
import time

from .effects import filters_for_effects, windowed_video_filtergraph
from .assets import sfx_path
from pathlib import Path


def encoder(use_hardware: bool) -> str:
    return "h264_amf" if use_hardware else "libx264"


def encoder_options(video_encoder: str, cpu_threads: int = 0) -> list[str]:
    options = ["-c:v", video_encoder]
    if video_encoder == "h264_amf":
        options += ["-quality", "quality", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"]
    else:
        options += ["-crf", "18", "-preset", "medium"]
    if cpu_threads > 0: options += ["-threads", str(cpu_threads)]
    return options


def segment_command(source: Path, segment: dict, output: Path, fps: str, preview_height: int | None = None, has_audio: bool = True, layout: dict | None = None, output_size: tuple[int, int] | None = None, video_encoder: str = "libx264", cpu_threads: int = 0) -> list[str]:
    duration = segment["end"] - segment["start"]
    fade = min(0.03, duration / 4)
    effect_video, effect_audio = filters_for_effects(segment.get("effects", []), layout, output_size)
    filters = effect_video + [f"fps={fps}"]
    if preview_height: filters.append(f"scale=-2:{preview_height}")
    graph = windowed_video_filtergraph(segment.get("effects", []), layout, fps, preview_height)
    has_window_graph = graph is not None
    sfx = sfx_path(segment.get("sfx"))
    command = ["ffmpeg", "-y", "-ss", str(segment["start"]), "-i", str(source)]
    if sfx: command += ["-i", str(sfx)]
    command += ["-t", str(duration)]
    audio_filters = effect_audio + [f"afade=t=in:st=0:d={fade}", f"afade=t=out:st={max(0, duration-fade)}:d={fade}"] if has_audio else []
    if sfx and not has_audio: raise ValueError("SFX exige um vídeo de origem com áudio.")
    if sfx:
        audio_graph = f"[0:a]{','.join(audio_filters)}[source_audio];[source_audio][1:a]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        graph = ";".join(part for part in (graph, audio_graph) if part)
    if graph:
        command += ["-filter_complex", graph, "-map", "[vout]" if has_window_graph else "0:v:0", "-map", "[aout]" if sfx else "0:a?"]
        if not has_window_graph: command += ["-vf", ",".join(filters)]
    else: command += ["-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(filters)]
    if has_audio and not sfx:
        command += ["-af", ",".join(audio_filters), "-c:a", "aac"]
    elif sfx: command += ["-c:a", "aac"]
    command += encoder_options(video_encoder, cpu_threads)
    command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    return command


def _run(command: list[str], cancelled=None, cpu_threads: int = 0, filter_threads: int = 0) -> None:
    # FFmpeg writes progress continually to stderr. Keeping that pipe unread
    # deadlocks a long render once Windows' pipe buffer fills.
    original = command
    command = [original[0], "-hide_banner", "-loglevel", "error"]
    if cpu_threads > 0: command += ["-threads", str(cpu_threads)]
    if filter_threads > 0: command += ["-filter_threads", str(filter_threads)]
    command += original[1:]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    while process.poll() is None:
        if cancelled and cancelled.is_set():
            process.terminate(); process.wait(timeout=5)
            raise RuntimeError("Renderização cancelada.")
        time.sleep(.1)
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, command)


def subtitle_style(layout: dict | None, output_size: tuple[int, int] | None) -> str:
    """Choose one of three safe caption bands from calibrated HUD/webcam areas."""
    regions = (layout or {}).get("regions", {}).values()
    bands = [("top", .14), ("middle", .50), ("bottom", .84)]
    def obstruction(y: float) -> float:
        return sum(max(0.0, min(y + .09, r.get("y", 0) + r.get("height", 0)) - max(y - .09, r.get("y", 0))) for r in regions)
    # Bottom remains the preferred conventional location when it is equally safe.
    name, y = min(bands, key=lambda band: (obstruction(band[1]), -band[1]))
    height = (output_size or (1280, 720))[1]
    font_size = 24 if height <= 720 else 32
    appearance = f"FontName=Arial,FontSize={font_size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0"
    if name == "top": return f"Alignment=8,MarginV={max(24, round(height * y))},{appearance}"
    if name == "middle": return f"Alignment=5,MarginV=0,{appearance}"
    return f"Alignment=2,MarginV={max(24, round(height * (1-y)))},{appearance}"


def _subtitle_filter(path: Path, layout: dict | None = None, output_size: tuple[int, int] | None = None) -> str:
    # ffmpeg's subtitles filter accepts forward slashes; escape the drive colon.
    escaped = path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
    return f"subtitles=filename='{escaped}':charenc=UTF-8:force_style='{subtitle_style(layout, output_size)}'"


def render(source: Path, edl: dict, output: Path, preview_height: int | None = None, has_audio: bool = True, cancelled=None, progress=None, layout: dict | None = None, output_size: tuple[int, int] | None = None, use_hardware: bool = False, cpu_threads: int = 0, filter_threads: int = 0) -> None:
    if not edl["segments"]: raise ValueError("Nenhum highlight selecionado para renderizar.")
    work = output.parent / "render_segments"; work.mkdir(exist_ok=True)
    clips = []
    for index, segment in enumerate(edl["segments"]):
        if cancelled and cancelled.is_set(): raise RuntimeError("Renderização cancelada.")
        clip = work / f"{index:03}.mp4"; clips.append(clip)
        preferred = encoder(use_hardware)
        try:
            _run(segment_command(source, segment, clip, edl["fps_rational"], preview_height, has_audio, layout, output_size, preferred, cpu_threads), cancelled, cpu_threads, filter_threads)
        except subprocess.CalledProcessError:
            if preferred != "h264_amf": raise
            _run(segment_command(source, segment, clip, edl["fps_rational"], preview_height, has_audio, layout, output_size, "libx264", cpu_threads), cancelled, cpu_threads, filter_threads)
        if progress: progress(index + 1, len(edl["segments"]))
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{clip.resolve().as_posix()}'\n" for clip in clips), encoding="utf-8")
    intermediate = output.with_name(f"{output.stem}.concat.mp4")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(intermediate)], cancelled, cpu_threads, filter_threads)
    subtitles = edl.get("subtitles")
    if subtitles and Path(subtitles).is_file():
        caption_size = output_size
        if preview_height and output_size:
            caption_size = (round(output_size[0] * preview_height / output_size[1]), preview_height)
        preferred = encoder(use_hardware)
        command = ["ffmpeg", "-y", "-i", str(intermediate), "-vf", _subtitle_filter(Path(subtitles), layout, caption_size), *encoder_options(preferred, cpu_threads), "-c:a", "copy", "-movflags", "+faststart", str(output)]
        try:
            _run(command, cancelled, cpu_threads, filter_threads)
        except subprocess.CalledProcessError:
            if preferred != "h264_amf": raise
            fallback = ["ffmpeg", "-y", "-i", str(intermediate), "-vf", _subtitle_filter(Path(subtitles), layout, caption_size), *encoder_options("libx264", cpu_threads), "-c:a", "copy", "-movflags", "+faststart", str(output)]
            _run(fallback, cancelled, cpu_threads, filter_threads)
        intermediate.unlink(missing_ok=True)
    else:
        intermediate.replace(output)
