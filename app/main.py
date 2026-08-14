import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .core.audio import analyze_audio
from .core.edl import make_edl
from .core.gameplay import analyze_gameplay, detect_events
from .core.highlights import build_highlights
from .core.jobs import JobManager
from .core.layout import load_layout, save_layout
from .core.paths import CONFIG, ROOT
from .core.probe import probe_video
from .core.project import create_project, read_json, write_json
from .core.renderer import render
from .core.thumbnails import create_thumbnail
from .core.transcription import transcribe_local
from .core.verify import verify_render

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
    projects = (ROOT / "projects").resolve()
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


@app.post("/api/analyze")
def analyze(request: ProjectRequest):
    project = folder(request.project)
    def work(job):
        source = read_json(project / "source.json"); video = Path(source["path"]); defaults = read_json(CONFIG / "default.json"); game = read_json(CONFIG / "freefire.json")
        job.update("Transcrevendo localmente", 10); transcript_path = project / "transcript.json"
        transcript = read_json(transcript_path) or transcribe_local(video); write_json(transcript_path, transcript)
        (project / "transcript.txt").write_text("\n".join(s.get("text", "") for s in transcript["segments"]), encoding="utf-8")
        if job.cancelled.is_set(): return {}
        job.update("Extraindo atividade de áudio", 30); audio = read_json(project / "audio_features.json") or analyze_audio(video, source["duration"]); write_json(project / "audio_features.json", audio)
        if job.cancelled.is_set(): return {}
        job.update("Analisando movimento da gameplay", 55); visual = read_json(project / "activity_score.json") or analyze_gameplay(video, defaults["analysis_sample_seconds"]); write_json(project / "activity_score.json", visual)
        if job.cancelled.is_set(): return {}
        job.update("Detectando e agrupando highlights", 78); events = detect_events(visual, audio, defaults["combat_threshold"]); write_json(project / "gameplay_events.json", events)
        highlights = build_highlights(events, game["weights"], game["highlight"])
        job.update("Gerando thumbnails", 88)
        for highlight in highlights:
            if job.cancelled.is_set(): return {}
            thumbnail = project / "thumbnails" / f"{highlight['id']}.jpg"
            if create_thumbnail(video, highlight["start"], thumbnail): highlight["thumbnail"] = thumbnail.name
        write_json(project / "highlights.json", highlights)
        return {"highlights": highlights, "transcription": transcript.get("engine"), "warning": transcript.get("warning")}
    job = jobs.start(str(project), "analysis", work)
    return job.snapshot()


@app.post("/api/edl")
def save_edl(request: HighlightsRequest):
    project = folder(request.project); source = read_json(project / "source.json")
    write_json(project / "highlights.json", request.highlights)
    edl = make_edl(source["path"], request.highlights, source["fps_rational"]); write_json(project / "edl.json", edl)
    with (project / "feedback.jsonl").open("a", encoding="utf-8") as output:
        for h in request.highlights: output.write(json.dumps({"highlight_id": h["id"], "decision": "keep" if h.get("selected") else "remove", "features": {"score": h["score"], "events": h["events"]}}, ensure_ascii=False) + "\n")
    return edl


@app.post("/api/render/{kind}")
def render_video(kind: str, request: ProjectRequest):
    if kind not in {"preview", "final"}: raise HTTPException(400, "Tipo de renderização inválido.")
    project = folder(request.project); source = read_json(project / "source.json"); edl = read_json(project / "edl.json")
    if not edl: raise HTTPException(400, "Gere o EDL antes de renderizar.")
    def work(job):
        output = project / f"{kind}.mp4"; job.update("Renderizando segmentos", 5)
        render(Path(source["path"]), edl, output, 720 if kind == "preview" else None, has_audio=bool(source["audio"]), cancelled=job.cancelled, progress=lambda n, total: job.update("Renderizando segmentos", 5 + int(80 * n / total)))
        if job.cancelled.is_set(): return {}
        job.update("Verificando saída", 92); verification = verify_render(output, source["fps"]); write_json(project / f"{kind}_verify.json", verification)
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


@app.get("/api/layout")
def get_layout(project: str):
    return load_layout(folder(project))


@app.put("/api/layout")
def put_layout(request: LayoutRequest):
    try: return save_layout(folder(request.project), request.layout)
    except ValueError as error: raise HTTPException(400, str(error)) from error
