import json
import math
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .core.audio import analyze_audio, audio_features_are_finite
from .core.assets import list_sfx, sfx_path
from .core.captions import build_srt
from .core.edl import automatic_target_duration, make_edl, validate_highlights
from .core.effects import validate_effect
from .core.gameplay import analyze_gameplay, build_activity_score, detect_dead_zones, detect_events, detect_outcome_candidates, sanitize_activity, save_debug_frames
from .core.highlights import build_highlights, style_highlight_settings
from .core.jobs import JobManager
from .core.layout import load_layout, save_layout
from .core.paths import CONFIG, PROJECTS, ROOT
from .core.probe import probe_video
from .core.project import append_log, create_project, read_json, recent_projects, write_json
from .core.renderer import render
from .core.speech import transcript_events
from .core.thumbnails import create_frame, create_thumbnail
from .core.transcription import transcribe_local
from .core.verify import expected_edl_duration, verify_render

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
app = FastAPI(title="Aizen Auto Editor")
app.mount("/static", StaticFiles(directory=ROOT / "app" / "web" / "static"), name="static")
jobs = JobManager()


class VideoRequest(BaseModel): path: str; edit_type: str = "automatic"; effects: str = "medium"; captions: str = "important"; target_duration: str = "automatic"
class HighlightsRequest(BaseModel): project: str; highlights: list[dict]
class ProjectRequest(BaseModel): project: str
class LayoutRequest(BaseModel): project: str; layout: dict


def folder(value: str) -> Path:
    candidate = Path(value).resolve()
    projects = PROJECTS.resolve()
    if not candidate.is_dir() or not candidate.is_relative_to(projects): raise HTTPException(400, "Projeto inválido.")
    return candidate


@app.get("/", response_class=HTMLResponse)
def home(): return (ROOT / "app" / "web" / "templates" / "index.html").read_text(encoding="utf-8")


@app.post("/api/load")
def load_video(request: VideoRequest):
    video = Path(request.path)
    if not video.is_file(): raise HTTPException(400, "Caminho de vídeo inválido.")
    source = probe_video(video)
    settings = request.model_dump()
    project = create_project(video, source, settings)
    return {"project": str(project), "source": source}


@app.get("/api/projects")
def list_projects(): return recent_projects()


@app.get("/api/assets/sfx")
def available_sfx(): return list_sfx()


@app.get("/api/project")
def open_project(project: str):
    base = folder(project)
    activity_path = base / "activity_score.json"
    activity = read_json(activity_path, [])
    repaired_activity = sanitize_activity(activity)
    if repaired_activity != activity: write_json(activity_path, repaired_activity)
    return {"project": str(base), "source": read_json(base / "source.json"), "settings": read_json(base / "settings.json", {}), "layout": load_layout(base), "highlights": read_json(base / "highlights.json", []), "events": read_json(base / "gameplay_events.json", []), "activity": repaired_activity, "dead_zones": read_json(base / "dead_zones.json", []), "has_edl": (base / "edl.json").exists()}


