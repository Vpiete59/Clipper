"""Effets sonores synthétisés par ffmpeg (aucun fichier sous droits) : whoosh de transition et impact."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..config import DATA_DIR
from ..media import FFMPEG, NO_WINDOW

SFX_DIR = DATA_DIR / "sfx"

RECIPES = {
    # souffle rose filtré qui monte puis retombe
    "whoosh": (["-f", "lavfi", "-i", "anoisesrc=d=0.6:c=pink:a=0.7"],
               "highpass=f=350,lowpass=f=5500,afade=t=in:d=0.38:curve=exp,afade=t=out:st=0.38:d=0.22,volume=1.6"),
    # basse sourde + craquement court, comme un coup de poing dans le mix
    "impact": (["-f", "lavfi", "-i", "sine=f=52:d=0.7", "-f", "lavfi", "-i", "anoisesrc=d=0.12:c=brown:a=0.9"],
               "[0]afade=t=out:st=0.04:d=0.66:curve=exp,volume=2.4[a];[1]lowpass=f=1100,afade=t=out:d=0.12[b];"
               "[a][b]amix=inputs=2:normalize=0,alimiter=limit=0.9"),
}


def path(name: str) -> Path:
    """Génère le son au premier usage puis le garde en cache."""
    SFX_DIR.mkdir(exist_ok=True)
    out = SFX_DIR / f"{name}.wav"
    if not out.exists():
        inputs, graph = RECIPES[name]
        flag = "-filter_complex" if ";" in graph else "-af"
        subprocess.run([FFMPEG, "-y", "-v", "error", *inputs, flag, graph, "-ac", "2", "-ar", "48000", str(out)],
                       check=True, creationflags=NO_WINDOW)
    return out
