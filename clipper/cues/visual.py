"""Signaux visuels : mouvement/flash à l'écran et lecture de texte (OCR) dans des zones du HUD.

Même principe que Powder (crops OCR + correspondance de texte), mais les zones et les
textes sont décrits dans les profils de jeu JSON, donc modifiables sans recompiler.
"""

from __future__ import annotations

import threading
from typing import Callable

import numpy as np
from rapidfuzz import fuzz

from .. import media
from . import STEP

_reader = None
_reader_langs = None
_lock = threading.Lock()


def _get_reader(langs: tuple[str, ...]):
    global _reader, _reader_langs
    with _lock:
        if _reader is None or _reader_langs != langs:
            import easyocr
            import torch

            _reader = easyocr.Reader(list(langs), gpu=torch.cuda.is_available(), verbose=False)
            _reader_langs = langs
        return _reader


def _crop(frame: np.ndarray, rect: list[float]) -> np.ndarray:
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = rect
    return frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)]


def _match(text: str, patterns: list[str], threshold: int) -> float:
    best = 0.0
    for p in patterns:
        p = p.lower()
        # partial_ratio note 100 un texte très court contenu dans le motif (« e ») : on l'écarte
        if len(text) < 0.6 * len(p):
            continue
        score = fuzz.partial_ratio(p, text)
        if score > best:
            best = score
    return best / 100.0 if best >= threshold else 0.0


def analyze(
    video: str,
    duration: float,
    ocr_zones: list[dict],
    ocr_langs: tuple[str, ...] = ("fr", "en"),
    fps: float = 2.0,
    progress: Callable[[float], None] | None = None,
) -> tuple[dict[str, np.ndarray], list[dict]]:
    """Parcourt la vidéo à `fps` images/s.

    Renvoie les signaux continus (motion, flash) et la liste des lectures OCR qui
    correspondent à un motif d'une zone : [{t, zone, event, text, confidence}].
    """
    n = int(np.ceil(duration / STEP))
    motion = np.zeros(n, dtype=np.float32)
    flash = np.zeros(n, dtype=np.float32)
    reader = _get_reader(tuple(ocr_langs)) if ocr_zones else None
    detections: list[dict] = []
    prev_small = None
    prev_luma = None
    last_ocr = {zone["name"]: -1e9 for zone in ocr_zones}
    # 1280x720 suffit pour lire le HUD et divise par 2 le coût de décodage
    for t, frame in media.sample_frames(video, fps, 1280, 720):
        i = min(n - 1, int(t / STEP))
        small = frame[::8, ::8].mean(axis=2)
        luma = float(small.mean())
        if prev_small is not None:
            motion[i] = max(motion[i], float(np.abs(small - prev_small).mean()) / 120.0)
            flash[i] = max(flash[i], max(0.0, luma - prev_luma) / 60.0)
        prev_small, prev_luma = small, luma

        for zone in ocr_zones:
            if t - last_ocr[zone["name"]] < zone.get("every_s", 0.5) - 1e-6:
                continue
            last_ocr[zone["name"]] = t
            crop = _crop(frame, zone["rect"])
            texts = reader.readtext(crop, detail=0, paragraph=True)
            text = " ".join(texts).lower().strip()
            if not text:
                continue
            for ev in zone["events"]:
                conf = _match(text, ev["patterns"], ev.get("threshold", 80))
                if conf:
                    detections.append({"t": round(t, 2), "zone": zone["name"], "event": ev["name"], "text": text, "confidence": conf})
        if progress:
            progress(min(1.0, t / duration))
    return {"motion": np.clip(motion, 0, 1), "flash": np.clip(flash, 0, 1)}, detections
