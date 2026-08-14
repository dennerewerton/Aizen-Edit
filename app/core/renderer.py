import subprocess
import time
from pathlib import Path


def encoder(use_hardware: bool) -> str:
    return "h264_amf" if use_hardware else "libx264"


def segment_command(source: Path, segment: dict, output: Path, fps: str, preview_height: int | None = None, has_audio: bool = True) -> list[str]:
    duration = segment["end"] - segment["start"]
    fade = min(0.03, duration / 4)
    filters = [f"fps={fps}"]
    if preview_height: filters.append(f"scale=-2:{preview_height}")
    command = ["ffmpeg", "-y", "-ss", str(segment["start"]), "-i", str(source), "-t", str(duration), "-map", "0:v:0", "-map", "0:a?", "-vf", ",".join(filters)]
    if has_audio:
        command += ["-af", f"afade=t=in:st=0:d={fade},afade=t=out:st={max(0, duration-fade)}:d={fade}", "-c:a", "aac"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    return command


def _run(command: list[str], cancelled=None) -> None:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while process.poll() is None:
        if cancelled and cancelled.is_set():
            process.terminate(); process.wait(timeout=5)
            raise RuntimeError("Renderização cancelada.")
        time.sleep(.1)
    if process.returncode:
        _, error = process.communicate()
        raise subprocess.CalledProcessError(process.returncode, command, stderr=error)


def render(source: Path, edl: dict, output: Path, preview_height: int | None = None, has_audio: bool = True, cancelled=None, progress=None) -> None:
    if not edl["segments"]: raise ValueError("Nenhum highlight selecionado para renderizar.")
    work = output.parent / "render_segments"; work.mkdir(exist_ok=True)
    clips = []
    for index, segment in enumerate(edl["segments"]):
        if cancelled and cancelled.is_set(): raise RuntimeError("Renderização cancelada.")
        clip = work / f"{index:03}.mp4"; clips.append(clip)
        _run(segment_command(source, segment, clip, edl["fps_rational"], preview_height, has_audio), cancelled)
        if progress: progress(index + 1, len(edl["segments"]))
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{clip.resolve().as_posix()}'\n" for clip in clips), encoding="utf-8")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(output)], cancelled)
