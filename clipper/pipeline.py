"""Analyse complète d'une vidéo : audio → transcription → sons → image → moments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import numpy as np

from . import games, media, scoring, sounds, transcribe
from .config import ANALYSIS_DIR, Settings
from .cues import STEP, audio, chat, hitmarker, speech, visual

Progress = Callable[[str, float], None]


def video_id(path: str | Path) -> str:
    p = Path(path)
    st = p.stat()
    return hashlib.sha1(f"{p.resolve()}|{st.st_size}".encode()).hexdigest()[:16]


def work_dir(vid: str) -> Path:
    d = ANALYSIS_DIR / vid
    d.mkdir(parents=True, exist_ok=True)
    return d


STAGES = ("audio", "voix", "transcription", "sons", "image")


def analyze(path: str, game_id: str, settings: Settings, progress: Progress | None = None, resume: bool = True) -> dict:
    """Analyse complète. Chaque étape terminée est gardée (fichier + marqueur « .done ») :
    après une pause, une annulation ou un redémarrage, `resume` repart de la dernière étape faite.
    """
    report = progress or (lambda stage, p: None)
    vid = video_id(path)
    wd = work_dir(vid)
    info = media.probe(path)
    profile = games.load(game_id)
    orientation = "portrait" if info.height > info.width else "landscape"
    track = min(settings.audio_track, max(0, info.audio_tracks - 1))

    def done(stage: str) -> bool:
        return resume and (wd / f"{stage}.done").exists()

    def finish(stage: str) -> None:
        (wd / f"{stage}.done").touch()

    if not resume:
        for s in STAGES:
            (wd / f"{s}.done").unlink(missing_ok=True)

    report("audio", 0.0)
    wav = wd / "audio.wav"
    if not done("audio"):
        media.extract_audio(path, wav, track=track)
        finish("audio")
    samples, sr = media.load_wav(wav)

    report("voix", 0.0)
    vocals = wd / "vocals.wav"
    if not done("voix"):
        stereo = media.extract_audio(path, wd / "audio_44k.wav", track=track, sample_rate=44100, channels=2)
        transcribe.isolate_vocals(stereo, vocals, progress=lambda p: report("voix", p))
        stereo.unlink(missing_ok=True)  # gros fichier, inutile une fois les voix extraites
        finish("voix")

    report("transcription", 0.0)
    seg_file = wd / "segments.json"
    if done("transcription"):
        segments = json.loads(seg_file.read_text(encoding="utf-8"))
    else:
        segments = transcribe.transcribe(
            wav, settings.whisper_model, settings.language, profile.get("vocabulary"),
            progress=lambda p: report("transcription", p), vocals=vocals,
        )
        seg_file.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
        finish("transcription")

    report("sons", 0.0)
    sound_file = wd / "sounds.npz"
    if done("sons"):
        with np.load(sound_file) as z:
            sound_sig = {k: z[k] for k in z.files}
    else:
        sound_sig = audio.loudness(samples, sr, info.duration)
        events_sig, embs, emb_t = audio.sound_events(samples, sr, info.duration, progress=lambda p: report("sons", p))
        sound_sig.update(events_sig)
        np.savez_compressed(wd / "embeddings.npz", emb=embs, t=emb_t)
        np.savez_compressed(sound_file, **sound_sig)
        finish("sons")
    signals: dict[str, np.ndarray] = dict(sound_sig)
    signals.update(speech.speech_intensity(segments, info.duration))

    report("image", 0.0)
    vis_file, ocr_file = wd / "visual.npz", wd / "ocr.json"
    if done("image"):
        with np.load(vis_file) as z:
            vis_signals = {k: z[k] for k in z.files}
        cached = json.loads(ocr_file.read_text(encoding="utf-8"))
        ocr, ocr_lines = cached["ocr"], cached["lines"]
    else:
        zones = profile["ocr_zones"].get(orientation, [])
        vis_signals, ocr, ocr_lines = visual.analyze(
            path, info.duration, zones, tuple(profile.get("ocr_langs", ["fr", "en"])),
            progress=lambda p: report("image", p),
            full_every=profile.get("ocr_full_every", {}).get(orientation),
        )
        np.savez_compressed(vis_file, **vis_signals)
        ocr_file.write_text(json.dumps({"ocr": ocr, "lines": ocr_lines}, ensure_ascii=False), encoding="utf-8")
        finish("image")
    signals.update(vis_signals)

    np.savez_compressed(wd / "signals.npz", **signals)
    raw = {
        "video_id": vid, "path": str(path), "game": game_id, "orientation": orientation,
        "duration": info.duration, "width": info.width, "height": info.height, "fps": info.fps,
        "segments": segments, "ocr": ocr, "ocr_lines": ocr_lines, "bookmarks": [],
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


def load_embeddings(vid: str) -> tuple[np.ndarray, np.ndarray]:
    """Empreintes audio de la vidéo ; calculées à la volée pour les analyses d'avant leur ajout."""
    f = work_dir(vid) / "embeddings.npz"
    if not f.exists():
        raw = load_raw(vid)
        samples, sr = media.load_wav(work_dir(vid) / "audio.wav")
        sound_sig, embs, emb_t = audio.sound_events(samples, sr, raw["duration"])
        signals = load_signals(vid)
        signals.update(sound_sig)  # même passage : on rafraîchit aussi les sons à la nouvelle résolution
        np.savez_compressed(work_dir(vid) / "signals.npz", **signals)
        np.savez_compressed(f, emb=embs, t=emb_t)
    with np.load(f) as z:
        return z["emb"], z["t"]


