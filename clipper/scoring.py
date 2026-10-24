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


def _ocr_events(detections: list[dict], specs: dict) -> list[dict]:
    """Une notification reste affichée plusieurs secondes : on regroupe les lectures successives.

    `merge_s` (profil) : écart max entre deux lectures d'un même événement. L'objectif
    « Cible à bannir » ou la vue spectateur restent des minutes à l'écran : un seul événement.
    """
    events: list[dict] = []
    for d in sorted(detections, key=lambda d: d["t"]):
        last = next((e for e in reversed(events) if e["type"] == d["event"]), None)
        gap = specs.get(d["event"], {}).get("merge_s", 3.0)
        if last and d["t"] - last["end"] <= gap:
            last["end"] = d["t"]
            last["strength"] = max(last["strength"], d["confidence"])
            continue
        events.append({"t": d["t"], "start": d["t"], "end": d["t"], "type": d["event"], "source": "ocr",
                       "strength": d["confidence"], "text": d["text"]})
    return events


def _pvp_events(events: list[dict], profile: dict) -> list[dict]:
    """Combat contre des joueurs : un cri d'agonie (ou ta mort) entouré de tirs.

    Les monstres de l'IA ne crient pas comme un chasseur : cri + rafales = affrontement
    JcJ. On remonte jusqu'au premier tir pour que le clip montre tout le combat.
    """
    if "pvp_fight" not in profile["events"]:
        return []
    shots = sorted(e["t"] for e in events if e["type"] == "gunfight")
    anchors = sorted((e for e in events if e["type"] in ("death_cry", "death")), key=lambda e: e["t"])
    out: list[dict] = []
    for a in anchors:
        near = [s for s in shots if a["t"] - 35 <= s <= a["t"] + 10]
        if not near and a["type"] == "death":
            continue  # mort sans tir : chute, piège, monstre…
        if out and a["t"] - out[-1]["t"] < 15:  # même combat, plusieurs cris
            out[-1]["kills"] += 1
            out[-1]["end"] = a["t"]
            continue
        first = min([*near, a["t"]])
        out.append({"t": a["t"], "start": first, "end": a["t"], "type": "pvp_fight", "source": "combo",
                    "strength": min(1.0, 0.55 + 0.15 * len(near)), "kills": 1, "lead": a["t"] - first})
    for e in out:
        dead = f"{e['kills']} mort{'s' if e['kills'] > 1 else ''}"
        e["text"] = f"{dead} · {round(e['lead'])} s de combat" if e["lead"] >= 3 else dead
    return out


def detect_events(profile: dict, signals: dict[str, np.ndarray], ocr: list[dict],
                  keyword_hits: list[dict], bookmarks: list[float]) -> list[dict]:
    events: list[dict] = []
    for name, spec in profile["signals"].items():
        if name in signals:
            events += _signal_events(name, signals[name], spec)
    events += _ocr_events(ocr, profile["events"])
    for h in keyword_hits:
        events.append({"t": h["t"], "start": h["t"], "end": h["end"], "type": "keyword", "source": "speech",
                       "strength": 1.0, "text": h["keyword"], "weight": h["weight"]})
    for b in bookmarks:
        events.append({"t": b, "start": b, "end": b, "type": "bookmark", "source": "user", "strength": 1.0})

    events += _pvp_events(events, profile)

    specs = profile["events"]
    for e in events:
        spec = specs.get(e["type"], {"label": e["type"], "score": 3, "before": 3, "after": 3, "effects": []})
        base = e.pop("weight", spec["score"])
        # la force du signal module le score entre 60 % et 100 %
        e["score"] = round(base * (0.6 + 0.4 * min(1.0, e["strength"])), 2)
        e["label"] = spec["label"]
        e["highlight"] = spec.get("highlight", True)
        e["before"], e["after"] = spec["before"], spec["after"]
        if e["type"] == "pvp_fight":  # le clip commence au premier tir du combat
            e["before"] = max(spec["before"], e.pop("lead") + 3)
            e["score"] = round(e["score"] + 4 * (e.pop("kills") - 1), 2)
        e["effects"] = spec.get("effects", [])
    return sorted(events, key=lambda e: e["t"])


PVP_HOOKS = ["Ça tire de partout", "Duel dans le bayou", "Ils étaient prêts", "Combat à bout portant", "Personne ne lâche"]


def _action_hook(group: list[dict], title: str) -> str:
    """Accroche variée pour un combat, pour ne pas enchaîner dix « Combat JcJ » sur un fil."""
    fight = next((e for e in group if e["type"] == "pvp_fight"), None)
    if not fight:
        return title
    if any(e["type"] == "death" for e in group):
        return "Il ne m'a pas raté"
    kills = int(fight.get("text", "1").split()[0]) if fight.get("text", "").split()[0].isdigit() else 1
    if kills >= 2:
        return f"{kills} chasseurs au tapis"
    return PVP_HOOKS[int(fight["t"]) % len(PVP_HOOKS)]


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
    events = [e for e in events if e.get("highlight", True)]
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
        # seules les phrases fortes font une accroche (« putain » ou « quoi » non)
        spoken = [e for e in group if e["type"] == "keyword" and e["score"] >= 6]
        if gameplay:
            title = max(gameplay, key=lambda e: e["score"])["label"]
        elif spoken:
            title = max(spoken, key=lambda e: e["score"])["text"].capitalize()
        else:
            title = top["label"]
        # la phrase du joueur fait la meilleure accroche ; sinon le nom de l'action
        hook = max(spoken, key=lambda e: e["score"])["text"] if spoken else _action_hook(group, title)
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
    used: set[str] = set()
    for i, m in enumerate(sorted(chosen, key=lambda m: m["start"])):
        m["id"] = i
        if m["hook"] in PVP_HOOKS:  # deux combats de la même partie n'ont pas la même accroche
            free = [h for h in PVP_HOOKS if h not in used] or PVP_HOOKS
            m["hook"] = m["hook"] if m["hook"] in free else free[0]
        used.add(m["hook"])
    return sorted(chosen, key=lambda m: m["start"])


