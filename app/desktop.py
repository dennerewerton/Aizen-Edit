"""Native Windows shell for the local FastAPI application."""
import socket
import time
from threading import Thread
from urllib.request import urlopen

import uvicorn
import webview

from app.core.version import APP_NAME, VERSION
from app.core.paths import CONFIG
from app.core.project import read_json
from app.core.updates import install_update_before_start

HOST = "127.0.0.1"

def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def _serve(port: int) -> None: uvicorn.run("app.main:app", host=HOST, port=port, log_level="warning", reload=False)

def _ready(port: int, timeout: float = 12) -> bool:
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        try:
            with urlopen(f"http://{HOST}:{port}/api/health", timeout=.5) as response:
                if response.status == 200: return True
        except OSError: time.sleep(.1)
    return False

def run() -> None:
    if install_update_before_start(read_json(CONFIG / "update.json", {})):
        return
    port = _available_port()
    Thread(target=_serve, args=(port,), daemon=True).start()
    if not _ready(port): raise RuntimeError("Não foi possível iniciar o Aizen Auto Editor localmente.")
    webview.create_window(f"{APP_NAME} {VERSION}", f"http://{HOST}:{port}", width=1360, height=900, min_size=(980, 700), background_color="#08111d")
    webview.start(gui="edgechromium", debug=False)

if __name__ == "__main__": run()
