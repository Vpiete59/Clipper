"""Montage automatique : enchaîne les clips verticaux avec des transitions rapides et un whoosh.

Un seul teaser en ouverture (celui du meilleur clip) : les suivants démarrent après le leur,
sinon chaque clip rejouerait son « regarde ce qui va arriver ».
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..media import FFMPEG, NO_WINDOW, probe
from . import sfx

TRANSITIONS = ["slideup", "zoomin", "smoothleft", "fadewhite", "circleopen"]
XFADE = 0.3


def _teaser(clip: Path) -> float:
    meta = clip.with_suffix(".json")
    return json.loads(meta.read_text())["teaser"] if meta.exists() else 0.0


def build_montage(clips: list[Path], out_path: Path, whoosh: bool = True) -> Path:
    if not clips:
        raise ValueError("Aucun clip à assembler")
    if len(clips) == 1:
        out_path.write_bytes(clips[0].read_bytes())
        return out_path

    inputs: list[str] = []
    durations: list[float] = []
    for i, c in enumerate(clips):
        skip = _teaser(c) if i > 0 else 0.0
        if skip:
            inputs += ["-ss", f"{skip:.3f}"]
        inputs += ["-i", str(c)]
        durations.append(probe(c).duration - skip)

    parts, offset, cuts = [], 0.0, []
    prev_v, prev_a = "[0:v]", "[0:a]"
    for i in range(1, len(clips)):
        offset += durations[i - 1] - XFADE
        cuts.append(offset)
        tr = TRANSITIONS[(i - 1) % len(TRANSITIONS)]
        parts.append(f"[{i}:v]setpts=PTS-STARTPTS[in{i}];[{i}:a]asetpts=PTS-STARTPTS[ain{i}]")
        parts.append(f"{prev_v}[in{i}]xfade=transition={tr}:duration={XFADE}:offset={offset:.3f}[v{i}]")
        parts.append(f"{prev_a}[ain{i}]acrossfade=d={XFADE}[a{i}]")
        prev_v, prev_a = f"[v{i}]", f"[a{i}]"

    if whoosh:
        n = len(clips)
        mix = [prev_a]
        for k, at in enumerate(cuts):
            inputs += ["-i", str(sfx.path("whoosh"))]
            ms = max(0, int((at - 0.25) * 1000))
            parts.append(f"[{n + k}:a]adelay={ms}|{ms},volume=0.6[w{k}]")
            mix.append(f"[w{k}]")
        parts.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.95[aout]")
        prev_a = "[aout]"

    cmd = [FFMPEG, "-y", "-v", "error", *inputs, "-filter_complex", ";".join(parts),
           "-map", prev_v, "-map", prev_a, "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23",
           "-b:v", "10M", "-maxrate", "14M", "-bufsize", "28M",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg (montage) a échoué : {res.stderr[-1500:]}")
    return out_path
