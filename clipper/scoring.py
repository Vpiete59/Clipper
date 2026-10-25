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
                  keyword_hits: list[dict], bookmarks: list[float],
                  phrase_hits: dict[str, list[dict]] | None = None, markers: list[float] | None = None) -> list[dict]:
    """`phrase_hits` : {type: occurrences} pour les phrases d'alerte / allié à terre / ennemi à terre.
    `markers` : instants du « X » de touche sur un joueur."""
    events: list[dict] = []
    for t in markers or []:
        events.append({"t": t, "start": t, "end": t + 0.3, "type": "hit_marker", "source": "visual", "strength": 1.0})
    for kind, hits in (phrase_hits or {}).items():
        if kind in profile["events"]:
            for h in hits:
                events.append({"t": h["t"], "start": h["t"], "end": h["end"], "type": kind, "source": "speech",
                               "strength": 1.0, "text": h["keyword"]})
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


def _sentence_at(t: float, segments: list[dict]) -> dict | None:
    """La phrase en cours à l'instant `t` (marge de 50 ms pour ne pas compter un bord de phrase)."""
    return next((s for s in segments if s["start"] + 0.05 < t < s["end"] - 0.05), None)


def snap_window(start: float, end: float, segments: list[dict], *, max_back: float = 6.0, max_fwd: float = 8.0,
                lo: float = 0.0, hi: float = float("inf")) -> tuple[float, float]:
    """Cale un extrait sur les phrases : on ne commence ni ne finit jamais au milieu d'une phrase.

    Début dans une phrase : on recule à son début ; si c'est trop loin, on saute la phrase
    entamée. Fin dans une phrase : on la laisse finir ; si elle est trop longue, on coupe
    juste avant elle. `lo`/`hi` : bornes à ne pas dépasser (la partie, la vidéo).
    """
    s, e = start, end
    seg = _sentence_at(s, segments)
    if seg:
        if s - seg["start"] <= max_back and seg["start"] - 0.15 >= lo:
            s = seg["start"] - 0.15
        elif seg["end"] + 0.05 < e - 3:
            s = seg["end"] + 0.05
    seg = _sentence_at(e, segments)
    if seg:
        if seg["end"] - e <= max_fwd and seg["end"] + 0.3 <= hi:
            e = seg["end"] + 0.3
        elif seg["start"] - 0.1 > s + 3:
            e = seg["start"] - 0.1
    # parole enchaînée sans respirer : on attend une vraie pause (≥ 0,6 s) pour couper
    ordered = sorted(segments, key=lambda x: x["start"])
    budget_fwd, budget_back = max_fwd, max_back
    for seg in ordered:
        if e - 0.35 < seg["start"] <= e + 0.3 and seg["end"] + 0.3 <= hi and seg["end"] - e <= budget_fwd:
            budget_fwd -= seg["end"] + 0.3 - e
            e = seg["end"] + 0.3
    for seg in reversed(ordered):
        if s - 0.45 <= seg["end"] < s + 0.15 and seg["start"] - 0.15 >= lo and s - seg["start"] <= budget_back:
            budget_back -= s - (seg["start"] - 0.15)
            s = seg["start"] - 0.15
    return round(max(lo, s), 2), round(min(hi, e), 2)


def snap_chapters(chapters: list[dict], segments: list[dict], lo: float, hi: float) -> list[dict]:
    """Applique `snap_window` à chaque chapitre, sans qu'ils se chevauchent ensuite."""
    out, prev_end = [], lo
    for c in chapters:
        s, e = snap_window(c["start"], c["end"], segments, lo=max(lo, prev_end), hi=hi)
        if e - s >= 1.0:
            out.append({**c, "start": s, "end": e})
            prev_end = e
    return out


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
        start, end = snap_window(start, end, segments, lo=0.0, hi=duration)

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
            "potential": int(min(100, round(score * 1.5))),
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

ORDINALS = ["Premier", "Deuxième", "Troisième", "Quatrième", "Cinquième", "Sixième"]

