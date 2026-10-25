"""File de tâches GPU : une seule tâche à la fois (analyse ou rendu).

On peut la mettre en pause (le travail en cours se termine, rien d'autre ne démarre),
retirer une vidéo de la file, ou annuler le travail en cours : il s'arrête au prochain
point de contrôle (chaque étape d'analyse, chaque clip rendu).
"""

from __future__ import annotations

import threading
import traceback
from pathlib import Path

from . import games, library, pipeline, scoring
from .config import DATA_DIR, Settings
from .render import build_montage, render_clip
from .render.longform import render_longform
from .render.story import render_story

_items: list[tuple] = []  # (clé, type, vidéo, options) en attente, dans l'ordre
_running: dict | None = None
_cancel = threading.Event()
_cond = threading.Condition()
PAUSE_FLAG = DATA_DIR / "queue_paused"  # la pause survit à un redémarrage de l'app

STAGE_WEIGHTS = {"audio": (0.0, 0.02), "voix": (0.02, 0.15), "transcription": (0.15, 0.45), "sons": (0.45, 0.58),
                 "image": (0.58, 0.97), "moments": (0.97, 1.0)}


class JobCancelled(Exception):
    pass


def _check() -> None:
    if _cancel.is_set():
        raise JobCancelled()


def is_paused() -> bool:
    return PAUSE_FLAG.exists()


def set_paused(paused: bool) -> None:
    with _cond:
        if paused:
            PAUSE_FLAG.touch()
        else:
            PAUSE_FLAG.unlink(missing_ok=True)
        _cond.notify_all()


def enqueue(kind: str, vid: str, **kwargs) -> bool:
    key = (kind, vid, tuple(sorted((k, str(v)) for k, v in kwargs.items())))
    with _cond:
        if any(item[0] == key for item in _items) or (_running and _running["key"] == key):
            return False
        _items.append((key, kind, vid, kwargs))
        _cond.notify_all()
    library.update_video(vid, status="queued" if kind == "analyze" else "rendering_queued", error=None)
    return True


def _restore_status(vid: str) -> None:
    """Après retrait ou annulation : la vidéo retrouve l'état de ce qui est déjà fait."""
    if library.get_video(vid) is None:
        return
    if pipeline.load_analysis(vid) is None:
        library.update_video(vid, status="new", stage=None, progress=0)
    else:
        library.update_video(vid, status="done" if library.list_renders(vid) else "analyzed", stage=None, progress=1)


def remove(vid: str) -> bool:
    """Retire la vidéo de la file ; si elle est en cours de traitement, l'annule."""
    with _cond:
        before = len(_items)
        _items[:] = [it for it in _items if it[2] != vid]
        removed = len(_items) != before
        running = _running is not None and _running["vid"] == vid
        if running:
            _cancel.set()
    if removed and not running:
        _restore_status(vid)
    return removed or running


def clear() -> int:
    """Vide la file d'attente (le travail en cours continue)."""
    with _cond:
        vids = {it[2] for it in _items}
        _items.clear()
    for vid in vids:
        if not (_running and _running["vid"] == vid):
            _restore_status(vid)
    return len(vids)


def snapshot() -> dict:
    with _cond:
        return {
            "paused": is_paused(),
            "running": {"vid": _running["vid"], "kind": _running["kind"]} if _running else None,
            "pending": [{"vid": it[2], "kind": it[1]} for it in _items],
        }


def _analyze(vid: str, resume: bool = True) -> None:
    v = library.get_video(vid)
    settings = Settings.load()

    def progress(stage: str, p: float) -> None:
        _check()
        a, b = STAGE_WEIGHTS.get(stage, (0, 1))
        library.update_video(vid, stage=stage, progress=round(a + (b - a) * p, 3))

    library.update_video(vid, status="analyzing", progress=0)
    result = pipeline.analyze(v["path"], v["game"], settings, progress, resume=resume)
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
    # noms propres du jeu (Boucher, Bayou, Mosin…) : mis en valeur dans les sous-titres
    vocab = {w.lower() for v in games.load(analysis["game"]).get("vocabulary", []) for w in v.split() if len(w) > 2}
    return dict(orientation=analysis["orientation"], layout=settings.layout, facecam=settings.facecam_rect,
                subtitle_style=settings.subtitle_style,
                subtitle_y=settings.subtitle_y_portrait if portrait else settings.subtitle_y, fps=analysis["fps"],
                emphasis=vocab)


