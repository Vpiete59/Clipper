"""Fusion des signaux en événements, puis en « moments » clippables classés par score.

Reprend l'idée de Powder (score par événement + marges avant/après + fusion des
événements proches) en y ajoutant un bonus de combo et l'alignement sur les phrases
pour ne jamais couper quelqu'un en plein milieu d'un mot.
"""

from __future__ import annotations

import numpy as np

from .cues import STEP


def _signal_events(name: str, signal: np.ndarray, spec: dict) -> list[dict]:
    thr, min_len = spec["threshold"], spec.get("min_duration", 0.5)
    above = signal >= thr
    events, i, n = [], 0, len(signal)
    while i < n:
        if not above[i]:
            i += 1
            continue
        j = i
        while j < n and above[j]:
            j += 1
        if (j - i) * STEP >= min_len:
            peak = i + int(np.argmax(signal[i:j]))
            events.append({
                "t": round(peak * STEP, 2), "start": round(i * STEP, 2), "end": round(j * STEP, 2),
                "type": spec["event"], "source": name, "strength": float(signal[peak]),
            })
        i = j
    return events


def _ocr_events(detections: list[dict]) -> list[dict]:
    """Une notification reste affichée plusieurs secondes : on regroupe les lectures successives."""
    events: list[dict] = []
    for d in sorted(detections, key=lambda d: d["t"]):
        last = next((e for e in reversed(events) if e["type"] == d["event"]), None)
        if last and d["t"] - last["end"] <= 3.0:
            last["end"] = d["t"]
            last["strength"] = max(last["strength"], d["confidence"])
            continue
        events.append({"t": d["t"], "start": d["t"], "end": d["t"], "type": d["event"], "source": "ocr",
                       "strength": d["confidence"], "text": d["text"]})
    return events


def detect_events(profile: dict, signals: dict[str, np.ndarray], ocr: list[dict],
                  keyword_hits: list[dict], bookmarks: list[float]) -> list[dict]:
    events: list[dict] = []
    for name, spec in profile["signals"].items():
        if name in signals:
            events += _signal_events(name, signals[name], spec)
    events += _ocr_events(ocr)
    for h in keyword_hits:
        events.append({"t": h["t"], "start": h["t"], "end": h["end"], "type": "keyword", "source": "speech",
                       "strength": 1.0, "text": h["keyword"], "weight": h["weight"]})
    for b in bookmarks:
        events.append({"t": b, "start": b, "end": b, "type": "bookmark", "source": "user", "strength": 1.0})

    specs = profile["events"]
    for e in events:
        spec = specs.get(e["type"], {"label": e["type"], "score": 3, "before": 3, "after": 3, "effects": []})
        base = e.pop("weight", spec["score"])
        # la force du signal module le score entre 60 % et 100 %
        e["score"] = round(base * (0.6 + 0.4 * min(1.0, e["strength"])), 2)
        e["label"] = spec["label"]
        e["before"], e["after"] = spec["before"], spec["after"]
        e["effects"] = spec.get("effects", [])
    return sorted(events, key=lambda e: e["t"])


def _snap(t: float, segments: list[dict], direction: int, max_shift: float) -> float:
    """Recule le début (direction=-1) ou prolonge la fin (+1) jusqu'à une frontière de phrase."""
    for seg in segments:
        if seg["start"] < t < seg["end"]:
            target = seg["start"] if direction < 0 else seg["end"] + 0.25
            if abs(target - t) <= max_shift:
                return target
    return t


def build_moments(events: list[dict], segments: list[dict], duration: float, *,
                  min_len: float, max_len: float, min_score: float, max_clips: int) -> list[dict]:
    if not events:
        return []
    clusters: list[list[dict]] = []
    for e in events:
        if clusters:
            prev = clusters[-1]
            prev_end = max(x["t"] + x["after"] for x in prev)
            if e["t"] - e["before"] <= prev_end + 2.0 and e["t"] - prev[0]["t"] <= max_len:
                prev.append(e)
                continue
        clusters.append([e])

    moments = []
    for group in clusters:
        types = {e["type"] for e in group}
        # mêmes événements répétés : rendement décroissant ; types variés : bonus de combo
        by_type: dict[str, list[float]] = {}
        for e in group:
            by_type.setdefault(e["type"], []).append(e["score"])
        score = sum(sum(s * (0.5 ** k) for k, s in enumerate(sorted(v, reverse=True))) for v in by_type.values())
        score *= 1 + 0.15 * (len(types) - 1)

        start = max(0.0, min(e["t"] - e["before"] for e in group))
        end = min(duration, max(e["t"] + e["after"] for e in group))
        if end - start < min_len:
            pad = (min_len - (end - start)) / 2
            start, end = max(0.0, start - pad), min(duration, end + pad)
        if end - start > max_len:
            peak = max(group, key=lambda e: e["score"])["t"]
            start = max(0.0, min(start, peak - max_len * 0.6))
            end = min(duration, start + max_len)
        start = max(0.0, _snap(start, segments, -1, 3.0))
        end = min(duration, _snap(end, segments, +1, 4.0))

        top = max(group, key=lambda e: e["score"])
        # « Pic de volume » ou « Réaction » font de mauvais titres : on préfère une vraie action, sinon ta phrase
        weak = {"keyword", "loud", "hype_talk"}
        gameplay = [e for e in group if e["type"] not in weak]
        spoken = [e for e in group if e["type"] == "keyword"]
        if gameplay:
            title = max(gameplay, key=lambda e: e["score"])["label"]
        elif spoken:
            title = max(spoken, key=lambda e: e["score"])["text"].capitalize()
        else:
            title = top["label"]
        # la phrase du joueur fait la meilleure accroche ; sinon le nom de l'action
        hook = max(spoken, key=lambda e: e["score"])["text"] if spoken else title
        moments.append({
            "start": round(start, 2), "end": round(end, 2), "score": round(score, 1),
            "title": title, "hook": hook, "peak": top["t"], "events": group,
        })

    moments = [m for m in moments if m["score"] >= min_score]
    moments.sort(key=lambda m: m["score"], reverse=True)
    chosen: list[dict] = []
    for m in moments:
        if all(m["end"] <= c["start"] or m["start"] >= c["end"] for c in chosen):
            chosen.append(m)
        if len(chosen) >= max_clips:
            break
    for i, m in enumerate(sorted(chosen, key=lambda m: m["start"])):
        m["id"] = i
    return sorted(chosen, key=lambda m: m["start"])
