"""API HTTP locale consommée par l'interface (http://127.0.0.1:8765)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import games, jobs, library, media, pipeline, watcher
from .config import UI_DIST, Settings
from .render.subtitles import join_words

app = FastAPI(title="Clipper")


def _video_or_404(vid: str) -> dict:
    v = library.get_video(vid)
    if not v:
        raise HTTPException(404, "Vidéo inconnue")
    return v


def _save_analysis(vid: str, analysis: dict) -> None:
    (pipeline.work_dir(vid) / "analysis.json").write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")


# ---------- réglages & jeux

@app.get("/api/settings")
def get_settings():
    return Settings.load().__dict__


@app.put("/api/settings")
def put_settings(patch: dict):
    before = Settings.load().watch_folders
    s = Settings.load().update(patch)
    if s.watch_folders != before:
        watcher.start()
    return s.__dict__


@app.get("/api/games")
def get_games():
    return games.list_games()


# ---------- bibliothèque

@app.get("/api/videos")
def get_videos():
    return library.list_videos()


@app.get("/api/inbox")
def inbox():
    """Fichiers présents dans les dossiers surveillés mais pas encore dans la bibliothèque."""
    known = {v["path"] for v in library.list_videos()}
    out = []
    for folder in Settings.load().watch_folders:
        if Path(folder).is_dir():
            for p in watcher.scan_existing(folder):
                if str(p) not in known:
                    st = p.stat()
                    out.append({"path": str(p), "name": p.name, "size": st.st_size, "mtime": st.st_mtime})
    return sorted(out, key=lambda f: -f["mtime"])[:60]


class ImportBody(BaseModel):
    path: str
    game: str | None = None
    analyze: bool = True


@app.post("/api/videos")
def import_video(body: ImportBody):
    p = Path(body.path)
    if not p.exists():
        raise HTTPException(400, "Fichier introuvable")
    v = watcher.register(p, auto=False)
    if v is None:
        raise HTTPException(400, "Format vidéo non pris en charge")
    if body.game:
        library.update_video(v["id"], game=body.game)
    if body.analyze:
        jobs.enqueue("analyze", v["id"])
    return library.get_video(v["id"])


@app.get("/api/videos/{vid}")
def get_video(vid: str):
    v = _video_or_404(vid)
    return {"video": v, "analysis": pipeline.load_analysis(vid), "renders": library.list_renders(vid)}


@app.delete("/api/videos/{vid}")
def delete_video(vid: str):
    library.delete_video(vid)
    return {"ok": True}


class GameBody(BaseModel):
    game: str


@app.post("/api/videos/{vid}/game")
def set_game(vid: str, body: GameBody):
    _video_or_404(vid)
    library.update_video(vid, game=body.game)
    if pipeline.load_analysis(vid):
        res = pipeline.rescore(vid, Settings.load(), body.game)
        jobs._after_analysis(vid, res)  # noqa: SLF001
        # l'OCR dépend des zones du jeu : un vrai changement de jeu demande une ré-analyse
        return {"rescored": True, "needs_reanalyze": True}
    return {"rescored": False}


@app.post("/api/videos/{vid}/analyze")
def analyze(vid: str):
    _video_or_404(vid)
    return {"queued": jobs.enqueue("analyze", vid)}


@app.post("/api/videos/{vid}/rescore")
def rescore(vid: str):
    res = pipeline.rescore(vid, Settings.load())
    jobs._after_analysis(vid, res)  # noqa: SLF001
    return res


class MomentPatch(BaseModel):
    start: float | None = None
    end: float | None = None
    hook: str | None = None
    excluded: bool | None = None


@app.patch("/api/videos/{vid}/moments/{mid}")
def patch_moment(vid: str, mid: int, body: MomentPatch):
    analysis = pipeline.load_analysis(vid)
    m = next((m for m in analysis["moments"] if m["id"] == mid), None)
    if not m:
        raise HTTPException(404, "Moment inconnu")
    m.update(body.model_dump(exclude_none=True))
    _save_analysis(vid, analysis)
    return m


class NewMoment(BaseModel):
    start: float
    end: float
    hook: str = "Moment fort"


@app.post("/api/videos/{vid}/moments")
def add_moment(vid: str, body: NewMoment):
    raw = pipeline.load_raw(vid)
    raw.setdefault("manual_moments", []).append(
        {"start": body.start, "end": body.end, "score": 99, "title": body.hook, "hook": body.hook, "peak": body.start})
    pipeline.save_raw(vid, raw)
    return pipeline.rescore(vid, Settings.load())


class Bookmark(BaseModel):
    t: float


@app.post("/api/videos/{vid}/bookmarks")
def add_bookmark(vid: str, body: Bookmark):
    raw = pipeline.load_raw(vid)
    raw.setdefault("bookmarks", []).append(body.t)
    pipeline.save_raw(vid, raw)
    return pipeline.rescore(vid, Settings.load())


class WordEdit(BaseModel):
    segment: int
    word: int
    text: str


@app.put("/api/videos/{vid}/words")
def edit_word(vid: str, body: WordEdit):
    """Correction d'un mot de sous-titre (conservée dans les deux fichiers d'analyse)."""
    for loader, saver in ((pipeline.load_raw, pipeline.save_raw),
                          (pipeline.load_analysis, lambda v, a: _save_analysis(v, a))):
        data = loader(vid)
        seg = data["segments"][body.segment]
        seg["words"][body.word]["word"] = body.text
        seg["text"] = join_words([w["word"] for w in seg["words"]])
        saver(vid, data)
    return {"ok": True}


class RenderBody(BaseModel):
    moment_ids: list[int] | None = None
    montage: bool = False


@app.post("/api/videos/{vid}/render")
def render(vid: str, body: RenderBody):
    _video_or_404(vid)
    return {"queued": jobs.enqueue("render", vid, moment_ids=body.moment_ids, montage=body.montage)}


# ---------- fichiers

@app.get("/media/source/{vid}")
def media_source(vid: str):
    return FileResponse(_video_or_404(vid)["path"])


@app.get("/media/thumb/{vid}")
def media_thumb(vid: str, t: float | None = None):
    """Vignette JPEG mise en cache : à `t`, sinon au meilleur moment, sinon à 15 % de la vidéo."""
    v = _video_or_404(vid)
    if t is None:
        analysis = pipeline.load_analysis(vid)
        best = max(analysis["moments"], key=lambda m: m["score"], default=None) if analysis else None
        t = best["peak"] if best else (v["duration"] or 60) * 0.15
    out = pipeline.work_dir(vid) / f"thumb_{int(t * 10)}.jpg"
    if not out.exists():
        try:
            media.thumbnail(v["path"], t, out, width=480)
        except Exception as exc:  # fichier déplacé, ou instant au-delà de la fin
            raise HTTPException(404, "Vignette indisponible") from exc
    return FileResponse(out, headers={"Cache-Control": "max-age=86400"})


@app.get("/media/file")
def media_file(path: str):
    p = Path(path)
    out_root = Path(Settings.load().output_folder).resolve()
    if not p.resolve().is_relative_to(out_root) or not p.exists():
        raise HTTPException(403, "Accès refusé")
    return FileResponse(p)


class OpenBody(BaseModel):
    path: str


@app.post("/api/reveal")
def reveal(body: OpenBody):
    p = Path(body.path)
    target = p if p.is_dir() else p.parent
    if target.exists():
        os.startfile(target)  # noqa: S606 — ouvre l'Explorateur Windows
    return {"ok": True}


if UI_DIST.exists():
    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
