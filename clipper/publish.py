"""Publication semi-automatique : textes par plateforme, ouverture de la page d'upload, suivi.

Les API officielles imposent des audits (YouTube et TikTok publient en privé tant qu'ils
n'ont pas eu lieu). On prépare donc tout ici, et c'est toi qui fais le dernier geste.
"""

from __future__ import annotations

import re
import subprocess
import webbrowser
from pathlib import Path

from . import games
from .config import Settings

PLATFORMS = {
    "youtube": {
        "name": "YouTube Shorts",
        "upload_url": "https://www.youtube.com/upload",
        "title_max": 100,
        "caption_max": 5000,
        "max_hashtags": 5,
        "max_duration": 180,
    },
    "tiktok": {
        "name": "TikTok",
        "upload_url": "https://www.tiktok.com/tiktokstudio/upload",
        "title_max": 0,
        "caption_max": 2200,
        "max_hashtags": 5,
        "max_duration": 600,
    },
    "instagram": {
        "name": "Instagram Reels",
        "upload_url": "https://www.instagram.com/",
        "title_max": 0,
        "caption_max": 2200,
        "max_hashtags": 5,
        "max_duration": 180,
    },
}

# petite touche par type d'action, pour un titre qui donne envie de cliquer
EVENT_FLAVOR = {
    "death": "💀", "gunfight": "🔫", "bounty": "💰", "extract": "🏃", "banish": "🔥",
    "laughter": "😂", "scream": "😱", "explosion": "💥", "revive": "🩹",
}
EVENT_TAGS = {
    "death": "fail", "gunfight": "fps", "bounty": "clutch", "laughter": "funny", "scream": "rage",
}


def _clean_tag(tag: str) -> str:
    return re.sub(r"[^\w]", "", tag.lstrip("#").lower())


def _shorten(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _capitalize(text: str) -> str:
    text = text.strip().rstrip(".")
    return text[:1].upper() + text[1:] if text else text


OUTCOME_LINE = {"extracted": "Extraction réussie 🏃", "dead": "Ça finit mal 💀", "unknown": ""}


def _match_hook(match: dict) -> str:
    bits = []
    if match["clues"]:
        bits.append(f"{match['clues']} indice{'s' if match['clues'] > 1 else ''}")
    if match["fights"]:
        bits.append(f"{match['fights']} combat{'s' if match['fights'] > 1 else ''}")
    if match["bounty"]:
        bits.append("la prime")
    return "Une partie complète : " + ", ".join(bits) if bits else "Une partie complète"


def suggest(analysis: dict, moment: dict | None, platform: str, settings: Settings, match: dict | None = None) -> dict:
    """Titre, description et hashtags proposés pour un clip, le résumé d'une partie (`match`) ou le montage."""
    spec = PLATFORMS[platform]
    profile = games.load(analysis["game"])
    game_name = profile["name"].replace(" (tous jeux)", "")

    if moment:
        hook = _capitalize(moment.get("hook") or moment["title"])
        main = max(moment["events"], key=lambda e: e["score"])["type"] if moment["events"] else ""
        flavor = EVENT_FLAVOR.get(main, "")
        line = _shorten(" ".join(seg["text"] for seg in analysis["segments"]
                                 if moment["start"] <= seg["start"] < moment["end"]), 140)
        types = {e["type"] for e in moment["events"]}
    elif match:
        hook, flavor, line = _match_hook(match), "", OUTCOME_LINE[match["outcome"]]
        types = {c["type"] for c in match["chapters"]}
    else:
        hook, flavor, line = f"Best of {game_name}", "🔥", ""
        types = {e["type"] for m in analysis["moments"] for e in m["events"]}

    tags: list[str] = []
    for t in [*profile.get("hashtags", []), *(EVENT_TAGS[t] for t in types if t in EVENT_TAGS), *settings.extra_hashtags]:
        t = _clean_tag(t)
        if t and t not in tags:
            tags.append(t)
    if platform == "youtube":
        tags.insert(0, "shorts")
    tags = tags[: spec["max_hashtags"]]
    hashtags = " ".join(f"#{t}" for t in tags)

    title = f"{hook} {flavor}".strip()
    if platform == "youtube":
        if moment or match:
            title = f"{title} | {game_name}"
        title = title[: spec["title_max"]]
        body = [line and f"« {line} »", settings.publish_signature, hashtags]
    else:
        body = [f"{hook} {flavor}".strip(), line if match else "", settings.publish_signature, hashtags]
    caption = "\n\n".join(p for p in body if p)[: spec["caption_max"]]
    return {"platform": platform, "title": title if spec["title_max"] else "", "caption": caption}


def open_upload(platform: str, file_path: str) -> None:
    """Ouvre la page d'upload dans le navigateur par défaut et montre le fichier dans l'Explorateur."""
    webbrowser.open(PLATFORMS[platform]["upload_url"])
    path = Path(file_path)
    if path.exists():
        # une seule chaîne : explorer attend « /select,"chemin" » collé, guillemets compris
        subprocess.Popen(f'explorer /select,"{path}"')  # noqa: S602,S607 — Explorateur Windows
