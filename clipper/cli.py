"""Ligne de commande : python -m clipper.cli analyze|render <vidéo> [--game hunt_showdown]."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import pipeline
from .config import Settings
from .render import build_montage, render_clip


def _progress(stage: str, p: float) -> None:
    sys.stdout.write(f"\r  {stage:<14} {p * 100:5.1f} %")
    sys.stdout.flush()
    if p >= 1:
        sys.stdout.write("\n")


def main() -> None:
    ap = argparse.ArgumentParser(prog="clipper")
    ap.add_argument("command", choices=["analyze", "render"])
    ap.add_argument("video")
    ap.add_argument("--game", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--montage", action="store_true")
    args = ap.parse_args()
    settings = Settings.load()
    game = args.game or settings.default_game

    vid = pipeline.video_id(args.video)
    analysis = pipeline.load_analysis(vid)
    if args.command == "analyze" or analysis is None:
        t0 = time.time()
        analysis = pipeline.analyze(args.video, game, settings, _progress)
        print(f"\nAnalyse en {time.time() - t0:.0f} s — {len(analysis['events'])} événements, {len(analysis['moments'])} moments")
    elif args.game and args.game != analysis["game"]:
        analysis = pipeline.rescore(vid, settings, args.game)

    for match in analysis.get("matches", []):
        print(f"  PARTIE {match['id'] + 1} {match['start']:7.1f}-{match['end']:7.1f}s {match['outcome']} "
              f"— {', '.join(c['label'] for c in match['chapters'])}")
    for m in analysis["moments"]:
        kinds = ", ".join(sorted({e["label"] for e in m["events"]}))
        print(f"  #{m['id']} {m['start']:7.1f}-{m['end']:7.1f}s  score {m['score']:5.1f}  {m['title']:<16} [{kinds}]")

    if args.command == "render":
        out_dir = Path(args.out or settings.output_folder) / Path(args.video).stem
        clips = []
        for m in analysis["moments"]:
            t0 = time.time()
            path = render_clip(
                args.video, m, analysis["segments"], out_dir / f"clip_{m['id']:02d}.mp4",
                orientation=analysis["orientation"], layout=settings.layout, facecam=settings.facecam_rect,
                effects=settings.effects, subtitle_style=settings.subtitle_style, subtitle_y=settings.subtitle_y_portrait if analysis["orientation"] == "portrait" else settings.subtitle_y,
                hook=m.get("hook", m["title"]), fps=analysis["fps"],
                quiet=pipeline.quiet_mask(vid, analysis["segments"], m["start"], m["end"]),
            )
            clips.append(path)
            print(f"  rendu {path.name} en {time.time() - t0:.1f} s")
        if args.montage and analysis.get("matches"):
            from .jobs import _render_kwargs
            from .render.story import render_story

            for match in analysis["matches"]:
                t0 = time.time()
                path = render_story(args.video, match, analysis, out_dir / f"partie_{match['id'] + 1:02d}.mp4",
                                    render_kwargs=_render_kwargs(settings, analysis), effects=settings.effects,
                                    quiet=lambda a, b: pipeline.quiet_mask(vid, analysis["segments"], a, b))
                print(f"  résumé {path.name} ({len(match['chapters'])} chapitres) en {time.time() - t0:.0f} s")
        elif args.montage and clips:
            ordered = sorted(clips, key=lambda p: -next(m["score"] for m in analysis["moments"] if p.stem.endswith(f"{m['id']:02d}")))
            print("  montage :", build_montage(ordered, out_dir / "montage.mp4"))


if __name__ == "__main__":
    main()
