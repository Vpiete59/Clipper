"""Point d'entrée : serveur local + fenêtre de bureau (WebView2)."""

from __future__ import annotations

import argparse
import threading
import time
import urllib.request

import uvicorn

from . import jobs, watcher
from .server import app

HOST, PORT = "127.0.0.1", 8765


def _serve() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def _wait_ready(timeout: float = 20) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://{HOST}:{PORT}/api/settings", timeout=1)
            return
        except OSError:
            time.sleep(0.2)


def main() -> None:
    ap = argparse.ArgumentParser(prog="clipper")
    ap.add_argument("--no-window", action="store_true", help="serveur seul (ouvrir l'URL dans un navigateur)")
    args = ap.parse_args()

    jobs.start()
    watcher.start()
    if args.no_window:
        print(f"Clipper sur http://{HOST}:{PORT}")
        _serve()
        return

    threading.Thread(target=_serve, daemon=True).start()
    _wait_ready()
    import webview

    webview.create_window("Clipper", f"http://{HOST}:{PORT}", width=1440, height=900, min_size=(1100, 700),
                          background_color="#0d0e12")
    webview.start()


if __name__ == "__main__":
    main()