def _render_longform(vid: str, match_ids: list[int]) -> None:
    """Vidéo longue YouTube 16:9 des parties choisies (+ chapitres, .srt, miniature)."""
    analysis = pipeline.load_analysis(vid)
    v = library.get_video(vid)
    out_dir = output_dir(vid)
    game_name = games.load(analysis["game"])["name"]
    matches = [m for m in analysis.get("matches", []) if m["id"] in match_ids]
    library.update_video(vid, status="rendering", stage="longue", progress=0)
    for k, m in enumerate(matches):
        _check()
        inside = [e for e in analysis["events"] if m["start"] <= e["t"] <= m["end"]]
        wide = {**m, "chapters": scoring.build_chapters(inside, m["start"], m["end"], m["outcome"], "longform")}
        files = render_longform(v["path"], wide, analysis, out_dir / f"youtube_partie_{m['id'] + 1:02d}.mp4", game_name=game_name)
        library.add_render(vid, m["id"], "longform", str(files["video"]))
        library.update_video(vid, progress=round((k + 1) / len(matches), 3))
    library.update_video(vid, status="done", stage=None, progress=1)


def _render(vid: str, moment_ids: list[int] | None = None, montage: bool = False,
            match_ids: list[int] | None = None, longform: bool = False) -> None:
    """Clips des moments choisis, puis (si `montage`) un short récap par partie détectée.

    `match_ids` seul : uniquement les résumés de ces parties, sans re-rendre les clips.
    """
    if longform:
        return _render_longform(vid, match_ids or [m["id"] for m in pipeline.load_analysis(vid).get("matches", [])])
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
    if match_ids is None and settings.story_only_worth:
        # rendu automatique : pas de résumé pour une partie perdue sans action
        matches = [m for m in matches if m.get("worth", True)]
    out_dir = output_dir(vid)
    total = len(moments) + len(matches) + (1 if montage and not analysis.get("matches") else 0)
    library.update_video(vid, status="rendering", stage="rendu", progress=0)
    rendered = []
    for i, m in enumerate(moments):
        _check()
        path = render_clip(
            v["path"], m, analysis["segments"], out_dir / f"clip_{m['id']:02d}.mp4",
            effects=settings.effects, hook=m.get("hook", m["title"]),
            quiet=pipeline.quiet_mask(vid, analysis["segments"], m["start"], m["end"]), **kwargs,
        )
        library.add_render(vid, m["id"], "clip", str(path))
        rendered.append((m["start"], path))
        library.update_video(vid, progress=round((i + 1) / max(1, total), 3))

    for k, match in enumerate(matches):
        _check()
        library.update_video(vid, stage="montage")
        path = render_story(
            v["path"], match, analysis, out_dir / f"partie_{match['id'] + 1:02d}.mp4",
            render_kwargs=kwargs, effects=settings.effects,
            quiet=lambda a, b: pipeline.quiet_mask(vid, analysis["segments"], a, b),
            progress=lambda p: _check(), title_style=settings.title_style,
        )
        library.add_render(vid, match["id"], "story", str(path))
        library.update_video(vid, progress=round((len(moments) + k + 1) / max(1, total), 3))

    # pas de partie reconnue (autre jeu, extrait court) : best-of classique des clips
    if montage and not analysis.get("matches") and len(rendered) > 1:
        library.update_video(vid, stage="montage")
        clips = [p for _, p in sorted(rendered, key=lambda x: x[0])]  # ordre de la partie, pas du score
        path = build_montage(clips, out_dir / "montage.mp4")
        library.add_render(vid, None, "montage", str(path))
    library.update_video(vid, status="done", stage=None, progress=1)


def _worker() -> None:
    global _running
    while True:
        with _cond:
            while not _items or is_paused():
                _cond.wait(timeout=2)
            key, kind, vid, kwargs = _items.pop(0)
            _running = {"key": key, "kind": kind, "vid": vid}
            _cancel.clear()
        try:
            if kind == "analyze":
                _analyze(vid, **kwargs)
            elif kind == "render":
                _render(vid, **kwargs)
        except JobCancelled:
            _restore_status(vid)
        except Exception as exc:  # une vidéo en échec ne doit pas bloquer la file
            traceback.print_exc()
            library.update_video(vid, status="error", error=f"{type(exc).__name__}: {exc}"[:1000], stage=None)
        finally:
            with _cond:
                _running = None
                _cancel.clear()


def _short(path: str, settings: Settings) -> bool:
    from .media import probe

    try:
        return probe(path).duration < settings.auto_min_duration
    except Exception:
        return False


def start() -> None:
    threading.Thread(target=_worker, name="clipper-worker", daemon=True).start()
    # reprise après redémarrage : ce qui était en cours est remis en file (les étapes déjà faites sont gardées)
    settings = Settings.load()
    for v in library.list_videos():
        if v["status"] in ("queued", "analyzing"):
            # ajoutée automatiquement avant la règle de durée minimale (vidéo Kinevir…) : on ne la relance pas
            if v["status"] == "queued" and pipeline.load_analysis(v["id"]) is None and _short(v["path"], settings):
                library.update_video(v["id"], status="new", stage=None, progress=0)
                continue
            enqueue("analyze", v["id"])
        elif v["status"] in ("rendering", "rendering_queued"):
            enqueue("render", v["id"], montage=True)
