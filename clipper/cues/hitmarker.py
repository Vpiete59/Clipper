"""Marqueur de touche de Hunt : le « X » blanc (4 traits en diagonale) au centre de l'écran.

Il n'apparaît que ~0,25 s quand une balle touche un joueur ; le réticule normal, lui, est
fait de traits horizontaux et verticaux. On ne regarde que le centre de l'image, et
seulement autour des combats déjà repérés à l'oreille : quelques minutes de vidéo à décoder.
"""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ..media import FFMPEG, NO_WINDOW

SIZE = 64  # carré analysé, en pixels d'une image 1080p
FPS = 15   # le X reste ~4 images à 60 i/s : 15 i/s en attrape au moins deux


def _score(frames: np.ndarray) -> np.ndarray:
    """Contraste entre les 4 diagonales (le X) et les directions intermédiaires, par image."""
    c = SIZE // 2
    diag, off = [], []
    for r in range(7, 18):
        for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            diag.append((c + sy * r, c + sx * r))
        for a in np.deg2rad(np.arange(22.5, 360, 45)):
            off.append((int(round(c + np.sin(a) * r * 1.41)), int(round(c + np.cos(a) * r * 1.41))))
    d = np.median(frames[:, [y for y, _ in diag], [x for _, x in diag]], axis=1)
    o = np.median(frames[:, [y for y, _ in off], [x for _, x in off]], axis=1)
    return np.where(d > 150, d - o, 0)


def _scan_window(source: str, a: float, b: float) -> list[float]:
    side = f"ih*{SIZE}/1080"
    raw = subprocess.run(
        [FFMPEG, "-v", "error", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}", "-i", source, "-an",
         "-vf", f"fps={FPS},crop={side}:{side}:(iw-{side})/2:(ih-{side})/2,scale={SIZE}:{SIZE},format=gray",
         "-f", "rawvideo", "-"], capture_output=True, creationflags=NO_WINDOW).stdout
    n = len(raw) // (SIZE * SIZE)
    if not n:
        return []
    frames = np.frombuffer(raw[: n * SIZE * SIZE], np.uint8).reshape(n, SIZE, SIZE).astype(np.float32)
    out: list[float] = []
    for i in np.flatnonzero(_score(frames) > 90):
        t = round(a + i / FPS, 2)
        if not out or t - out[-1] > 0.4:  # un même X vu sur deux images
            out.append(t)
    return out


def scan(source: str, windows: list[tuple[float, float]], cache: Path) -> list[float]:
    """Instants des marqueurs de touche dans `windows`, mémorisés par fenêtre dans `cache`."""
    done: dict[str, list[float]] = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [(a, b) for a, b in windows if f"{a:.1f}-{b:.1f}" not in done]
    if todo:
        with ThreadPoolExecutor(4) as pool:
            for (a, b), found in zip(todo, pool.map(lambda w: _scan_window(source, *w), todo)):
                done[f"{a:.1f}-{b:.1f}"] = found
        cache.write_text(json.dumps(done))
    return sorted({t for a, b in windows for t in done[f"{a:.1f}-{b:.1f}"]})


def windows_around(times: list[float], pad: float = 12.0) -> list[tuple[float, float]]:
    """Fenêtres fusionnées de ±`pad` s autour des sons de combat, calées sur une grille de 5 s
    pour que le cache serve encore quand un seuil bouge un peu."""
    out: list[list[float]] = []
    for t in sorted(times):
        a, b = max(0.0, (t - pad) // 5 * 5), (t + pad) // 5 * 5 + 5
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]
