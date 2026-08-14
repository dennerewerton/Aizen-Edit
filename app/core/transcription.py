from abc import ABC, abstractmethod
from pathlib import Path


class Transcriber(ABC):
    @abstractmethod
    def transcribe(self, video: Path) -> dict: ...


class FasterWhisperTranscriber(Transcriber):
    def __init__(self, model="small", device="cpu", compute_type="int8"):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(self, video: Path) -> dict:
        segments, info = self.model.transcribe(str(video), word_timestamps=True, vad_filter=True)
        output = []
        for segment in segments:
            output.append({"start": segment.start, "end": segment.end, "text": segment.text.strip(), "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (segment.words or [])]})
        return {"engine": "faster-whisper", "language": info.language, "segments": output}


def transcribe_local(video: Path, model="small", device="cpu", compute_type="int8") -> dict:
    try: return FasterWhisperTranscriber(model, device, compute_type).transcribe(video)
    except ModuleNotFoundError:
        return {"engine": "unavailable", "segments": [], "warning": "Transcrição local requer faster-whisper. Execute: python -m pip install faster-whisper"}
