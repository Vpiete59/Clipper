"""Short récapitulatif d'une partie : chapitres dans l'ordre, titres, compteur de kills, whoosh, barre de progression.

Chaque chapitre (indice, combat, boss, prime, extraction…) est rendu comme un clip court
avec son titre en accroche, puis tout est enchaîné par le monteur de montage.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from ..media import FFMPEG, NO_WINDOW, probe
from ..scoring import snap_chapters
from .montage import build_montage
from .vertical import render_clip



def _moment(analysis: dict, start: float, end: float, peak: float, hook: str) -> dict:
    events = [e for e in analysis["events"] if start <= e["t"] <= end and e.get("highlight", True)]
    return {"start": start, "end": end, "peak": peak, "hook": hook, "title": hook, "events": events}


def render_story(
    source: str,
    match: dict,
    analysis: dict,
    out_path: Path,
    *,
    render_kwargs: dict,
    effects: dict,
    quiet: Callable[[float, float], list[bool]],
    progress: Callable[[float], None] | None = None,
    title_style: str = "center",
) -> Path:
    # jamais de coupure au milieu d'une phrase, ni au début ni à la fin d'un chapitre
    chapters = snap_chapters(match["chapters"], analysis["segments"], match["start"], match["end"])
    if not chapters:
        raise ValueError("Aucun chapitre dans cette partie")
    work = out_path.parent / f"_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    chapter_fx = {**effects, "teaser": False, "progress_bar": False, "hook_title": True}
    clips: list[Path] = []

    # pas de teaser : le résumé raconte la partie dans l'ordre, du premier indice à la sortie
    kill_times = sorted({k for c in chapters for k in c.get("kills", [])})
    for i, c in enumerate(chapters, start=1):
        m = _moment(analysis, c["start"], c["end"], c["t"], c["label"])
        kills = {"base": sum(1 for k in kill_times if k < c["start"]), "times": kill_times} if kill_times else None
        clips.append(render_clip(source, m, analysis["segments"], work / f"c{i:02d}.mp4", effects=chapter_fx,
                                 hook=m["hook"], quiet=quiet(c["start"], c["end"]), title_style=title_style,
                                 kills=kills, **render_kwargs))
        if progress:
            progress(i / (len(chapters) + 1))

    joined = build_montage(clips, work / "joined.mp4")
    duration = probe(joined).duration
    vf = "null"
    if effects.get("progress_bar"):
        vf = f"drawbox=x=0:y=ih-12:w='iw*t/{duration:.3f}':h=12:color=0xFFE500@0.95:t=fill"
    res = subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-i", str(joined), "-vf", vf, "-c:v", "h264_nvenc", "-preset", "p5",
         "-rc", "vbr", "-cq", "23", "-b:v", "10M", "-maxrate", "14M", "-bufsize", "28M", "-c:a", "copy",
         "-movflags", "+faststart", str(out_path)],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg (résumé) a échoué : {res.stderr[-1500:]}")
    shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0)
    return out_path
