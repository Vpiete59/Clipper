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


EMB_WIN, EMB_HOP = 1.0, 0.5  # fenêtres courtes : un cri d'agonie dure moins d'une seconde


def _forward(chunks: list[np.ndarray], sr: int):
    """Un passage AST : probabilités AudioSet + empreinte (vecteur 768) de chaque fenêtre."""
    import torch

    fe, model, device, _ = _get_classifier()
    feats = fe(chunks, sampling_rate=sr, return_tensors="pt")["input_values"].to(device)
    if device == "cuda":
        feats = feats.half()
    with torch.no_grad():
        pooled = model.audio_spectrogram_transformer(feats).pooler_output
        probs = torch.sigmoid(model.classifier(pooled)).float().cpu().numpy()
    return probs, pooled.float().cpu().numpy()


def sound_events(
    audio: np.ndarray, sr: int, duration: float, progress: Callable[[float], None] | None = None
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Probabilité de rire / cri / tir / explosion sur chaque pas de la timeline, plus les empreintes.

    Fenêtres d'1 s glissant de 0,5 s ; chaque pas reçoit le max des fenêtres qui le couvrent.
    Les empreintes servent à retrouver un son appris (cri de mort, etc.) sans relancer le modèle.
    """
    _, _, _, groups = _get_classifier()
    n = int(np.ceil(duration / STEP))
    out = {g: np.zeros(n, dtype=np.float32) for g in groups}
    win, hop = int(EMB_WIN * sr), int(EMB_HOP * sr)
    starts = list(range(0, max(1, len(audio) - win + 1), hop))
    embs = np.zeros((len(starts), 768), dtype=np.float16)
    batch = 48
    for b in range(0, len(starts), batch):
        chunk_starts = starts[b:b + batch]
        probs, pooled = _forward([audio[s:s + win] for s in chunk_starts], sr)
        embs[b:b + len(chunk_starts)] = pooled
        for s, p in zip(chunk_starts, probs):
            i0, i1 = int(s / sr / STEP), min(n, int((s + win) / sr / STEP))
            for g, ids in groups.items():
                if ids:
                    out[g][i0:i1] = np.maximum(out[g][i0:i1], p[ids].max())
        if progress:
            progress(min(1.0, (b + batch) / len(starts)))
    return out, embs, np.array(starts, dtype=np.float32) / sr


def embed_at(audio: np.ndarray, sr: int, t: float) -> np.ndarray:
    """Empreinte d'un son précis : fenêtre d'1 s commençant un peu avant `t`."""
    s = max(0, int((t - 0.25) * sr))
    _, pooled = _forward([audio[s:s + int(EMB_WIN * sr)]], sr)
    return pooled[0]


def similarity(embs: np.ndarray, refs: list[np.ndarray]) -> np.ndarray:
    """Similarité cosinus de chaque fenêtre avec le plus proche des sons de référence."""
    if not refs or not len(embs):
        return np.zeros(len(embs), dtype=np.float32)
    e = embs.astype(np.float32)
    e /= np.linalg.norm(e, axis=1, keepdims=True) + 1e-6
    r = np.stack(refs).astype(np.float32)
    r /= np.linalg.norm(r, axis=1, keepdims=True) + 1e-6
    return (e @ r.T).max(axis=1)