def learned_signals(vid: str, profile: dict, duration: float) -> dict[str, np.ndarray]:
    """Ressemblance avec chaque son appris pour ce jeu, sur la grille de la timeline."""
    refs = sounds.references(profile["id"])
    kinds = [k for k in profile.get("learned_sounds", {}) if refs.get(k, {}).get("pos")]
    if not kinds:
        return {}
    embs, starts = load_embeddings(vid)
    n = int(np.ceil(duration / STEP))
    out = {}
    for kind in kinds:
        sims = audio.similarity(embs, refs[kind]["pos"])
        if refs[kind]["neg"]:
            # plus proche d'un contre-exemple que d'un exemple : ce n'est pas ce son
            neg = audio.similarity(embs, refs[kind]["neg"])
            sims = np.where(neg >= sims - 0.02, sims * 0.85, sims)
        grid = np.zeros(n, dtype=np.float32)
        for s, v in zip(starts, sims):
            i0, i1 = int(s / STEP), min(n, int((s + audio.EMB_WIN) / STEP))
            grid[i0:i1] = np.maximum(grid[i0:i1], v)
        out[f"learned_{kind}"] = grid
    return out


def quiet_mask(vid: str, segments: list[dict], start: float, end: float) -> list[bool]:
    """Pas de 0,5 s sans parole, sans tir ni pic sonore : candidats à l'accélération."""
    sig = load_signals(vid)
    i0, i1 = int(start / STEP), int(np.ceil(end / STEP))
    loud = sig.get("loudness_spike", np.zeros(i1))[i0:i1]
    gun = sig.get("gunshot", np.zeros(i1))[i0:i1]
    quiet = (loud < 0.25) & (gun < 0.12)
    for seg in segments:
        for w in seg["words"]:
            a, b = int(w["start"] / STEP) - i0, int(np.ceil(w["end"] / STEP)) - i0
            quiet[max(0, a - 1):max(0, b + 1)] = False  # on ne coupe jamais la parole
    return quiet.tolist()


def _pool(v: np.ndarray, k: int) -> list[float]:
    """Max par bloc de k pas : on allège la timeline sans perdre les pics."""
    pad = (-len(v)) % k
    return np.pad(v, (0, pad)).reshape(-1, k).max(axis=1).round(3).tolist()