# préréglages de montage du résumé : (avant, après) par type de chapitre et budget total
PRESETS = {
    # tout le récit, en prenant le temps (l'accélération des temps morts resserre ensuite)
    "recit": {"budget": 220, "clue": (7, 6), "boss_found": (3, 6), "boss_down": (14, 5), "bounty": (6, 6),
              "fight_pad": (4, 5), "fight_max": 90, "extract": (14, 3), "death": (10, 3), "max_clues": 6},
    # l'action d'abord : indices courts, combats longs
    "action": {"budget": 150, "clue": (4, 4), "boss_found": (2, 4), "boss_down": (10, 4), "bounty": (4, 4),
               "fight_pad": (5, 6), "fight_max": 75, "extract": (10, 2), "death": (10, 3), "max_clues": 6},
    # vidéo longue YouTube 16:9 : on laisse respirer chaque moment
    "longform": {"budget": 720, "clue": (20, 12), "boss_found": (10, 15), "boss_down": (45, 12), "bounty": (15, 15),
                 "fight_pad": (15, 15), "fight_max": 180, "extract": (40, 6), "death": (25, 6), "max_clues": 6},
    # compilation YouTube de plusieurs parties : ~2 min 30 par partie
    "condense": {"budget": 160, "clue": (9, 7), "boss_found": (5, 8), "boss_down": (22, 6), "bounty": (8, 8),
                 "fight_pad": (8, 8), "fight_max": 90, "extract": (22, 4), "death": (14, 4), "max_clues": 6},
    # format court, tout tient en une minute
    "express": {"budget": 95, "clue": (4, 3), "boss_found": (2, 3), "boss_down": (8, 3), "bounty": (3, 4),
                "fight_pad": (3, 4), "fight_max": 45, "extract": (8, 2), "death": (8, 2), "max_clues": 6},
}


def build_matches(events: list[dict], duration: float, preset: str = "recit") -> list[dict]:
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
        inside = [e for e in inside if e["t"] <= stop]
        chapters = build_chapters(inside, s, stop, outcome, preset)
        match = {
            "id": len(matches), "start": round(s, 2), "end": round(stop, 2), "outcome": outcome,
            "clues": sum(1 for e in inside if e["type"] == "clue"),
            "fights": sum(1 for c in chapters if c["type"] in ("confrontation", "kill")),
            "kills": sum(1 for c in chapters if c["type"] == "kill"),
            "bounty": any(e["type"] == "bounty" for e in inside),
            "boss": any(e["type"] == "boss_down" for e in inside),
            "chapters": chapters,
        }
        match["potential"] = match_potential(match)
        # une partie mérite un résumé si on la gagne ou si on y fait plusieurs kills
        match["worth"] = outcome == "extracted" or match["kills"] >= 2
        matches.append(match)
    return matches


def match_potential(m: dict) -> int:
    """Potentiel 0-100 d'un résumé : une victoire avec des kills et la prime, c'est ce qui se partage."""
    score = (35 if m["outcome"] == "extracted" else 0) + 15 * min(m["kills"], 4) + 12 * m["bounty"]         + 8 * m["boss"] + 4 * min(m["fights"], 4) + 2 * min(m["clues"], 3)
    return int(min(100, score))


# temps forts d'un long combat : secondes gardées avant / après
BEATS = {"alert": (5, 8), "kill": (10, 4), "enemy_down": (8, 4), "ally_down": (8, 5), "end": (10, 0)}


def _fights(events: list[dict], boss_window: tuple[float, float] | None) -> list[dict]:
    """Confrontations contre des joueurs, avec tout leur cheminement.

    Un combat regroupe tirs, cris de mort (joueur abattu, allié ou ennemi) et phrases d'équipe
    (« je suis down », « un de moins »…) espacés de moins de 40 s. Il commence à la phrase
    d'alerte qui le précède (« y'a des gens », « chut »…) s'il y en a une dans la minute
    d'avant : on entend alors ce qui t'a mis la puce à l'oreille. Hors combat de boss, il
    faut au moins 3 tirs, ou un cri, ou une phrase d'équipe.
    """
    core = sorted((e for e in events if e["type"] in ("gunfight", "player_hit", "hit_marker", "death_cry", "pvp_fight",
                                                       "ally_down", "enemy_down")), key=lambda e: e["t"])
    alerts = sorted(e["t"] for e in events if e["type"] == "alert")
    deaths = [e["t"] for e in events if e["type"] == "death"]
    # vidéo sans X de touche détecté (autre jeu, format vertical) : chaque râle compte comme un kill
    has_markers = any(e["type"] == "hit_marker" for e in events)
    groups: list[list[dict]] = []
    for e in core:
        gap = e["t"] - groups[-1][-1]["t"] if groups else 1e9
        # une accalmie pleine de « il est là », « y en a encore deux » fait toujours partie du combat
        talk = groups and any(groups[-1][-1]["t"] < x < e["t"] for x in alerts)
        if gap < 40 or (talk and gap < 75):
            groups[-1].append(e)
        else:
            groups.append([e])
    out, prev_end = [], -1e9
    for g in groups:
        a, b = g[0]["t"], g[-1]["t"]
        shots = sum(1 for e in g if e["type"] in ("gunfight", "player_hit", "hit_marker"))
        team = [e for e in g if e["type"] in ("ally_down", "enemy_down")]
        # un cri tout près de « je suis down » ou de notre mort, c'est un allié qui tombe : pas un kill
        ours = [e["t"] for e in team if e["type"] == "ally_down"] + deaths
        kills: list[float] = []
        downs = 0  # chasseurs à terre sans notre X de touche : un équipier ou un ennemi, pas notre kill
        for e in g:
            if (e["type"] in ("death_cry", "pvp_fight") and not any(abs(e["t"] - x) <= 6 for x in ours)
                    and not (kills and e["t"] - kills[-1] < 4)):  # cri et fusillade du même kill
                # notre kill = un râle juste après notre X de touche ; le kill-cam se cale sur le X
                hit = next((m["t"] for m in reversed(g) if m["type"] == "hit_marker" and e["t"] - 3 <= m["t"] <= e["t"] + 0.5), None)
                if hit is not None or not has_markers:
                    kills.append(hit if hit is not None else e["t"])
                elif e["type"] == "death_cry":
                    downs += 1
        in_boss = boss_window and boss_window[0] - 5 <= a and b <= boss_window[1] + 5
        if not (kills or downs or team or (shots >= 3 and not in_boss)):
            continue
        alert = next((x for x in reversed(alerts) if max(prev_end, a - 60) <= x <= a), None)
        # les temps forts du combat, dans l'ordre : chaque alerte, kill, allié ou ennemi à terre
        beats = [(x, "alert", next((e.get("text", "") for e in events if e["type"] == "alert" and e["t"] == x), ""))
                 for x in alerts if a < x < b]
        beats += [(k, "kill", "") for k in kills]
        beats += [(e["t"], e["type"], "") for e in team]
        out.append({"start": a, "end": b, "alert": alert, "shots": shots, "kills": kills, "beats": sorted(beats), "downs": downs,
                    "ally_down": sum(1 for e in team if e["type"] == "ally_down"),
                    "enemy_down": sum(1 for e in team if e["type"] == "enemy_down"),
                    "alert_text": next((e.get("text", "") for e in events if e["type"] == "alert" and e["t"] == alert), "")})
        prev_end = b
    return out


