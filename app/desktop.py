"""Native Windows shell for the local FastAPI application."""
import socket
import time
from threading import Thread

import uvicorn
import webview

HOST, PORT = "127.0.0.1", 8000

def _serve() -> None: uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="warning", reload=False)

def _ready(timeout: float = 12) -> bool:
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        try:
            with socket.create_connection((HOST, PORT), timeout=.2): return True
        except OSError: time.sleep(.1)
    return False

def run() -> None:
    Thread(target=_serve, daemon=True).start()
    if not _ready(): raise RuntimeError("Não foi possível iniciar o Aizen Auto Editor localmente.")
    webview.create_window("Aizen Auto Editor", f"http://{HOST}:{PORT}", width=1360, height=900, min_size=(980, 700), background_color="#08111d")
    webview.start(gui="edgechromium", debug=False)

if __name__ == "__main__": run()
