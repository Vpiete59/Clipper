"""Signaux tirés de la transcription : mots-clés et intensité de la parole."""

from __future__ import annotations

import re
import unicodedata

import numpy as np

from . import STEP


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9' ]+", " ", text).strip()


def keyword_hits(segments: list[dict], keywords: dict[str, float]) -> list[dict]:
    """Repère chaque mot-clé (expression multi-mots possible) dans le flux de mots.

    `keywords` : expression -> poids. Renvoie [{t, end, keyword, weight}].
    """
    words = [w for seg in segments for w in seg["words"]]
    normed = [_norm(w["word"]) for w in words]
    hits = []
    for phrase, weight in keywords.items():
        target = _norm(phrase).split()
        if not target:
            continue
        k = len(target)
        for i in range(len(words) - k + 1):
            if normed[i:i + k] == target:
                hits.append({"t": words[i]["start"], "end": words[i + k - 1]["end"], "keyword": phrase, "weight": weight})
    return hits


def speech_intensity(segments: list[dict], duration: float) -> dict[str, np.ndarray]:
    """Débit de parole (mots/s) lissé : un joueur qui s'emballe parle vite et fort."""
    n = int(np.ceil(duration / STEP))
    rate = np.zeros(n, dtype=np.float32)
    for seg in segments:
        for w in seg["words"]:
            i = int(w["start"] / STEP)
            if 0 <= i < n:
                rate[i] += 1
    kernel = np.ones(int(3 / STEP)) / 3.0  # mots par seconde sur 3 s
    rate = np.convolve(rate, kernel, mode="same")
    # le français parlé tourne autour de 3-4 mots/s : l'excitation commence au-delà
    speaking = np.clip((rate - 4.0) / 2.5, 0, 1)
    return {"speech_rate": rate.astype(np.float32), "speech_excited": speaking.astype(np.float32)}
