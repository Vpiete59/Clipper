"""Montage automatique : enchaîne les clips verticaux avec des transitions rapides."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..media import FFMPEG, NO_WINDOW, probe

TRANSITIONS = ["slideup", "zoomin", "smoothleft", "fadewhite", "circleopen"]
XFADE = 0.3


def build_montage(clips: list[Path], out_path: Path) -> Path:
    if not clips:
        raise ValueError("Aucun clip à assembler")
    if len(clips) == 1:
        out_path.write_bytes(clips[0].read_bytes())
        return out_path
    durations = [probe(c).duration for c in clips]
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    parts, offset = [], 0.0
    prev_v, prev_a = "[0:v]", "[0:a]"
    for i in range(1, len(clips)):
        offset += durations[i - 1] - XFADE
        tr = TRANSITIONS[(i - 1) % len(TRANSITIONS)]
        parts.append(f"{prev_v}[{i}:v]xfade=transition={tr}:duration={XFADE}:offset={offset:.3f}[v{i}]")
        parts.append(f"{prev_a}[{i}:a]acrossfade=d={XFADE}[a{i}]")
        prev_v, prev_a = f"[v{i}]", f"[a{i}]"
    cmd = [FFMPEG, "-y", "-v", "error", *inputs, "-filter_complex", ";".join(parts),
           "-map", prev_v, "-map", prev_a, "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "10M", "-maxrate", "14M", "-bufsize", "28M",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg (montage) a échoué : {res.stderr[-1500:]}")
    return out_path
