"""Optional localhost-only helper for future transcript ranking refinement."""
import json
from urllib.error import URLError
from urllib.request import Request, urlopen


class LocalLLM:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str | None = None, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.model)

    def available(self) -> bool:
        if not self.enabled: return False
        try:
            with urlopen(f"{self.base_url}/api/tags", timeout=2) as response:
                return response.status == 200
        except (URLError, OSError):
            return False

    def classify_excerpt(self, excerpt: str) -> dict | None:
        """Ask only about a short transcript excerpt; never sends media or frames."""
        if not self.enabled or not excerpt.strip(): return None
        prompt = ("Classifique este trecho de gameplay em JSON com os booleanos funny, trash_talk, "
                  "important e uma confidence de 0 a 1. Não invente contexto. Trecho: " + excerpt[:2000])
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False, "format": "json"}).encode()
        request = Request(f"{self.base_url}/api/generate", data=body, headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                value = json.loads(json.loads(response.read().decode())["response"])
            return {"funny": bool(value.get("funny")), "trash_talk": bool(value.get("trash_talk")), "important": bool(value.get("important")), "confidence": max(0.0, min(1.0, float(value.get("confidence", 0))))}
        except (URLError, OSError, ValueError, KeyError, json.JSONDecodeError):
            return None
