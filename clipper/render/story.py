"""Short récapitulatif d'une partie : cold open, chapitres dans l'ordre, whoosh, barre de progression.

Chaque chapitre (indice, combat, boss, prime, extraction…) est rendu comme un clip court
avec son titre en accroche, puis tout est enchaîné par le monteur de montage.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from ..media import FFMPEG, NO_WINDOW, probe
from .montage import build_montage
from .vertical import render_clip

COLD_OPEN = {"extracted": "On s'en sort ?", "dead": "Ça finit mal…", "unknown": "Partie de Hunt"}
OPENING_PRIORITY = ["pvp_fight", "bounty", "boss_down", "extracted", "gunfight"]


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
) -> Path:
    chapters = match["chapters"]
    if not chapters:
        raise ValueError("Aucun chapitre dans cette partie")
    work = out_path.parent / f"_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    chapter_fx = {**effects, "teaser": False, "progress_bar": False, "hook_title": True}
    clips: list[Path] = []

    # cold open : 1,8 s du moment le plus fort, avant de tout reprendre depuis le début
    best = next((c for kind in OPENING_PRIORITY for c in chapters if c["type"] == kind), None)
    if best and effects.get("teaser", True):
        peak = best["t"] if best["type"] != "pvp_fight" else best["t"] - 0.2
        m = _moment(analysis, max(0.0, peak - 1.8), peak, peak, COLD_OPEN[match["outcome"]])
        m["events"] = []
        clips.append(render_clip(source, m, analysis["segments"], work / "c00.mp4",
                                 effects={**chapter_fx, "speed_ramp": False, "slowmo": False}, hook=m["hook"], **render_kwargs))

    for i, c in enumerate(chapters, start=1):
        m = _moment(analysis, c["start"], c["end"], c["t"], c["label"])
        clips.append(render_clip(source, m, analysis["segments"], work / f"c{i:02d}.mp4", effects=chapter_fx, hook=m["hook"],
                                 quiet=quiet(c["start"], c["end"]), **render_kwargs))
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