def build_chapters(events: list[dict], m_start: float, m_end: float, outcome: str, preset: str = "recit") -> list[dict]:
    p = PRESETS.get(preset, PRESETS["recit"])
    first = lambda kind: next((e for e in events if e["type"] == kind), None)  # noqa: E731
    found, down, bounty = first("boss_found"), first("boss_down"), first("bounty")
    extracted, death = first("extracted"), first("death")
    picks: list[dict] = []

    def add(kind: str, label: str, t: float, before: float, after: float, prio: int, score: float = 10, **extra):
        picks.append({"type": kind, "label": label, "t": round(t, 2), "prio": prio, "score": score,
                      "start": round(max(m_start, t - before), 2), "end": round(min(m_end, t + after), 2), **extra})

    clues = [e for e in events if e["type"] == "clue"][: p["max_clues"]]
    for i, e in enumerate(clues):
        label = f"{ORDINALS[min(i, 5)]} indice"
        if e.get("clue_count"):  # « 1/3 » lu sous « Indice trouvé », et le boss concerné si on le connaît
            label += f" · {e['clue_count']}"
        if e.get("boss_name"):
            label += f" · {e['boss_name']}"
        add("clue", label, e["t"], *p["clue"], prio=1, score=30)  # le fil de la partie : jamais sacrifié
    if found:
        add("boss_found", "Boss trouvé", found["t"], *p["boss_found"], prio=2)
    if down:
        add("boss_down", "Boss tué", down["t"], *p["boss_down"], prio=1)
    if bounty:
        add("bounty", "Prime récupérée", bounty["t"], *p["bounty"], prio=1)
    boss_window = (found["t"], down["t"]) if found and down else None
    for f in _fights(events, boss_window):
        pad_b, pad_a = p["fight_pad"]
        start = f["alert"] - 5 if f["alert"] is not None else f["start"] - pad_b  # 5 s avant « y'a des gens »
        end = f["end"] + pad_a
        kind = "kill" if f["kills"] else "confrontation"
        label = "Ennemi tué" if f["kills"] else "Confrontation"
        if not f["kills"] and (f["ally_down"] or f["downs"]):
            label = "Allié à terre" if f["ally_down"] else "Chasseur à terre"
        extra = {"shots": f["shots"], "kills": f["kills"]}
        prio, score = (1, 15 + 3 * len(f["kills"])) if f["kills"] else (2, 8 + f["shots"] + 4 * (f["ally_down"] + f["downs"]))
        if end - start <= p["fight_max"]:
            add(kind, label, f["start"], f["start"] - start, end - f["start"], prio=prio, score=score, **extra)
        else:
            # combat trop long : on garde son cheminement, temps fort par temps fort (l'alerte et
            # le bruit qui l'a déclenchée, chaque kill, chaque allié ou ennemi à terre), puis la fin
            beats = [(f["alert"], "alert", f["alert_text"])] if f["alert"] is not None else []
            segs: list[list] = []
            for x, kind_b, text in beats + f["beats"]:
                lo, hi = BEATS[kind_b]
                s0, s1 = x - lo, x + hi
                if segs and s0 - segs[-1][1] < 6:  # deux temps forts proches : un seul passage
                    segs[-1][1] = max(segs[-1][1], s1)
                    segs[-1][3] += [k for k in f["kills"] if s0 <= k <= s1 and k not in segs[-1][3]]
                else:
                    segs.append([s0, s1, (kind_b, text), [k for k in f["kills"] if s0 <= k <= s1]])
            if not segs or f["end"] + pad_a - segs[-1][1] > 6:
                segs.append([f["end"] - 10, f["end"] + pad_a, ("end", ""), [k for k in f["kills"] if k >= f["end"] - 10]])
            for s0, s1, (kind_b, text), ks in segs:
                lab = {"alert": f"« {text.strip().capitalize()} »" if text.strip() else "Ça s'approche",
                       "kill": "Ennemi tué", "enemy_down": "Ennemi à terre", "ally_down": "Allié à terre"}.get(kind_b, label)
                k_kind = "kill" if ks else ("alert" if kind_b == "alert" else "confrontation")
                # seuls les passages avec un de nos kills sont garantis ; le reste passe si le budget le permet
                add(k_kind, lab, s0, 0, s1 - s0, prio=1 if ks else 2, score=score + (2 if ks else 0), shots=f["shots"], kills=ks)
    if extracted:
        add("extracted", "Extraction réussie", extracted["t"], *p["extract"], prio=1, score=12)
    elif death:
        add("death", "Mort au combat", death["t"], *p["death"], prio=1, score=10)

    # chevauchements : on fusionne dans le chapitre le plus important, en gardant son titre
    picks.sort(key=lambda c: (c["prio"], -c["score"]))
    kept: list[dict] = []
    total = 0.0
    for c in picks:
        clash = next((k for k in kept if c["start"] < k["end"] and c["end"] > k["start"]), None)
        if clash:
            clash["start"], clash["end"] = min(clash["start"], c["start"]), max(clash["end"], c["end"])
            clash.setdefault("also", []).append(c["label"])
            if c.get("kills"):  # le compteur de kills ne perd pas ceux du chapitre absorbé
                clash["kills"] = sorted({*clash.get("kills", []), *c["kills"]})
            continue
        length = c["end"] - c["start"]
        if total + length > p["budget"] and c["prio"] > 1:
            continue
        kept.append(c)
        total += length
    kept.sort(key=lambda c: c["t"])
    for c in kept:
        c.pop("prio")
    return kept


