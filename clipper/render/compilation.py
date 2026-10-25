"""Vidéo YouTube 16:9 qui enchaîne plusieurs parties condensées.

Chaque partie : carton-titre (« PARTIE 2 » + bilan sur l'image floutée de son meilleur
moment, coup sourd), puis ses chapitres en version condensée. Fondu au noir entre deux
parties, transitions rapides à l'intérieur. Livrée avec chapitres YouTube, .srt et miniature.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .. import scoring
from ..media import FFMPEG, NO_WINDOW, probe
from . import sfx
from .longform import VIDEO_ARGS, H, W, _fmt, _srt, best_moment, render_chapter
from .montage import build_montage
from .subtitles import _esc, _ts
from .thumbnail import best_frame, make_thumbnail

CARD_S = 3.2
XFADE = 0.45
OUTCOME = {"extracted": "Extraction réussie", "dead": "Mort au combat", "unknown": ""}


def match_summary(match: dict) -> str:
    bits = [OUTCOME[match["outcome"]]] if OUTCOME[match["outcome"]] else []
    if match.get("kills"):
        bits.append(f"{match['kills']} kill{'s' if match['kills'] > 1 else ''}")
    if match.get("boss"):
        bits.append("Boss tué")
    if match.get("bounty"):
        bits.append("Prime")
    return " · ".join(bits)


def _card_ass(title: str, subtitle: str) -> str:
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Big,Georgia,150,&H0096D8F2,&H0096D8F2,&H00000000,&H00000000,-1,0,0,0,100,100,14,0,1,6,4,5,0,0,0,1",
        "Style: Sub,Georgia,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,4,0,1,3,2,5,0,0,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 0,{_ts(0.15)},{_ts(CARD_S)},Big,,0,0,0,,{{\\pos({W // 2},{H // 2 - 50})\\fad(250,300)\\fsp30\\t(0,900,\\fsp14)}}{_esc(title.upper())}",
        f"Dialogue: 0,{_ts(0.6)},{_ts(CARD_S)},Sub,,0,0,0,,{{\\pos({W // 2},{H // 2 + 85})\\fad(300,300)}}{_esc(subtitle)}",
    ]) + "\n"


def render_card(source: str, t: float, title: str, subtitle: str, work: Path, name: str) -> Path:
    """Carton-titre : image floutée et assombrie qui avance doucement, titre doré, coup sourd."""
    still = work / f"{name}.jpg"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-i", source, "-frames:v", "1",
                    "-vf", f"scale={W}:{H}", "-q:v", "2", still.name], cwd=work, check=True, capture_output=True,
                   creationflags=NO_WINDOW)
    ass = work / f"{name}.ass"
    ass.write_text(_card_ass(title, subtitle), encoding="utf-8-sig")
    frames = int(CARD_S * 60)
    clip = work / f"{name}.mp4"
    res = subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-loop", "1", "-t", f"{CARD_S}", "-i", still.name, "-i", str(sfx.path("impact")),
         "-filter_complex",
         f"[0:v]boxblur=22:2,eq=brightness=-0.28:saturation=0.8,"
         f"zoompan=z='1+0.0006*on':d={frames}:s={W}x{H}:fps=60,subtitles={ass.name},format=yuv420p[v];"
         f"[1:a]adelay=150|150,apad,atrim=0:{CARD_S},aformat=sample_rates=48000:channel_layouts=stereo[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{CARD_S}", *VIDEO_ARGS, "-c:a", "aac", "-b:a", "192k", clip.name],
        cwd=work, capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg (carton-titre) a échoué : {res.stderr[-1500:]}")
    return clip


def render_compilation(parts: list[dict], out_path: Path, *, title: str = "", game_name: str = "Hunt: Showdown",
                       progress=None) -> dict:
    """`parts` : [{"source", "match", "analysis"}] dans l'ordre voulu.

    Écrit à côté de la vidéo : <nom>_chapitres.txt (une ligne par partie), <nom>.srt et
    <nom>_miniature.jpg (meilleure partie).
    """
    work = out_path.parent / f"_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    transitions: list[str] = []
    card_index: list[int] = []
    srt_pieces: list[tuple[int, dict, list]] = []
    for n, p in enumerate(parts, start=1):
        match, analysis, source = p["match"], p["analysis"], p["source"]
        inside = [e for e in analysis["events"] if match["start"] <= e["t"] <= match["end"]]
        chapters = scoring.build_chapters(inside, match["start"], match["end"], match["outcome"], "condense")
        chapters = scoring.snap_chapters(chapters, analysis["segments"], match["start"], match["end"])
        if not chapters:
            continue
        if clips:
            transitions.append("fadeblack")  # changement de partie : fondu au noir
        card_index.append(len(clips))
        at = best_frame(source, best_moment({**match, "chapters": chapters}))
        clips.append(render_card(source, at, f"Partie {n}", match_summary(match), work, f"p{n:02d}_card"))
        for i, c in enumerate(chapters):
            transitions.append("fade" if i == 0 else ("smoothleft" if i % 2 else "slideup"))
            idx = len(clips)
            clips.append(render_chapter(source, c, work, f"p{n:02d}_c{i:02d}"))
            srt_pieces.append((idx, c, analysis["segments"]))
        if progress:
            progress(n / (len(parts) + 1))
    if not clips:
        raise ValueError("Aucune des parties choisies n'a de chapitre à montrer")

    build_montage(clips, out_path, transitions=transitions, xfade=XFADE, video_args=VIDEO_ARGS)

    # position de chaque morceau dans la vidéo finale (les transitions se chevauchent de XFADE)
    starts, cursor = [], 0.0
    for clip in clips:
        starts.append(cursor)
        cursor += probe(clip).duration - XFADE
    lines = []
    for k, idx in enumerate(card_index):
        p = parts[k]
        summary = match_summary(p["match"])
        lines.append(f"{'0:00' if k == 0 else _fmt(starts[idx])} Partie {k + 1}{' — ' + summary if summary else ''}")
    chapters_txt = out_path.with_name(out_path.stem + "_chapitres.txt")
    chapters_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    srt_parts = []
    for idx, c, segs in srt_pieces:
        srt_parts.append(_srt(segs, [(c["start"], c["end"], starts[idx])]))
    srt = out_path.with_suffix(".srt")
    # renumérotation globale : chaque bloc a été numéroté depuis 1
    blocks = [b.split("\n", 1)[1] for part in srt_parts for b in part.split("\n\n") if b.strip() and "\n" in b]
    srt.write_text("\n".join(f"{i}\n{b.strip()}\n" for i, b in enumerate(blocks, start=1)), encoding="utf-8")

    best = max(parts, key=lambda p: p["match"].get("potential", 0))
    thumb = out_path.with_name(out_path.stem + "_miniature.jpg")
    make_thumbnail(best["source"], best_frame(best["source"], best_moment(best["match"])), thumb,
                   text=(title or f"{len(card_index)} PARTIES").upper(), subtitle=game_name.upper())
    shutil.rmtree(work, ignore_errors=True)
    if progress:
        progress(1.0)
    return {"video": out_path, "chapters": chapters_txt, "srt": srt, "thumbnail": thumb, "parts": len(card_index)}