@app.post("/api/pick-video")
def pick_video():
    """Native file selector for the local Windows-only application."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(title="Selecionar gameplay", filetypes=[("Vídeos", "*.mp4 *.mkv *.mov *.avi *.webm"), ("Todos os arquivos", "*.*")])
        root.destroy()
        return {"path": selected}
    except Exception as error:
        raise HTTPException(500, f"Não foi possível abrir o seletor de arquivos: {error}") from error


@app.post("/api/analyze")
def analyze(request: ProjectRequest):
    project = folder(request.project)
    def work(job):
        source = read_json(project / "source.json"); video = Path(source["path"]); defaults = read_json(CONFIG / "default.json"); game = read_json(CONFIG / "freefire.json")
        job.update("Transcrevendo localmente", 10); append_log(project, "Iniciando transcrição local"); transcript_path = project / "transcript.json"
        transcription_config = defaults["transcription"]
        transcript = read_json(transcript_path)
        if not transcript or transcript.get("engine") == "unavailable":
            def transcription_progress(fraction: float) -> None:
                elapsed = max(0, min(source["duration"], source["duration"] * fraction))
                job.update(f"Transcrevendo fala: {elapsed / 60:.1f} / {source['duration'] / 60:.1f} min", 10 + round(18 * fraction))
            transcript = transcribe_local(video, transcription_config["model"], transcription_config["device"], transcription_config["compute_type"], int(transcription_config.get("cpu_threads", 0)), source["duration"], transcription_progress, job.cancelled)
            write_json(transcript_path, transcript)
        (project / "transcript.txt").write_text("\n".join(s.get("text", "") for s in transcript["segments"]), encoding="utf-8")
        if job.cancelled.is_set(): return {}
        job.update("Extraindo atividade de áudio", 30); append_log(project, "Extraindo atividade de áudio"); audio = read_json(project / "audio_features.json")
        expected_audio_windows = math.ceil(source["duration"] / defaults["analysis_sample_seconds"]) + 2
        if not audio or len(audio) > expected_audio_windows or not audio_features_are_finite(audio):
            sample_rate = source["audio"]["sample_rate"] if source["audio"] else 48_000
            audio = analyze_audio(video, source["duration"], defaults["analysis_sample_seconds"], sample_rate)
            write_json(project / "audio_features.json", audio)
        if job.cancelled.is_set(): return {}
        job.update("Analisando movimento da gameplay", 55); append_log(project, "Analisando movimento e HUD da gameplay"); layout = load_layout(project)
        state = read_json(project / "project.json", {})
        analysis_signature = {"sample_seconds": defaults["analysis_sample_seconds"], "layout": layout}
        visual = read_json(project / "visual_features.json")
        if not visual or state.get("analysis_signature") != analysis_signature:
            visual = analyze_gameplay(video, defaults["analysis_sample_seconds"], layout)
            write_json(project / "visual_features.json", visual)
            state["analysis_signature"] = analysis_signature; write_json(project / "project.json", state)
        activity = build_activity_score(visual, audio, transcript); write_json(project / "activity_score.json", activity)
        dead_zones = detect_dead_zones(activity, game["dead_zone"]); write_json(project / "dead_zones.json", dead_zones)
        if job.cancelled.is_set(): return {}
        job.update("Detectando e agrupando highlights", 78); append_log(project, "Detectando eventos e agrupando highlights"); visual_events = detect_events(visual, audio, defaults["combat_threshold"]); outcome_candidates = detect_outcome_candidates(visual_events); events = visual_events + outcome_candidates + transcript_events(transcript); events.sort(key=lambda event: event["start"]); write_json(project / "gameplay_events.json", events)
        settings = read_json(project / "settings.json", {})
        highlight_settings = style_highlight_settings(game["highlight"], settings.get("edit_type", "automatic"))
        highlights = build_highlights(events, game["weights"], highlight_settings, source["duration"], dead_zones)
        debug_frames = save_debug_frames(video, visual_events + outcome_candidates, project / "debug")
        job.update("Gerando thumbnails", 88)
        for index, highlight in enumerate(highlights, 1):
            if job.cancelled.is_set(): return {}
            job.update(f"Gerando thumbnails ({index}/{len(highlights)})", 88 + int(8 * index / max(1, len(highlights))))
            thumbnail = project / "thumbnails" / f"{highlight['id']}.jpg"
            if create_thumbnail(video, highlight["start"], thumbnail): highlight["thumbnail"] = thumbnail.name
        write_json(project / "highlights.json", highlights); append_log(project, f"Análise concluída ({settings.get('edit_type', 'automatic')}): {len(highlights)} highlights; {len(dead_zones)} zonas mortas")
        return {"highlights": highlights, "events": events, "activity": activity, "dead_zones": dead_zones, "debug_frames": debug_frames, "duration": source["duration"], "transcription": transcript.get("engine"), "warning": transcript.get("warning")}
    job = jobs.start(str(project), "analysis", work)
    return job.snapshot()


@app.post("/api/edl")
def save_edl(request: HighlightsRequest):
    project = folder(request.project); source = read_json(project / "source.json")
    try: validate_highlights(request.highlights, source["duration"])
    except ValueError as error: raise HTTPException(400, str(error)) from error
    effect_flags = read_json(CONFIG / "freefire.json")["effects"]
    for highlight in request.highlights:
        try: highlight["effects"] = [validate_effect(effect, effect_flags) for effect in highlight.get("effects", [])]
        except ValueError as error: raise HTTPException(400, str(error)) from error
        try: highlight["sfx"] = sfx_path(highlight.get("sfx")).name if highlight.get("sfx") else None
        except ValueError as error: raise HTTPException(400, str(error)) from error
    write_json(project / "highlights.json", request.highlights)
    settings = read_json(project / "settings.json", {}); transcript = read_json(project / "transcript.json", {"segments": []})
    caption_mode = settings.get("captions", "Nenhuma")
    subtitle_path = project / "subtitles.srt"
    target = settings.get("target_duration", "automatic")
    try: target_seconds = automatic_target_duration(source["duration"], read_json(CONFIG / "freefire.json")["highlight"]) if target == "automatic" else (None if target in {"custom", ""} else float(target))
    except (TypeError, ValueError): target_seconds = None
    edl = make_edl(source["path"], request.highlights, source["fps_rational"], str(subtitle_path) if caption_mode not in {"none", "Nenhuma"} else None, target_seconds)
    if not build_srt(transcript, edl["segments"], subtitle_path, caption_mode): edl["subtitles"] = None
    write_json(project / "edl.json", edl)
    append_log(project, f"EDL salva: {len(edl['segments'])} segmentos, {edl['total_duration']} s")
    with (project / "feedback.jsonl").open("a", encoding="utf-8") as output:
        for h in request.highlights:
            decision = "favorite" if h.get("favorite") else ("keep" if h.get("selected") else "remove")
            output.write(json.dumps({"highlight_id": h["id"], "decision": decision, "features": {"score": h["score"], "events": h["events"]}}, ensure_ascii=False) + "\n")
    return edl


@app.post("/api/render/{kind}")
def render_video(kind: str, request: ProjectRequest):
    if kind not in {"preview", "final"}: raise HTTPException(400, "Tipo de renderização inválido.")
    project = folder(request.project); source = read_json(project / "source.json"); edl = read_json(project / "edl.json")
    if not edl: raise HTTPException(400, "Gere o EDL antes de renderizar.")
    def work(job):
        output = project / f"{kind}.mp4"; job.update("Renderizando segmentos", 5); append_log(project, f"Iniciando renderização {kind}")
        defaults = read_json(CONFIG / "default.json")
        render(Path(source["path"]), edl, output, 720 if kind == "preview" else None, has_audio=bool(source["audio"]), cancelled=job.cancelled, progress=lambda n, total: job.update("Renderizando segmentos", 5 + int(80 * n / total)), layout=load_layout(project), output_size=(source["width"], source["height"]), use_hardware=defaults.get("use_hardware_encoder", False), cpu_threads=int(defaults.get("cpu_threads", 0)), filter_threads=int(defaults.get("filter_threads", 0)))
        if job.cancelled.is_set(): return {}
        job.update("Verificando saída", 92); verification = verify_render(output, source["fps"], expected_edl_duration(edl)); write_json(project / f"{kind}_verify.json", verification); append_log(project, f"Renderização {kind} concluída; validação: {'ok' if verification['ok'] else 'falhou'}")
        return {"file": f"{kind}.mp4", "verification": verification}
    return jobs.start(str(project), kind, work).snapshot()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job: raise HTTPException(404, "Operação não encontrada.")
    return job.snapshot()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    job = jobs.cancel(job_id)
    if not job: raise HTTPException(404, "Operação não encontrada.")
    return job.snapshot()


@app.get("/api/media")
def media(project: str, name: str):
    base = folder(project)
    item = (base / name).resolve()
    if not item.is_relative_to(base): raise HTTPException(400, "Arquivo inválido.")
    if not item.is_file(): raise HTTPException(404, "Arquivo não encontrado.")
    return FileResponse(item)


@app.get("/api/source")
def source_media(project: str):
    base = folder(project); source = read_json(base / "source.json")
    item = Path(source["path"])
    if not item.is_file(): raise HTTPException(404, "Vídeo de origem não encontrado.")
    return FileResponse(item)


@app.post("/api/calibration-frame")
def calibration_frame(request: ProjectRequest):
    project = folder(request.project); source = read_json(project / "source.json")
    frame = project / "calibration.jpg"
    if not frame.exists() and not create_frame(Path(source["path"]), source["duration"] / 2, frame, 960):
        raise HTTPException(500, "Não foi possível extrair um frame para calibração.")
    return {"file": "calibration.jpg"}


@app.get("/api/layout")
def get_layout(project: str):
    return load_layout(folder(project))


@app.put("/api/layout")
def put_layout(request: LayoutRequest):
    try: return save_layout(folder(request.project), request.layout)
    except ValueError as error: raise HTTPException(400, str(error)) from error
