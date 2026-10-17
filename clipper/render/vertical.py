"""Rendu d'un moment en clip vertical 1080x1920 avec effets de rétention.

Effets (activables dans les réglages, déclenchés par les événements du moment) :
- slowmo      : ralenti x0.5 autour de l'action
- punch_zoom  : zoom brusque qui revient en douceur
- shake       : tremblement de caméra amorti
- flash       : éclair blanc
- hook_title  : bandeau d'accroche les 2,8 premières secondes
- progress_bar: barre de progression en bas (incite à regarder jusqu'au bout)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..media import FFMPEG, NO_WINDOW
from .subtitles import build_ass

W, H = 1080, 1920
MAX_SLOWMO = 2


def _pieces(moment: dict, effects: dict) -> list[tuple[float, float, float]]:
    """Découpe le moment en morceaux (début, fin, vitesse) en temps relatif au début du clip."""
    start, end = moment["start"], moment["end"]
    total = end - start
    windows: list[list[float]] = []
    if effects.get("slowmo"):
        peaks = sorted((e for e in moment["events"] if "slowmo" in e["effects"]), key=lambda e: -e["score"])
        for e in peaks[:MAX_SLOWMO]:
            a, b = max(0.0, e["t"] - start - 0.4), min(total, e["t"] - start + 1.0)
            if b - a > 0.3:
                windows.append([a, b])
    windows.sort()
    merged: list[list[float]] = []
    for w in windows:
        if merged and w[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], w[1])
        else:
            merged.append(w)
    pieces, cursor = [], 0.0
    for a, b in merged:
        if a > cursor:
            pieces.append((cursor, a, 1.0))
        pieces.append((a, b, 0.5))
        cursor = b
    if cursor < total:
        pieces.append((cursor, total, 1.0))
    return pieces


def _remapper(pieces: list[tuple[float, float, float]], origin: float):
    def remap(t_src: float) -> float:
        rel, out = t_src - origin, 0.0
        for a, b, speed in pieces:
            if rel <= a:
                break
            out += (min(rel, b) - a) / speed
        return out
    return remap


def _sum_expr(times: list[float], template: str) -> str:
    return "+".join(template.format(T=f"{t:.3f}") for t in times) or "0"


def _reframe(layout: str, orientation: str, facecam: list[float], zoom: str, shake: str) -> str:
    """Graphe [vc] -> [vr] : passage en 1080x1920 avec zoom/tremblement pilotés par le temps."""
    zoom_scale = (
        f"scale=w='trunc({W}*({zoom})/2)*2':h='trunc({H}*({zoom})/2)*2':eval=frame,"
        f"crop={W}:{H}:x='(iw-ow)/2+{shake}':y='(ih-oh)/2+0.6*({shake})'"
    )
    if orientation == "portrait":
        return f"[vc]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{zoom_scale}[vr]"
    if layout == "blur_fit":
        return (
            f"[vc]split[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:3,eq=brightness=-0.12[bgb];"
            f"[fg]scale={W}:-2[fgs];[bgb][fgs]overlay=(W-w)/2:(H-h)/2,{zoom_scale}[vr]"
        )
    if layout == "facecam_split":
        x0, y0, x1, y1 = facecam
        top_h, bot_h = 640, H - 640
        return (
            f"[vc]split[cam][game];"
            f"[cam]crop=iw*{x1 - x0:.4f}:ih*{y1 - y0:.4f}:iw*{x0:.4f}:ih*{y0:.4f},"
            f"scale={W}:{top_h}:force_original_aspect_ratio=increase,crop={W}:{top_h}[camv];"
            f"[game]crop=ih*{W}/{bot_h}:ih,scale=w='trunc({W}*({zoom})/2)*2':h='trunc({bot_h}*({zoom})/2)*2':eval=frame,"
            f"crop={W}:{bot_h}:x='(iw-ow)/2+{shake}':y='(ih-oh)/2'[gamev];"
            f"[camv][gamev]vstack[vr]"
        )
    # center_crop : la visée FPS est au centre, c'est le cadrage le plus naturel
    return f"[vc]crop=ih*9/16:ih,scale={W}:{H},{zoom_scale}[vr]"


def render_clip(
    source: str,
    moment: dict,
    segments: list[dict],
    out_path: Path,
    *,
    orientation: str,
    layout: str = "center_crop",
    facecam: list[float] | None = None,
    effects: dict | None = None,
    subtitle_style: str = "bold_pop",
    subtitle_y: float = 0.70,
    hook: str | None = None,
    fps: float = 60,
) -> Path:
    effects = effects or {}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    start, end = moment["start"], moment["end"]
    pieces = _pieces(moment, effects)
    remap = _remapper(pieces, start)
    out_dur = remap(end)

    ev_times = lambda name: sorted({round(remap(e["t"]), 3) for e in moment["events"]  # noqa: E731
                                    if name in e["effects"] and effects.get(name) and start <= e["t"] <= end})
    punch = ev_times("punch_zoom")[:4]
    shakes = ev_times("shake")[:4]
    flashes = ev_times("flash")[:3]

    base = 1.06 if shakes else 1.0
    zoom = f"min(1.35,{base}+" + _sum_expr(punch, "0.16*exp(-pow((t-{T})/0.35,2))") + ")"
    shake = _sum_expr(shakes, "gte(t,{T})*lt(t,{T}+0.9)*28*exp(-(t-{T})*4.5)*sin(t*57)")

    # --- graphe : morceaux (ralentis) -> concat -> recadrage -> effets -> sous-titres
    parts, labels = [], []
    for k, (a, b, speed) in enumerate(pieces):
        parts.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{speed}[v{k}]")
        parts.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,atempo={speed}[a{k}]")
        labels.append(f"[v{k}][a{k}]")
    parts.append(f"{''.join(labels)}concat=n={len(pieces)}:v=1:a=1[vc0][ac]")
    parts.append(f"[vc0]fps={min(fps, 60):.3f}[vc]")
    parts.append(_reframe(layout, orientation, facecam or [0, 0, 0.25, 0.25], zoom, shake))

    post = []
    if flashes:
        post.append("eq=brightness='" + _sum_expr(flashes, "0.55*exp(-pow((t-{T})/0.07,2))") + "':eval=frame")
    ass_path = out_path.with_suffix(".ass")
    words = [w for seg in segments for w in seg["words"] if start - 0.05 <= w["start"] < end]
    ass_path.write_text(
        build_ass(words, out_dur, remap, subtitle_style, subtitle_y,
                  hook if effects.get("hook_title") else None),
        encoding="utf-8-sig",
    )
    post.append(f"subtitles={ass_path.name}")
    if effects.get("progress_bar"):
        post.append(f"drawbox=x=0:y=ih-12:w='iw*t/{out_dur:.3f}':h=12:color=0xFFE500@0.95:t=fill")
    parts.append("[vr]" + ",".join(post) + ",format=yuv420p[vout]")
    graph = ";".join(parts)

    def run(codec: list[str]) -> subprocess.CompletedProcess:
        cmd = [FFMPEG, "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", source,
               "-filter_complex", graph, "-map", "[vout]", "-map", "[ac]", *codec,
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path.name]
        return subprocess.run(cmd, cwd=out_path.parent, capture_output=True, text=True, creationflags=NO_WINDOW)

    # ~12 Mb/s : qualité visuellement intacte, les plateformes recompressent de toute façon
    res = run(["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", "10M",
               "-maxrate", "14M", "-bufsize", "28M"])
    if res.returncode != 0:
        res = run(["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", "14M", "-bufsize", "28M"])
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué : {res.stderr[-1500:]}")
    return out_path
