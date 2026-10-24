"""Sous-titres ASS animés façon Shorts : groupes de 1 à 3 mots, mot courant surligné et « pop »."""

from __future__ import annotations

import re
from typing import Callable

STYLES = {
    # nom : (police, taille, couleur texte, couleur surlignage, contour)
    "bold_pop": ("Arial Black", 84, "&H00FFFFFF", "&H0000E5FF", 6),
    "clean": ("Segoe UI Semibold", 70, "&H00FFFFFF", "&H00FFFFFF", 4),
    "fire": ("Impact", 92, "&H00FFFFFF", "&H00245BFF", 7),
}


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def _fr_typo(token: str) -> str:
    """Typographie française : espace insécable (\\h en ASS) avant ? ! : ; — « NON ? » et pas « NON? »."""
    if token in ("?", "!", ":", ";"):
        return "\\h" + token
    return re.sub(r"(?<=\w)([?!:;]+)$", r"\\h\1", token)


def glues_left(word: str) -> bool:
    """Whisper découpe les élisions (« d » + « 'accord ») : ces morceaux se collent au mot précédent."""
    return word[:1] in "'’-.,!?…)" or word[:1] == ""


def join_words(words: list[str]) -> str:
    out = ""
    for w in words:
        out += w if (not out or glues_left(w) or out.endswith(("'", "’", "-"))) else " " + w
    return out


def _chunks(words: list[dict], max_words: int = 3, max_gap: float = 0.6, max_dur: float = 1.4) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    for w in words:
        if chunks:
            cur = chunks[-1]
            # une élision ne doit jamais être séparée de son mot
            if glues_left(w["word"]) or cur[-1]["word"].endswith(("'", "’")):
                cur.append(w)
                continue
            ends_sentence = cur[-1]["word"][-1:] in ".!?"
            if (len(cur) < max_words and w["start"] - cur[-1]["end"] <= max_gap
                    and w["end"] - cur[0]["start"] <= max_dur and not ends_sentence):
                cur.append(w)
                continue
        chunks.append([w])
    return chunks


def build_ass(
    words: list[dict],
    duration: float,
    remap: Callable[[float], float],
    style: str = "bold_pop",
    y_ratio: float = 0.70,
    hook: str | None = None,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """`words` en temps source ; `remap` convertit vers le temps du clip (ralentis compris)."""
    font, size, color, hl, outline = STYLES.get(style, STYLES["bold_pop"])
    y = int(height * y_ratio)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Sub,{font},{size},{color},{hl},&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,{outline},3,5,60,60,0,1",
        f"Style: Hook,{font},{int(size * 0.95)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,3,18,0,8,80,80,170,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    if hook:
        # bandeau d'accroche : apparaît en rebond puis disparaît après 2,8 s
        lines.append(
            f"Dialogue: 1,{_ts(0)},{_ts(min(2.8, duration))},Hook,,0,0,0,,"
            "{\\fad(80,250)\\fscx70\\fscy70\\t(0,180,\\fscx105\\fscy105)\\t(180,300,\\fscx100\\fscy100)\\3c&H0000E5FF&}"
            + _esc(hook.upper())
        )

    chunks = _chunks(words)
    for ci, chunk in enumerate(chunks):
        texts = [_fr_typo(_esc(w["word"]).upper()) for w in chunk]
        # un groupe s'efface au plus tard quand le suivant apparaît : jamais deux lignes superposées
        hard_end = remap(chunks[ci + 1][0]["start"]) if ci + 1 < len(chunks) else duration
        for i, w in enumerate(chunk):
            start = remap(w["start"])
            end = remap(chunk[i + 1]["start"]) if i + 1 < len(chunk) else min(remap(w["end"]) + 0.15, hard_end)
            if end <= start or start >= duration:
                continue
            line = ""
            for j, txt in enumerate(texts):
                piece = txt
                if j == i:
                    piece = "{\\c" + hl + "&\\fscx112\\fscy112\\t(0,90,\\fscx100\\fscy100)}" + txt + "{\\c" + color + "&}"
                glue = j == 0 or txt.startswith("\\h") or glues_left(txt) or texts[j - 1].endswith(("'", "’", "-"))
                line += piece if glue else " " + piece
            pop = "{\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)}" if i == 0 else ""
            lines.append(
                f"Dialogue: 0,{_ts(start)},{_ts(min(end, duration))},Sub,,0,0,0,,"
                + f"{{\\pos({width // 2},{y})}}" + pop + line
            )
    return "\n".join(lines) + "\n"
