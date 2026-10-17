"""File de tâches GPU : une seule tâche à la fois (analyse ou rendu)."""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path

from . import library, pipeline
from .config import Settings
from .render import build_montage, render_clip

_queue: queue.Queue = queue.Queue()
_pending: set[tuple] = set()
_lock = threading.Lock()

STAGE_WEIGHTS = {"audio": (0.0, 0.03), "transcription": (0.03, 0.40), "sons": (0.40, 0.55),
                 "image": (0.55, 0.97), "moments": (0.97, 1.0)}


def enqueue(kind: str, vid: str, **kwargs) -> bool:
    key = (kind, vid, tuple(sorted((k, str(v)) for k, v in kwargs.items())))
    with _lock:
        if key in _pending:
            return False
        _pending.add(key)
    library.update_video(vid, status="queued" if kind == "analyze" else "rendering_queued", error=None)
    _queue.put((key, kind, vid, kwargs))
    return True


def _analyze(vid: str) -> None:
    v = library.get_video(vid)
    settings = Settings.load()

    def progress(stage: str, p: float) -> None:
        a, b = STAGE_WEIGHTS.get(stage, (0, 1))
        library.update_video(vid, stage=stage, progress=round(a + (b - a) * p, 3))

    library.update_video(vid, status="analyzing", progress=0)
    result = pipeline.analyze(v["path"], v["game"], settings, progress)
    _after_analysis(vid, result)
    if settings.auto_process and result["moments"]:
        enqueue("render", vid, montage=True)


def _after_analysis(vid: str, result: dict) -> None:
    moments = result["moments"]
    library.update_video(vid, status="analyzed", stage=None, progress=1, duration=result["duration"],
                         orientation=result["orientation"], game=result["game"], n_moments=len(moments),
                         best_score=max((m["score"] for m in moments), default=0))


def output_dir(vid: str) -> Path:
    v = library.get_video(vid)
    return Path(Settings.load().output_folder) / v["name"]


def _render(vid: str, moment_ids: list[int] | None = None, montage: bool = False) -> None:
    settings = Settings.load()
    analysis = pipeline.load_analysis(vid)
    v = library.get_video(vid)
    if moment_ids is None:
        moments = [m for m in analysis["moments"] if not m.get("excluded")]
    else:
        moments = [m for m in analysis["moments"] if m["id"] in moment_ids]
    out_dir = output_dir(vid)
    library.update_video(vid, status="rendering", stage="rendu", progress=0)
    rendered = []
    for i, m in enumerate(moments):
        path = render_clip(
            v["path"], m, analysis["segments"], out_dir / f"clip_{m['id']:02d}.mp4",
            orientation=analysis["orientation"], layout=settings.layout, facecam=settings.facecam_rect,
            effects=settings.effects, subtitle_style=settings.subtitle_style, subtitle_y=settings.subtitle_y_portrait if analysis["orientation"] == "portrait" else settings.subtitle_y,
            hook=m.get("hook", m["title"]), fps=analysis["fps"],
        )
        library.add_render(vid, m["id"], "clip", str(path))
        rendered.append((m["score"], path))
        library.update_video(vid, progress=round((i + 1) / (len(moments) + (1 if montage else 0)), 3))
    if montage and len(rendered) > 1:
        library.update_video(vid, stage="montage")
        clips = [p for _, p in sorted(rendered, key=lambda x: -x[0])]
        path = build_montage(clips, out_dir / "montage.mp4")
        library.add_render(vid, None, "montage", str(path))
    library.update_video(vid, status="done", stage=None, progress=1)


def _worker() -> None:
    while True:
        key, kind, vid, kwargs = _queue.get()
        try:
            if kind == "analyze":
                _analyze(vid)
            elif kind == "render":
                _render(vid, **kwargs)
        except Exception as exc:  # une vidéo en échec ne doit pas bloquer la file
            traceback.print_exc()
            library.update_video(vid, status="error", error=f"{type(exc).__name__}: {exc}"[:1000], stage=None)
        finally:
            with _lock:
                _pending.discard(key)
            _queue.task_done()


def start() -> None:
    threading.Thread(target=_worker, name="clipper-worker", daemon=True).start()
    # reprise après redémarrage : ce qui était en cours est remis en file
    for v in library.list_videos():
        if v["status"] in ("queued", "analyzing"):
            enqueue("analyze", v["id"])
        elif v["status"] in ("rendering", "rendering_queued"):
            enqueue("render", v["id"], montage=True)
