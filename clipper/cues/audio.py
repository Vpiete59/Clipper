"""Signaux audio : pics de volume et classification d'événements sonores (AudioSet).

Remplace le modèle « Laughing » chiffré de Powder par un modèle AST public entraîné
sur AudioSet, qui reconnaît aussi les tirs et explosions.
"""

from __future__ import annotations

import threading
from typing import Callable

import numpy as np

from . import STEP

AST_MODEL = "MIT/ast-finetuned-audioset-10-10-0.4593"

# signal Clipper -> étiquettes AudioSet regroupées
SOUND_GROUPS = {
    "laughter": ["Laughter", "Giggle", "Chuckle, chortle", "Belly laugh", "Snicker"],
    "scream": ["Screaming", "Shout", "Yell", "Battle cry", "Children shouting"],
    "gunshot": ["Gunshot, gunfire", "Machine gun", "Fusillade", "Cap gun", "Artillery fire"],
    "explosion": ["Explosion", "Boom", "Burst, pop"],
    "cheer": ["Cheering", "Applause", "Crowd"],
}

_clf = None
_lock = threading.Lock()


def _get_classifier():
    global _clf
    with _lock:
        if _clf is None:
            import torch
            from transformers import ASTFeatureExtractor, ASTForAudioClassification

            device = "cuda" if torch.cuda.is_available() else "cpu"
            fe = ASTFeatureExtractor.from_pretrained(AST_MODEL)
            model = ASTForAudioClassification.from_pretrained(AST_MODEL).to(device).eval()
            if device == "cuda":
                model = model.half()
            label_ids = {lbl: i for i, lbl in model.config.id2label.items()}
            groups = {g: [label_ids[l] for l in labels if l in label_ids] for g, labels in SOUND_GROUPS.items()}
            _clf = (fe, model, device, groups)
        return _clf


def loudness(audio: np.ndarray, sr: int, duration: float) -> dict[str, np.ndarray]:
    """Volume (dBFS) par pas de STEP, et « spike » = écart au niveau ambiant récent."""
    n = int(np.ceil(duration / STEP))
    hop = int(sr * STEP)
    rms = np.zeros(n, dtype=np.float32)
    for i in range(n):
        chunk = audio[i * hop:(i + 1) * hop]
        if chunk.size:
            rms[i] = np.sqrt(np.mean(chunk.astype(np.float64) ** 2))
    db = 20 * np.log10(np.maximum(rms, 1e-5))
    # niveau ambiant = médiane glissante sur ~20 s ; un pic = > 9 dB au-dessus
    win = int(20 / STEP)
    padded = np.pad(db, (win // 2, win // 2), mode="edge")
    ambient = np.array([np.median(padded[i:i + win]) for i in range(n)], dtype=np.float32)
    spike = np.clip((db - ambient - 6) / 12, 0, 1)
    return {"loudness_db": db, "loudness_spike": spike.astype(np.float32)}


def sound_events(
    audio: np.ndarray, sr: int, duration: float, progress: Callable[[float], None] | None = None
) -> dict[str, np.ndarray]:
    """Probabilité de rire / cri / tir / explosion sur chaque pas de la timeline.

    Fenêtres de 2 s glissant d'1 s ; chaque pas reçoit le max des fenêtres qui le couvrent.
    """
    import torch

    fe, model, device, groups = _get_classifier()
    n = int(np.ceil(duration / STEP))
    out = {g: np.zeros(n, dtype=np.float32) for g in groups}
    win, hop = int(2.0 * sr), int(1.0 * sr)
    starts = list(range(0, max(1, len(audio) - win + 1), hop))
    batch = 32
    for b in range(0, len(starts), batch):
        chunk_starts = starts[b:b + batch]
        chunks = [audio[s:s + win] for s in chunk_starts]
        feats = fe(chunks, sampling_rate=sr, return_tensors="pt")["input_values"].to(device)
        if device == "cuda":
            feats = feats.half()
        with torch.no_grad():
            probs = torch.sigmoid(model(feats).logits).float().cpu().numpy()
        for s, p in zip(chunk_starts, probs):
            i0, i1 = int(s / sr / STEP), min(n, int((s + win) / sr / STEP))
            for g, ids in groups.items():
                if ids:
                    out[g][i0:i1] = np.maximum(out[g][i0:i1], p[ids].max())
        if progress:
            progress(min(1.0, (b + batch) / len(starts)))
    return out