BOSS_NAMES = {"boucher": "Boucher", "butcher": "Boucher", "araignee": "Araignée", "spider": "Araignée",
              "assassin": "Assassin", "scrapbeak": "Scrapbeak", "rotjaw": "Rotjaw", "hellborn": "Hellborn"}


def enrich_clues(events: list[dict], ocr_lines: list[dict], matches: list[dict]) -> None:
    """Relie chaque indice à son compteur (« 1/3 », lu sous « Indice trouvé ») et à son boss.

    Avec deux boss, le compteur repart à 1/3 pour le second : chaque retour à un nombre plus
    petit fait passer au boss suivant. Les noms viennent du panneau d'objectifs (« Boucher »),
    dans l'ordre où ils apparaissent dans la partie.
    """
    import re as _re

    from .cues.visual import norm

    for m in matches:
        names: list[str] = []
        for fr in ocr_lines:
            if m["start"] <= fr["t"] <= m["end"]:
                for x, y, txt in fr["items"]:
                    n = norm(txt).strip()
                    for key, name in BOSS_NAMES.items():
                        if x < 0.35 and y < 0.45 and n.startswith(key[:5]) and name not in names:
                            names.append(name)
        boss_idx, last = 0, 0
        clues = sorted((e for e in events if e["type"] == "clue" and m["start"] <= e["t"] <= m["end"]), key=lambda e: e["t"])
        # un seul nom lu mais plus de 3 indices : il y avait 2 boss, on ne devine pas lequel
        single_name = names[0] if len(names) == 1 and len(clues) <= 3 else None
        for e in clues:
            count = None
            for fr in ocr_lines:
                if e["t"] - 2 <= fr["t"] <= e["t"] + 3:
                    for x, y, txt in fr["items"]:
                        hit = _re.fullmatch(r"\s*([123])\s*/\s*3\s*", txt)
                        if x < 0.3 and y < 0.35 and hit:
                            count = int(hit.group(1))
            if count:
                if count <= last:
                    boss_idx += 1  # le compteur repart : on est passé au 2e boss
                last = count
                e["clue_count"] = f"{count}/3"
            if single_name:
                e["boss_name"] = single_name
            elif count and boss_idx < len(names):
                e["boss_name"] = names[boss_idx]
