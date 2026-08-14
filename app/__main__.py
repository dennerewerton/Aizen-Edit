import webbrowser
from threading import Timer

import uvicorn


if __name__ == "__main__":
    Timer(0.7, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)

