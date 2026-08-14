import subprocess
from pathlib import Path


def encoder(use_hardware: bool) -> str:
    return "h264_amf" if use_hardware else "libx264"


def segment_command(source: Path, segment: dict, output: Path, fps: str, preview_height: int | None = None) -> list[str]:
    duration = segment["end"] - segment["start"]
    fade = min(0.03, duration / 4)
    filters = [f"fps={fps}"]
    if preview_height: filters.append(f"scale=-2:{preview_height}")
    return ["ffmpeg", "-y", "-ss", str(segment["start"]), "-i", str(source), "-t", str(duration), "-vf", ",".join(filters), "-af", f"afade=t=in:st=0:d={fade},afade=t=out:st={max(0, duration-fade)}:d={fade}", "-c:v", "libx264", "-c:a", "aac", str(output)]


def render(source: Path, edl: dict, output: Path, preview_height: int | None = None) -> None:
    if not edl["segments"]: raise ValueError("Nenhum highlight selecionado para renderizar.")
    work = output.parent / "render_segments"; work.mkdir(exist_ok=True)
    clips = []
    for index, segment in enumerate(edl["segments"]):
        clip = work / f"{index:03}.mp4"; clips.append(clip)
        subprocess.run(segment_command(source, segment, clip, edl["fps_rational"], preview_height), check=True, capture_output=True)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{clip.resolve().as_posix()}'\n" for clip in clips), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(output)], check=True, capture_output=True)

