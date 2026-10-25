"""Vidéo longue YouTube (16:9) d'une partie : chapitres titrés, chapitres YouTube, .srt et miniature.

Les shorts font découvrir la chaîne ; la vidéo longue fait rester. Même découpage que le
résumé, mais en grand format, sans accélération, avec des chapitres plus larges.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..media import FFMPEG, NO_WINDOW, probe
from ..scoring import snap_chapters
from .montage import XFADE, build_montage
from .subtitles import _esc, _ts, join_words
from .thumbnail import best_frame, make_thumbnail

W, H = 1920, 1080
VIDEO_ARGS = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "21", "-b:v", "16M", "-maxrate", "24M", "-bufsize", "48M"]


def _fmt(t: float) -> str:
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def _title_ass(label: str, duration: float) -> str:
    """Titre de chapitre en bas à gauche, façon notification de Hunt (bande noire, lettres dorées)."""
    return "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: T,Georgia,58,&H0096D8F2,&H0096D8F2,&H00000000,&H50000000,-1,0,0,0,100,100,5,0,3,20,0,1,90,0,120,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 0,{_ts(0)},{_ts(min(3.5, duration))},T,,0,0,0,,{{\\fad(300,400)}}{_esc(label.upper())}",
    ]) + "\n"


def _glue_fragments(segments: list[dict]) -> list[dict]:
    """Recolle les morceaux d'élision coupés par d'anciennes transcriptions (« C » + « 'est toi… »)."""
    out: list[dict] = []
    for seg in segments:
        first = seg["words"][0]["word"] if seg["words"] else ""
        if out and (first[:1] in "'’" or len(out[-1]["text"].strip()) <= 2):
            prev = out[-1]
            out[-1] = {**prev, "end": seg["end"], "words": prev["words"] + seg["words"],
                       "text": join_words([w["word"] for w in prev["words"] + seg["words"]])}
        else:
            out.append(seg)
    return out


def _srt(segments: list[dict], pieces: list[tuple[float, float, float]]) -> str:
    """Sous-titres YouTube : chaque phrase reportée sur la timeline de la vidéo longue."""
    segments = _glue_fragments(segments)
    out, n = [], 0
    for src_a, src_b, out_a in pieces:
        for seg in segments:
            if src_a <= seg["start"] < src_b:
                a = out_a + seg["start"] - src_a
                b = out_a + min(seg["end"], src_b) - src_a
                n += 1
                ts = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x % 1 * 1000):03d}"  # noqa: E731
                out.append(f"{n}\n{ts(a)} --> {ts(b)}\n{join_words([w['word'] for w in seg['words']])}\n")
    return "\n".join(out)


def render_chapter(source: str, c: dict, work: Path, name: str) -> Path:
    """Un chapitre en 16:9 1080p60 avec son titre façon Hunt ; audio en 48 kHz stéréo pour s'enchaîner."""
    dur = c["end"] - c["start"]
    ass = work / f"{name}.ass"
    ass.write_text(_title_ass(c["label"], dur), encoding="utf-8-sig")
    clip = work / f"{name}.mp4"
    res = subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-ss", f"{c['start']:.3f}", "-t", f"{dur:.3f}", "-i", source,
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=60,subtitles={ass.name},format=yuv420p",
         *VIDEO_ARGS, "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", clip.name],
        cwd=work, capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg (vidéo longue) a échoué : {res.stderr[-1500:]}")
    return clip


def render_longform(source: str, match: dict, analysis: dict, out_path: Path, *, game_name: str = "Hunt: Showdown") -> dict:
    """Rend la vidéo, et écrit à côté : <nom>.srt, <nom>_chapitres.txt et <nom>_miniature.jpg."""
    # jamais de coupure au milieu d'une phrase
    chapters = snap_chapters(match["chapters"], analysis["segments"], match["start"], match["end"])
    match = {**match, "chapters": chapters}
    if not chapters:
        raise ValueError("Aucun chapitre dans cette partie")
    work = out_path.parent / f"_{out_path.stem}"
    work.mkdir(parents=True, exist_ok=True)
    clips = [render_chapter(source, c, work, f"c{i:02d}") for i, c in enumerate(chapters)]

    build_montage(clips, out_path, video_args=VIDEO_ARGS)

    # position de chaque chapitre dans la vidéo finale (les fondus se chevauchent de XFADE)
    starts, cursor = [], 0.0
    for clip in clips:
        starts.append(cursor)
        cursor += probe(clip).duration - XFADE
    lines = [f"{_fmt(s)} {c['label']}" for s, c in zip(starts, chapters)]
    if lines:
        lines[0] = f"0:00 {chapters[0]['label']}"  # YouTube exige un premier chapitre à 0:00
    chapters_txt = out_path.with_name(out_path.stem + "_chapitres.txt")
    chapters_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    srt = out_path.with_suffix(".srt")
    srt.write_text(_srt(analysis["segments"], [(c["start"], c["end"], s) for c, s in zip(chapters, starts)]), encoding="utf-8")

    thumb = out_path.with_name(out_path.stem + "_miniature.jpg")
    _thumbnail(source, match, thumb, game_name)
    shutil.rmtree(work, ignore_errors=True)
    return {"video": out_path, "chapters": chapters_txt, "srt": srt, "thumbnail": thumb}


THUMB_TEXT = {"extracted": "ON S'EN SORT !", "dead": "ÇA TOURNE MAL…", "unknown": "PARTIE FOLLE"}
PRIORITY = ["kill", "boss_down", "bounty", "confrontation", "extracted"]


def best_moment(match: dict) -> float:
    best = next((c for kind in PRIORITY for c in match["chapters"] if c["type"] == kind), match["chapters"][0])
    return best["t"]


def _thumbnail(source: str, match: dict, out: Path, game_name: str) -> Path:
    """Miniature automatique : image la plus lisible du moment le plus fort, gros texte jaune."""
    return make_thumbnail(source, best_frame(source, best_moment(match)), out,
                          text=THUMB_TEXT[match["outcome"]], subtitle=game_name.upper())
