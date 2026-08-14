import subprocess
import time

from .effects import filters_for_effects, windowed_video_filtergraph
from pathlib import Path


def encoder(use_hardware: bool) -> str:
    return "h264_amf" if use_hardware else "libx264"


def segment_command(source: Path, segment: dict, output: Path, fps: str, preview_height: int | None = None, has_audio: bool = True, layout: dict | None = None, output_size: tuple[int, int] | None = None, video_encoder: str = "libx264") -> list[str]:
    duration = segment["end"] - segment["start"]
    fade = min(0.03, duration / 4)
    effect_video, effect_audio = filters_for_effects(segment.get("effects", []), layout, output_size)
    filters = effect_video + [f"fps={fps}"]
    if preview_height: filters.append(f"scale=-2:{preview_height}")
    graph = windowed_video_filtergraph(segment.get("effects", []), layout, fps, preview_height)
    command = ["ffmpeg", "-y", "-ss", str(segment["start"]), "-i", str(source), "-t", str(duration)]
    if graph: command += ["-filter_complex", graph, "-map", "[vout]", "-map", "0:a?"]
    else: command += ["-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(filters)]
    if has_audio:
        audio_filters = effect_audio + [f"afade=t=in:st=0:d={fade}", f"afade=t=out:st={max(0, duration-fade)}:d={fade}"]
        command += ["-af", ",".join(audio_filters), "-c:a", "aac"]
    command += ["-c:v", video_encoder]
    if video_encoder == "h264_amf": command += ["-quality", "quality", "-rc", "cqp", "-qp_i", "20", "-qp_p", "22"]
    else: command += ["-crf", "18", "-preset", "medium"]
    command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    return command


def _run(command: list[str], cancelled=None) -> None:
    # FFmpeg writes progress continually to stderr. Keeping that pipe unread
    # deadlocks a long render once Windows' pipe buffer fills.
    command = [command[0], "-hide_banner", "-loglevel", "error", *command[1:]]
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
    if name == "top": return f"Alignment=8,MarginV={max(24, round(height * y))}"
    if name == "middle": return "Alignment=5,MarginV=0"
    return f"Alignment=2,MarginV={max(24, round(height * (1-y)))}"


def _subtitle_filter(path: Path, layout: dict | None = None, output_size: tuple[int, int] | None = None) -> str:
    # ffmpeg's subtitles filter accepts forward slashes; escape the drive colon.
    escaped = path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
    return f"subtitles=filename='{escaped}':charenc=UTF-8:force_style='{subtitle_style(layout, output_size)}'"


def render(source: Path, edl: dict, output: Path, preview_height: int | None = None, has_audio: bool = True, cancelled=None, progress=None, layout: dict | None = None, output_size: tuple[int, int] | None = None, use_hardware: bool = False) -> None:
    if not edl["segments"]: raise ValueError("Nenhum highlight selecionado para renderizar.")
    work = output.parent / "render_segments"; work.mkdir(exist_ok=True)
    clips = []
    for index, segment in enumerate(edl["segments"]):
        if cancelled and cancelled.is_set(): raise RuntimeError("Renderização cancelada.")
        clip = work / f"{index:03}.mp4"; clips.append(clip)
        preferred = encoder(use_hardware)
        try:
            _run(segment_command(source, segment, clip, edl["fps_rational"], preview_height, has_audio, layout, output_size, preferred), cancelled)
        except subprocess.CalledProcessError:
            if preferred != "h264_amf": raise
            _run(segment_command(source, segment, clip, edl["fps_rational"], preview_height, has_audio, layout, output_size, "libx264"), cancelled)
        if progress: progress(index + 1, len(edl["segments"]))
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{clip.resolve().as_posix()}'\n" for clip in clips), encoding="utf-8")
    intermediate = output.with_name(f"{output.stem}.concat.mp4")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(intermediate)], cancelled)
    subtitles = edl.get("subtitles")
    if subtitles and Path(subtitles).is_file():
        caption_size = output_size
        if preview_height and output_size:
            caption_size = (round(output_size[0] * preview_height / output_size[1]), preview_height)
        _run(["ffmpeg", "-y", "-i", str(intermediate), "-vf", _subtitle_filter(Path(subtitles), layout, caption_size), "-c:v", "libx264", "-c:a", "copy", "-movflags", "+faststart", str(output)], cancelled)
        intermediate.unlink(missing_ok=True)
    else:
        intermediate.replace(output)
