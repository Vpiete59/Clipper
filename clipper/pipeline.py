"""Analyse complète d'une vidéo : audio → transcription → sons → image → moments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import numpy as np

from . import games, media, scoring, transcribe
from .config import ANALYSIS_DIR, Settings
from .cues import STEP, audio, speech, visual

Progress = Callable[[str, float], None]


def video_id(path: str | Path) -> str:
    p = Path(path)
    st = p.stat()
    return hashlib.sha1(f"{p.resolve()}|{st.st_size}".encode()).hexdigest()[:16]


def work_dir(vid: str) -> Path:
    d = ANALYSIS_DIR / vid
    d.mkdir(parents=True, exist_ok=True)
    return d


def analyze(path: str, game_id: str, settings: Settings, progress: Progress | None = None) -> dict:
    report = progress or (lambda stage, p: None)
    vid = video_id(path)
    wd = work_dir(vid)
    info = media.probe(path)
    profile = games.load(game_id)
    orientation = "portrait" if info.height > info.width else "landscape"

    report("audio", 0.0)
    wav = media.extract_audio(path, wd / "audio.wav", track=min(settings.audio_track, max(0, info.audio_tracks - 1)))
    samples, sr = media.load_wav(wav)

    report("transcription", 0.0)
    segments = transcribe.transcribe(
        wav, settings.whisper_model, settings.language, profile.get("vocabulary"),
        progress=lambda p: report("transcription", p),
    )

    report("sons", 0.0)
    signals: dict[str, np.ndarray] = {}
    signals.update(audio.loudness(samples, sr, info.duration))
    signals.update(audio.sound_events(samples, sr, info.duration, progress=lambda p: report("sons", p)))
    signals.update(speech.speech_intensity(segments, info.duration))

    report("image", 0.0)
    zones = profile["ocr_zones"].get(orientation, [])
    vis_signals, ocr = visual.analyze(
        path, info.duration, zones, tuple(profile.get("ocr_langs", ["fr", "en"])),
        progress=lambda p: report("image", p),
    )
    signals.update(vis_signals)

    np.savez_compressed(wd / "signals.npz", **signals)
    raw = {
        "video_id": vid, "path": str(path), "game": game_id, "orientation": orientation,
        "duration": info.duration, "width": info.width, "height": info.height, "fps": info.fps,
        "segments": segments, "ocr": ocr, "bookmarks": [],
    }
    (wd / "raw.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    report("moments", 0.0)
    return rescore(vid, settings)


def load_raw(vid: str) -> dict:
    return json.loads((work_dir(vid) / "raw.json").read_text(encoding="utf-8"))


def save_raw(vid: str, raw: dict) -> None:
    (work_dir(vid) / "raw.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def load_signals(vid: str) -> dict[str, np.ndarray]:
    with np.load(work_dir(vid) / "signals.npz") as z:
        return {k: z[k] for k in z.files}


def rescore(vid: str, settings: Settings, game_id: str | None = None) -> dict:
    """Recalcule événements et moments sans relancer les modèles (changement de jeu, réglages, marque-pages)."""
    raw = load_raw(vid)
    if game_id:
        raw["game"] = game_id
        save_raw(vid, raw)
    profile = games.load(raw["game"])
    signals = load_signals(vid)
    keywords = dict(profile.get("keywords", {}))
    keywords.update({k: 10 for k in settings.custom_keywords})
    hits = speech.keyword_hits(raw["segments"], keywords)
    events = scoring.detect_events(profile, signals, raw["ocr"], hits, raw.get("bookmarks", []))
    moments = scoring.build_moments(
        events, raw["segments"], raw["duration"],
        min_len=settings.clip_min_s, max_len=settings.clip_max_s,
        min_score=settings.min_score, max_clips=settings.max_clips,
    )
    # les moments créés à la main survivent au recalcul
    for m in raw.get("manual_moments", []):
        inside = [e for e in events if m["start"] <= e["t"] <= m["end"]]
        moments.append({**m, "events": inside, "manual": True})
    moments.sort(key=lambda m: m["start"])
    for i, m in enumerate(moments):
        m["id"] = i
    result = {**raw, "events": events, "moments": moments,
              "timeline": {k: v[:: max(1, int(1 / STEP))].round(3).tolist() for k, v in signals.items()
                           if k in ("loudness_spike", "laughter", "scream", "gunshot", "explosion", "motion", "speech_excited")},
              "timeline_step": max(STEP, 1.0)}
    (work_dir(vid) / "analysis.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def load_analysis(vid: str) -> dict | None:
    f = work_dir(vid) / "analysis.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
