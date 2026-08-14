"""Small local job manager for long-running analysis and FFmpeg work."""
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
from uuid import uuid4


@dataclass
class Job:
    id: str
    project: str
    kind: str
    stage: str = "queued"
    percent: int = 0
    state: str = "queued"
    error: str | None = None
    result: dict | None = None
    cancelled: Event = field(default_factory=Event, repr=False)

    def update(self, stage: str, percent: int) -> None:
        self.stage, self.percent, self.state = stage, percent, "running"

    def snapshot(self) -> dict:
        return {"id": self.id, "project": self.project, "kind": self.kind, "stage": self.stage,
                "percent": self.percent, "state": self.state, "error": self.error, "result": self.result}


class JobManager:
    def __init__(self): self._jobs: dict[str, Job] = {}; self._lock = Lock()

    def start(self, project: str, kind: str, work) -> Job:
        job = Job(uuid4().hex, project, kind)
        with self._lock: self._jobs[job.id] = job
        def runner():
            try:
                job.state = "running"; job.result = work(job)
                if job.cancelled.is_set(): job.state, job.stage = "cancelled", "Cancelado"
                else: job.state, job.stage, job.percent = "completed", "Concluído", 100
            except Exception as error:
                job.state, job.stage, job.error = "failed", "Falhou", str(error)
        Thread(target=runner, daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock: return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job: job.cancelled.set()
        return job
