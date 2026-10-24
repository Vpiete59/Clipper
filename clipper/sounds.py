"""Sons appris par l'exemple (cri de mort, etc.), rangés par jeu.

On marque un son une fois dans une vidéo ; son empreinte AST est gardée et comparée à
toutes les fenêtres des autres vidéos. Plusieurs exemples d'un même son = détection plus sûre.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import numpy as np

from .config import DATA_DIR

SOUNDS_DIR = DATA_DIR / "sounds"
SOUNDS_DIR.mkdir(exist_ok=True)
INDEX = SOUNDS_DIR / "index.json"


def _index() -> list[dict]:
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else []


def _save(items: list[dict]) -> None:
    INDEX.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_sounds(game: str | None = None) -> list[dict]:
    return [s for s in _index() if game is None or s["game"] == game]


def references(game: str) -> dict[str, dict[str, list[np.ndarray]]]:
    """{type de son: {"pos": exemples, "neg": contre-exemples}}."""
    refs: dict[str, dict[str, list[np.ndarray]]] = {}
    for s in list_sounds(game):
        f = SOUNDS_DIR / f"{s['id']}.npy"
        if f.exists():
            side = "neg" if s.get("negative") else "pos"
            refs.setdefault(s["kind"], {"pos": [], "neg": []})[side].append(np.load(f))
    return refs


def add(game: str, kind: str, embedding: np.ndarray, video_id: str, t: float, video_name: str = "",
        negative: bool = False) -> dict:
    """`negative` : « ce son-là n'en est PAS un » (chien, explosion…), pour corriger les faux positifs."""
    item = {"id": uuid.uuid4().hex[:12], "game": game, "kind": kind, "video_id": video_id,
            "video_name": video_name, "t": round(t, 2), "negative": negative, "created_at": time.time()}
    np.save(SOUNDS_DIR / f"{item['id']}.npy", embedding.astype(np.float32))
    _save([*_index(), item])
    return item


def delete(sound_id: str) -> None:
    _save([s for s in _index() if s["id"] != sound_id])
    Path(SOUNDS_DIR / f"{sound_id}.npy").unlink(missing_ok=True)