def rescore(vid: str, settings: Settings, game_id: str | None = None) -> dict:
    """Recalcule événements et moments sans relancer les modèles (changement de jeu, réglages, marque-pages)."""
    raw = load_raw(vid)
    if game_id:
        raw["game"] = game_id
        save_raw(vid, raw)
    profile = games.load(raw["game"])
    signals = load_signals(vid)
    # chat Twitch posé à côté de la vidéo (export TwitchDownloader) : pics de réaction des viewers
    chat_info = None
    chat_file = chat.find_chat_file(Path(raw["path"]))
    if chat_file:
        messages = chat.load_messages(chat_file)
        if messages:
            signals.update(chat.chat_signals(messages, raw["duration"]))
            chat_info = {"file": chat_file.name, "messages": len(messages)}
    learned = learned_signals(vid, profile, raw["duration"])
    signals.update(learned)
    for kind, spec in profile.get("learned_sounds", {}).items():
        if f"learned_{kind}" in learned:
            profile["signals"][f"learned_{kind}"] = {"threshold": spec["threshold"], "event": spec["event"], "min_duration": 0}
    keywords = dict(profile.get("keywords", {}))
    keywords.update({k: 10 for k in settings.custom_keywords})
    hits = speech.keyword_hits(raw["segments"], keywords)
    # règles plein écran ré-appliquées aux lignes lues : corriger un motif ne demande pas de relancer l'OCR
    ocr = raw["ocr"] + visual.match_rules(raw.get("ocr_lines", []), profile.get("ocr_rules", {}).get(raw["orientation"], []))
    # phrases dites en jeu : alerte avant un combat, allié à terre, ennemi à terre (listes des Réglages)
    phrase_hits = {kind: speech.keyword_hits(raw["segments"], {p: 1 for p in phrases})
                   for kind, phrases in (("alert", settings.alert_phrases), ("ally_down", settings.ally_down_phrases),
                                         ("enemy_down", settings.enemy_down_phrases))}
    # « X » de touche au centre de l'écran, cherché seulement autour des sons de combat
    markers = []
    if profile.get("hit_marker") and raw["orientation"] == "landscape":
        fight_sounds = [e["t"] for e in scoring.detect_events(profile, signals, [], [], [])
                        if e["type"] in ("gunfight", "player_hit", "death_cry", "pvp_fight")]
        markers = hitmarker.scan(raw["path"], hitmarker.windows_around(fight_sounds), work_dir(vid) / "hitmarkers.json")
    events = scoring.detect_events(profile, signals, ocr, hits, raw.get("bookmarks", []), phrase_hits, markers)
    # compteur « 1/3 » et boss de chaque indice, puis découpage final (les libellés en dépendent)
    scoring.enrich_clues(events, raw.get("ocr_lines", []), scoring.build_matches(events, raw["duration"], settings.story_preset))
    matches = scoring.build_matches(events, raw["duration"], settings.story_preset)
    # hub du jeu (menus, recrutement, boutique) : rien à clipper entre deux parties
    in_game = events
    if matches:
        in_game = [e for e in events if any(m["start"] - 5 <= e["t"] <= m["end"] + 5 for m in matches)]
    moments = scoring.build_moments(
        in_game, raw["segments"], raw["duration"],
        min_len=settings.clip_min_s, max_len=settings.clip_max_s,
        min_score=settings.min_score, max_clips=settings.max_clips,
    )
    # un clip ne déborde jamais sur l'écran de fin ou le hub
    for m in moments:
        match = next((x for x in matches if x["start"] - 5 <= m["peak"] <= x["end"] + 5), None)
        if match:
            m["start"], m["end"] = max(m["start"], match["start"]), min(m["end"], match["end"])
    # les moments créés à la main survivent au recalcul
    for m in raw.get("manual_moments", []):
        inside = [e for e in events if m["start"] <= e["t"] <= m["end"]]
        moments.append({**m, "events": inside, "manual": True})
    moments.sort(key=lambda m: m["start"])
    for i, m in enumerate(moments):
        m["id"] = i
    result = {**{k: v for k, v in raw.items() if k != "ocr_lines"}, "events": events, "moments": moments, "matches": matches,
              "chat": chat_info,
              "timeline": {k: _pool(v, max(1, int(1 / STEP))) for k, v in signals.items()
                           if k in ("loudness_spike", "laughter", "scream", "gunshot", "explosion", "motion", "speech_excited", "chat_spike")
                           or k.startswith("learned_")},
              "timeline_step": max(STEP, 1.0)}
    (work_dir(vid) / "analysis.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def load_analysis(vid: str) -> dict | None:
    f = work_dir(vid) / "analysis.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
