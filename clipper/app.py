"""Point d'entrée : serveur local + fenêtre de bureau (WebView2)."""

from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.request

from .config import DATA_DIR

HOST, PORT = "127.0.0.1", 8765
LOG_FILE = DATA_DIR / "clipper.log"

# Lancé via pythonw (sans console), sys.stdout/stderr valent None : uvicorn plante en
# configurant ses logs, et les barres de téléchargement des modèles aussi. On les envoie
# dans un fichier, qui sert en plus de journal pour diagnostiquer.
if sys.stdout is None or sys.stderr is None:
    _log = open(LOG_FILE, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

import uvicorn  # noqa: E402

from . import jobs, watcher  # noqa: E402
from .server import app  # noqa: E402


def _serve() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def _is_up() -> bool:
    try:
        urllib.request.urlopen(f"http://{HOST}:{PORT}/api/settings", timeout=1)
        return True
    except OSError:
        return False


def _wait_ready(timeout: float = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_up():
            return True
        time.sleep(0.2)
    return False


ERROR_PAGE = """<body style="background:#0d0e12;color:#e8eaf0;font-family:Segoe UI,sans-serif;padding:60px">
<h2>Clipper n'a pas réussi à démarrer son moteur</h2>
<p>Le détail de l'erreur est dans le journal :</p><pre style="color:#ffe500">{log}</pre></body>"""


def main() -> None:
    ap = argparse.ArgumentParser(prog="clipper")
    ap.add_argument("--no-window", action="store_true", help="serveur seul (ouvrir l'URL dans un navigateur)")
    args = ap.parse_args()

    import webview

    window_opts = dict(width=1440, height=900, min_size=(1100, 700), background_color="#0d0e12")
    if _is_up():  # Clipper tourne déjà : on rouvre juste une fenêtre dessus
        webview.create_window("Clipper", f"http://{HOST}:{PORT}", **window_opts)
        webview.start()
        return

    jobs.start()
    watcher.start()
    if args.no_window:
        print(f"Clipper sur http://{HOST}:{PORT}")
        _serve()
        return

    threading.Thread(target=_serve, daemon=True).start()
    if _wait_ready():
        webview.create_window("Clipper", f"http://{HOST}:{PORT}", **window_opts)
    else:
        webview.create_window("Clipper", html=ERROR_PAGE.format(log=LOG_FILE), **window_opts)
    webview.start()


if __name__ == "__main__":
    main()