# ---------------------------------------------------------------- parties

CHAPTERS = {
    # type: (avant, après, priorité) — la priorité décide qui reste si le résumé est trop long
    "pvp_fight": (None, 3.0, 1),
    "extracted": (7.0, 1.5, 1),
    "bounty": (3.0, 3.0, 2),
    "boss_down": (6.0, 2.0, 2),
    "death": (6.0, 1.5, 2),
    "clue": (2.5, 2.0, 3),
    "rival_bounty": (1.5, 3.0, 4),
    "gunfight": (4.0, 3.0, 3),
    "laughter": (4.0, 2.0, 4),
}
CHAPTER_LABELS = {
    "pvp_fight": "Combat", "extracted": "Extraction réussie", "bounty": "Prime en poche",
    "boss_down": "Boss abattu", "death": "Mort au combat", "clue": "Indice", "rival_bounty": "Une équipe a la prime",
    "gunfight": "Ça tire", "laughter": "Fou rire",
}


def build_matches(events: list[dict], duration: float, budget: float = 75.0) -> list[dict]:
    """Découpe la vidéo en parties (début → fin) et choisit les chapitres de chaque résumé.

    Début : « La chasse est ouverte » (sinon le début de la vidéo). Fin : « Résumé de mission »,
    sinon le début de la partie suivante, sinon la fin de la vidéo — utile quand on oublie
    d'arrêter l'enregistrement.
    """
    starts = [e["t"] for e in events if e["type"] == "match_start"]
    ends = [e["t"] for e in events if e["type"] == "match_end"]
    gameplay = [e for e in events if e.get("highlight", True)]
    if not starts:
        if not gameplay:
            return []
        starts = [0.0]
    elif gameplay and gameplay[0]["t"] < starts[0] - 60:
        starts = [0.0, *starts]  # l'enregistrement a démarré en pleine partie

    matches = []
    for i, s in enumerate(starts):
        nxt = starts[i + 1] if i + 1 < len(starts) else duration
        end = next((e for e in ends if s < e <= nxt), None)
        stop = end if end is not None else nxt
        inside = [e for e in events if s <= e["t"] <= stop]
        if stop - s < 120 or not any(e.get("highlight", True) for e in inside):
            continue
        extracted = next((e for e in inside if e["type"] == "extracted"), None)
        dead = next((e for e in inside if e["type"] == "death"), None)
        outcome = "extracted" if extracted else ("dead" if dead else "unknown")
        if extracted:
            stop = min(stop, extracted["t"] + 4)
        chapters = _chapters([e for e in inside if e["t"] <= stop], budget)
        matches.append({
            "id": len(matches), "start": round(s, 2), "end": round(stop, 2), "outcome": outcome,
            "clues": sum(1 for e in inside if e["type"] == "clue"),
            "fights": sum(1 for e in inside if e["type"] == "pvp_fight"),
            "bounty": any(e["type"] == "bounty" for e in inside),
            "chapters": chapters,
        })
    return matches


def _chapters(events: list[dict], budget: float) -> list[dict]:
    picks = []
    for e in events:
        if e["type"] not in CHAPTERS:
            continue
        before, after, prio = CHAPTERS[e["type"]]
        if before is None:  # combat : du premier tir au cri, plafonné (les temps morts seront accélérés)
            before = min(14.0, max(4.0, e.get("before", 6) - 2))
        picks.append({"type": e["type"], "label": CHAPTER_LABELS[e["type"]], "t": e["t"], "prio": prio,
                      "start": round(max(0.0, e["t"] - before), 2), "end": round(e["t"] + after, 2), "score": e["score"]})
    # indices : trois au plus, les premiers trouvés
    clues = [c for c in picks if c["type"] == "clue"]
    shots = sorted((c for c in picks if c["type"] == "gunfight"), key=lambda c: -c["score"])
    picks = [c for c in picks if c["type"] not in ("clue", "gunfight")] + clues[:3] + shots[:3]
    # mort et combat qui se recouvrent : on garde le combat, qui la contient
    picks.sort(key=lambda c: (c["prio"], -c["score"]))
    kept: list[dict] = []
    total = 0.0
    for c in picks:
        if any(c["start"] < k["end"] and c["end"] > k["start"] for k in kept):
            continue
        length = c["end"] - c["start"]
        if total + length > budget and c["prio"] > 1:
            continue
        kept.append(c)
        total += length
    kept.sort(key=lambda c: c["t"])
    n_clues = sum(1 for c in kept if c["type"] == "clue")
    k = 0
    for c in kept:
        if c["type"] == "clue":
            k += 1
            c["label"] = f"Indice {k}/{n_clues}" if n_clues > 1 else "Indice"
        c.pop("prio")
    return kept
