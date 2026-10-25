"""Miniatures YouTube 1280x720 : image la plus lisible d'un moment, gros texte, couleur au choix.

Utilisé automatiquement par la vidéo longue et la compilation, et par l'éditeur de
miniature de l'interface (texte, couleur, position et image choisis à la main).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ..media import FFMPEG, NO_WINDOW

COLORS = {"jaune": "0xFFE500", "rouge": "0xFF3B30", "blanc": "0xFFFFFF", "vert": "0x3DD68C", "orange": "0xFF8A1F"}
FONT = "C\\:/Windows/Fonts/impact.ttf"


def best_frame(source: str, t: float, span: float = 6.0) -> float:
    """Parmi les images autour de `t`, la plus lisible : assez claire, contrastée et colorée.
    Une miniature sombre (nuit, fumée, écran de mort) ne se clique pas."""
    start = max(0.0, t - span)
    w, h, fps = 160, 90, 2
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{start:.2f}", "-t", f"{span + 1:.2f}", "-i", source,
                          "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, creationflags=NO_WINDOW).stdout
    frames = np.frombuffer(raw, np.uint8)[: len(raw) // (w * h * 3) * w * h * 3].reshape(-1, h, w, 3).astype(np.float32)
    if not len(frames):
        return max(0.0, t - 0.5)
    luma = frames.mean(axis=3)
    sat = frames.max(axis=3) - frames.min(axis=3)
    score = luma.std(axis=(1, 2)) + 0.5 * sat.mean(axis=(1, 2)) - np.abs(luma.mean(axis=(1, 2)) - 115) * 0.6
    return start + int(np.argmax(score)) / fps


def make_thumbnail(source: str, t: float, out: Path, *, text: str, subtitle: str = "", color: str = "jaune",
                   position: str = "bas", boost: bool = True, size: int = 118) -> Path:
    """Image à l'instant `t` (déjà choisi), texte principal + petit texte, en 1280x720.

    `position` : « bas », « haut » ou « centre » pour le texte principal.
    """
    fill = COLORS.get(color, color if color.startswith("0x") else COLORS["jaune"])
    # le texte tient sur ~1050 px (Impact ≈ 0,5 × la taille par caractère) : un titre long rétrécit
    size = int(min(size, 1050 / (0.5 * max(1, len(text)))))
    y_main = {"haut": "60", "centre": "(h-th)/2", "bas": "h-th-70"}.get(position, "h-th-70")
    y_sub = "h-th-40" if position == "haut" else "50"
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        # les textes passent par des fichiers : « : » et « ' » cassent la syntaxe des filtres ffmpeg
        Path(tmp, "big.txt").write_text(text, encoding="utf-8")
        Path(tmp, "sub.txt").write_text(subtitle, encoding="utf-8")
        tmp_rel = Path(tmp).name
        vf = "scale=1280:720" + (",eq=saturation=1.35:contrast=1.12" if boost else "")
        vf += (f",drawtext=fontfile='{FONT}':textfile={tmp_rel}/big.txt:fontsize={size}:fontcolor={fill}:"
               f"borderw=10:bordercolor=black:x=60:y={y_main}")
        if subtitle:
            vf += (f",drawtext=fontfile='{FONT}':textfile={tmp_rel}/sub.txt:fontsize=46:fontcolor=white:"
                   f"borderw=6:bordercolor=black:x=64:y={y_sub}")
        res = subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", source,
                              "-frames:v", "1", "-vf", vf, "-q:v", "2", out.name],
                             cwd=out.parent, capture_output=True, text=True, creationflags=NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg (miniature) a échoué : {res.stderr[-800:]}")
    return out
