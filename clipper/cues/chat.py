"""Signal du chat Twitch : un pic de messages = un moment qui a fait réagir les viewers.

Clipper ne va pas chercher le chat lui-même. Il lit le fichier que tu poses à côté de la
vidéo : export JSON de TwitchDownloader (« Chat Download »), ou un journal texte
« [0:12:34] pseudo: message ». Nom attendu : même nom que la vidéo, ou contenant « chat ».
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import STEP

HYPE = re.compile(r"(?i)\b(pog\w*|kek\w*|lul\w*|omega\w*|gg+|ez|wtf|xd+|mdr+|ptdr+|lol+|clip+|w+|l+|\?{2,}|!{2,})\b")


def find_chat_file(video: Path) -> Path | None:
    candidates = [video.with_suffix(".json"), video.with_suffix(".txt"), video.with_name(video.stem + "_chat.json")]
    candidates += sorted(video.parent.glob(f"*{video.stem.split('-')[0]}*chat*.*"))
    for c in candidates:
        if c.exists() and c.suffix.lower() in (".json", ".txt") and c != video:
            return c
    return None


def _parse_time(s: str) -> float:
    parts = [float(p) for p in s.split(":")]
    return sum(p * 60 ** i for i, p in enumerate(reversed(parts)))


def load_messages(path: Path) -> list[tuple[float, str]]:
    """[(secondes depuis le début de la VOD, message)]."""
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        comments = data.get("comments", data if isinstance(data, list) else [])
        out = []
        for c in comments:
            t = c.get("content_offset_seconds", c.get("offset"))
            body = (c.get("message") or {}).get("body") if isinstance(c.get("message"), dict) else c.get("message", "")
            if t is not None:
                out.append((float(t), body or ""))
        return out
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"\s*\[?(\d+:\d{2}(?::\d{2})?)\]?\s*[^:]+:\s*(.*)", line)
        if m:
            out.append((_parse_time(m.group(1)), m.group(2)))
    return out


def chat_signals(messages: list[tuple[float, str]], duration: float) -> dict[str, np.ndarray]:
    """`chat_rate` : messages/s lissés ; `chat_spike` (0-1) : écart au rythme habituel du chat.

    Le chat a du retard sur l'action (le temps de réagir et de taper) : on décale de 6 s.
    """
    n = int(np.ceil(duration / STEP))
    rate = np.zeros(n, dtype=np.float32)
    hype = np.zeros(n, dtype=np.float32)
    for t, body in messages:
        i = int((t - 6.0) / STEP)
        if 0 <= i < n:
            rate[i] += 1
            if HYPE.search(body or ""):
                hype[i] += 1
    win = int(4 / STEP)
    kernel = np.ones(win) / 4.0
    rate_s = np.convolve(rate, kernel, mode="same")
    hype_s = np.convolve(hype, kernel, mode="same")
    # rythme habituel du chat sur 5 min : un pic = bien au-dessus de ce rythme
    long = int(300 / STEP)
    padded = np.pad(rate_s, (long // 2, long // 2), mode="edge")
    base = np.array([np.median(padded[i:i + long]) for i in range(0, n)], dtype=np.float32) if n else rate_s
    # en messages par fenêtre de 4 s : le hasard donne λ ± √λ, un pic doit sortir largement de là
    count, lam = rate_s * 4, base * 4
    excess = count - (lam + 3 * np.sqrt(lam) + 3)
    spike = np.clip(excess / (lam + 6), 0, 1)
    spike = np.where(excess > 0, np.clip(spike + hype_s / 3, 0, 1), 0)  # les « POG », « GG », « clip » renforcent un vrai pic
    return {"chat_rate": rate_s.astype(np.float32), "chat_spike": spike.astype(np.float32)}
