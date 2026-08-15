from abc import ABC, abstractmethod
from pathlib import Path


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, video: Path) -> dict: ...


class FasterWhisperTranscriber(Transcriber):
    def __init__(self, model="small", device="cpu", compute_type="int8", cpu_threads: int = 0):
        from faster_whisper import WhisperModel
        options = {"device": device, "compute_type": compute_type}
        if cpu_threads > 0: options["cpu_threads"] = cpu_threads
        self.model = WhisperModel(model, **options)

    def transcribe(self, video: Path, duration: float | None = None, progress=None, cancelled=None) -> dict:
        segments, info = self.model.transcribe(str(video), word_timestamps=True, vad_filter=True)
        output = []
        for segment in segments:
            if cancelled and cancelled.is_set(): break
            output.append({"start": segment.start, "end": segment.end, "text": segment.text.strip(), "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (segment.words or [])]})
            if progress and duration and duration > 0: progress(min(1.0, float(segment.end) / duration))
        return {"engine": "faster-whisper", "language": info.language, "segments": output}


def transcribe_local(video: Path, model="small", device="cpu", compute_type="int8", cpu_threads: int = 0, duration: float | None = None, progress=None, cancelled=None) -> dict:
    try: return FasterWhisperTranscriber(model, device, compute_type, cpu_threads).transcribe(video, duration, progress, cancelled)
    except ModuleNotFoundError:
        return {"engine": "unavailable", "segments": [], "warning": "Transcrição local requer faster-whisper. Execute: python -m pip install faster-whisper"}
