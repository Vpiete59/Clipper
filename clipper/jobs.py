"""File de tâches GPU : une seule tâche à la fois (analyse ou rendu)."""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path

from . import library, pipeline
from .config import Settings
from .render import build_montage, render_clip
from .render.story import render_story

_queue: queue.Queue = queue.Queue()
_pending: set[tuple] = set()
_lock = threading.Lock()

STAGE_WEIGHTS = {"audio": (0.0, 0.02), "voix": (0.02, 0.15), "transcription": (0.15, 0.45), "sons": (0.45, 0.58),
                 "image": (0.58, 0.97), "moments": (0.97, 1.0)}


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


def _render_kwargs(settings: Settings, analysis: dict) -> dict:
    portrait = analysis["orientation"] == "portrait"
    return dict(orientation=analysis["orientation"], layout=settings.layout, facecam=settings.facecam_rect,
                subtitle_style=settings.subtitle_style,
                subtitle_y=settings.subtitle_y_portrait if portrait else settings.subtitle_y, fps=analysis["fps"])


def _render(vid: str, moment_ids: list[int] | None = None, montage: bool = False,
            match_ids: list[int] | None = None) -> None:
    """Clips des moments choisis, puis (si `montage`) un short récap par partie détectée.

    `match_ids` seul : uniquement les résumés de ces parties, sans re-rendre les clips.
    """
    settings = Settings.load()
    analysis = pipeline.load_analysis(vid)
    v = library.get_video(vid)
    kwargs = _render_kwargs(settings, analysis)
    if match_ids is not None:
        moments = []
    elif moment_ids is None:
        moments = [m for m in analysis["moments"] if not m.get("excluded")]
    else:
        moments = [m for m in analysis["moments"] if m["id"] in moment_ids]
    matches = [m for m in analysis.get("matches", []) if (match_ids is None and montage) or (match_ids and m["id"] in match_ids)]
    out_dir = output_dir(vid)
    total = len(moments) + len(matches) + (1 if montage and not analysis.get("matches") else 0)
    library.update_video(vid, status="rendering", stage="rendu", progress=0)
    rendered = []
    for i, m in enumerate(moments):
        path = render_clip(
            v["path"], m, analysis["segments"], out_dir / f"clip_{m['id']:02d}.mp4",
            effects=settings.effects, hook=m.get("hook", m["title"]),
            quiet=pipeline.quiet_mask(vid, analysis["segments"], m["start"], m["end"]), **kwargs,
        )
        library.add_render(vid, m["id"], "clip", str(path))
        rendered.append((m["score"], path))
        library.update_video(vid, progress=round((i + 1) / max(1, total), 3))

    for k, match in enumerate(matches):
        library.update_video(vid, stage="montage")
        path = render_story(
            v["path"], match, analysis, out_dir / f"partie_{match['id'] + 1:02d}.mp4",
            render_kwargs=kwargs, effects=settings.effects,
            quiet=lambda a, b: pipeline.quiet_mask(vid, analysis["segments"], a, b),
        )
        library.add_render(vid, match["id"], "story", str(path))
        library.update_video(vid, progress=round((len(moments) + k + 1) / max(1, total), 3))

    # pas de partie reconnue (autre jeu, extrait court) : best-of classique des clips
    if montage and not analysis.get("matches") and len(rendered) > 1:
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
