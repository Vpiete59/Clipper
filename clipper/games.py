"""Profils de jeu (JSON dans /games) avec héritage via la clé `extends`."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from .config import GAMES_DIR


def _merge(base: dict, child: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in child.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "ocr_zones":
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _raw(game_id: str) -> dict:
    path = GAMES_DIR / f"{game_id}.json"
    if not path.exists():
        raise KeyError(f"Profil de jeu inconnu : {game_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def load(game_id: str) -> dict:
    data = _raw(game_id)
    parent = data.pop("extends", None)
    if parent:
        data = _merge(load(parent), data)
        data["id"] = game_id
    return data


def list_games() -> list[dict]:
    games = []
    for path in sorted(GAMES_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        games.append({"id": raw["id"], "name": raw["name"], "description": raw.get("description", "")})
    return games
