"""Signaux visuels : mouvement/flash à l'écran et lecture du texte affiché (OCR).

Deux modes, décrits dans le profil de jeu :
- « full » : tout l'écran est lu une fois par seconde et chaque ligne est gardée avec sa
  position. Les règles (motif + zone de l'écran) s'appliquent ensuite au moment du
  scoring : on peut corriger une règle et recalculer sans relancer l'OCR.
- « zones » : seulement quelques rectangles du HUD (sources verticales, où le HUD est rogné).
"""

from __future__ import annotations

import re
import threading
import unicodedata
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


def norm(text: str) -> str:
    """Minuscules sans accents : l'OCR confond é/e, on compare sur une base neutre."""
    text = unicodedata.normalize("NFD", text.lower().replace("’", "'"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _match(text: str, patterns: list[str], threshold: int, whole: bool = False) -> float:
    """`whole` : la ligne entière doit ressembler au motif (« Tuer BOUCHER » ≠ « Bannir BOUCHER »),
    sinon il suffit que le motif apparaisse dans la ligne."""
    best = 0.0
    text = norm(text)
    for p in patterns:
        p = norm(p)
        # partial_ratio note 100 un texte très court contenu dans le motif (« e ») : on l'écarte
        if len(text) < 0.6 * len(p):
            continue
        score = fuzz.ratio(p, text) if whole else fuzz.partial_ratio(p, text)
        if score > best:
            best = score
    return best / 100.0 if best >= threshold else 0.0


def match_rules(lines: list[dict], rules: list[dict]) -> list[dict]:
    """Applique les règles du profil aux lignes lues : [{t, event, text, confidence}].

    Une règle : {event, patterns, rect?: [x0,y0,x1,y1], threshold?}. Le rect filtre sur le
    centre de la ligne (en fractions de l'écran) : « Indice trouvé » en haut à gauche n'est
    pas la même chose qu'une ligne d'aide qui contient le mot « indice ».
    """
    out = []
    for frame in lines:
        for rule in rules:
            x0, y0, x1, y1 = rule.get("rect", [0, 0, 1, 1])
            for x, y, text in frame["items"]:
                if not (x0 <= x <= x1 and y0 <= y <= y1):
                    continue
                conf = _match(text, rule["patterns"], rule.get("threshold", 78), rule.get("whole", False))
                if conf:
                    out.append({"t": frame["t"], "event": rule["event"], "text": text, "confidence": conf})
                    break
    return out


def analyze(
    video: str,
    duration: float,
    ocr_zones: list[dict],
    ocr_langs: tuple[str, ...] = ("fr", "en"),
    fps: float = 2.0,
    progress: Callable[[float], None] | None = None,
    full_every: float | None = None,
) -> tuple[dict[str, np.ndarray], list[dict], list[dict]]:
    """Parcourt la vidéo à `fps` images/s.

    Renvoie les signaux continus (motion, flash), les détections des zones
    [{t, zone, event, text, confidence}] et, si `full_every`, les lignes lues sur tout
    l'écran [{t, items: [[x, y, texte], ...]}].
    """
    n = int(np.ceil(duration / STEP))
    motion = np.zeros(n, dtype=np.float32)
    flash = np.zeros(n, dtype=np.float32)
    reader = _get_reader(tuple(ocr_langs)) if (ocr_zones or full_every) else None
    detections: list[dict] = []
    lines: list[dict] = []
    prev_small = None
    prev_luma = None
    last_ocr = {zone["name"]: -1e9 for zone in ocr_zones}
    last_full = -1e9
    # 1280x720 suffit pour lire le HUD et divise par 2 le coût de décodage
    for t, frame in media.sample_frames(video, fps, 1280, 720):
        i = min(n - 1, int(t / STEP))
        small = frame[::8, ::8].mean(axis=2)
        luma = float(small.mean())
        if prev_small is not None:
            motion[i] = max(motion[i], float(np.abs(small - prev_small).mean()) / 120.0)
            flash[i] = max(flash[i], max(0.0, luma - prev_luma) / 60.0)
        prev_small, prev_luma = small, luma

        if full_every and t - last_full >= full_every - 1e-6:
            last_full = t
            items = []
            for box, text, conf in reader.readtext(frame, paragraph=False):
                # on garde aussi les compteurs courts comme « 1/3 » (indices trouvés pour un boss)
                if conf >= 0.3 and (len(text.strip()) >= 4 or re.fullmatch(r"\s*\d\s*/\s*\d\s*", text)):
                    cx = float(sum(p[0] for p in box)) / 4 / frame.shape[1]
                    cy = float(sum(p[1] for p in box)) / 4 / frame.shape[0]
                    items.append([round(cx, 3), round(cy, 3), text.strip()])
            if items:
                lines.append({"t": round(t, 2), "items": items})

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
    return {"motion": np.clip(motion, 0, 1), "flash": np.clip(flash, 0, 1)}, detections, lines
