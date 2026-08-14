import subprocess
import time

from .effects import filters_for_effects
from pathlib import Path


def encoder(use_hardware: bool) -> str:
    return "h264_amf" if use_hardware else "libx264"


def segment_command(source: Path, segment: dict, output: Path, fps: str, preview_height: int | None = None, has_audio: bool = True, layout: dict | None = None, output_size: tuple[int, int] | None = None) -> list[str]:
    duration = segment["end"] - segment["start"]
    fade = min(0.03, duration / 4)
    effect_video, effect_audio = filters_for_effects(segment.get("effects", []), layout, output_size)
    filters = effect_video + [f"fps={fps}"]
    if preview_height: filters.append(f"scale=-2:{preview_height}")
    command = ["ffmpeg", "-y", "-ss", str(segment["start"]), "-i", str(source), "-t", str(duration), "-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(filters)]
    if has_audio:
        audio_filters = effect_audio + [f"afade=t=in:st=0:d={fade}", f"afade=t=out:st={max(0, duration-fade)}:d={fade}"]
        command += ["-af", ",".join(audio_filters), "-c:a", "aac"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
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


def _subtitle_filter(path: Path) -> str:
    # ffmpeg's subtitles filter accepts forward slashes; escape the drive colon.
    escaped = path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
    return f"subtitles=filename='{escaped}':charenc=UTF-8"


def render(source: Path, edl: dict, output: Path, preview_height: int | None = None, has_audio: bool = True, cancelled=None, progress=None, layout: dict | None = None, output_size: tuple[int, int] | None = None) -> None:
    if not edl["segments"]: raise ValueError("Nenhum highlight selecionado para renderizar.")
    work = output.parent / "render_segments"; work.mkdir(exist_ok=True)
    clips = []
    for index, segment in enumerate(edl["segments"]):
        if cancelled and cancelled.is_set(): raise RuntimeError("Renderização cancelada.")
        clip = work / f"{index:03}.mp4"; clips.append(clip)
        _run(segment_command(source, segment, clip, edl["fps_rational"], preview_height, has_audio, layout, output_size), cancelled)
        if progress: progress(index + 1, len(edl["segments"]))
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{clip.resolve().as_posix()}'\n" for clip in clips), encoding="utf-8")
    intermediate = output.with_name(f"{output.stem}.concat.mp4")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(intermediate)], cancelled)
    subtitles = edl.get("subtitles")
    if subtitles and Path(subtitles).is_file():
        _run(["ffmpeg", "-y", "-i", str(intermediate), "-vf", _subtitle_filter(Path(subtitles)), "-c:v", "libx264", "-c:a", "copy", "-movflags", "+faststart", str(output)], cancelled)
        intermediate.unlink(missing_ok=True)
    else:
        intermediate.replace(output)
