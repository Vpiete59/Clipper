"""Surveillance des dossiers OBS : chaque enregistrement terminé entre dans la bibliothèque."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import jobs, library, media, pipeline
from .config import Settings

VIDEO_EXT = {".mkv", ".mp4", ".mov", ".flv"}
_observer: Observer | None = None


def _is_finished(path: Path, quiet_s: float = 8.0) -> bool:
    """OBS écrit le fichier en continu : on attend qu'il ne grossisse plus et soit libéré."""
    try:
        size = path.stat().st_size
        time.sleep(quiet_s)
        if path.stat().st_size != size or size == 0:
            return False
        fd = os.open(path, os.O_RDWR)  # échoue tant qu'OBS garde le fichier ouvert en écriture
        os.close(fd)
        return True
    except OSError:
        return False


def too_short(path: Path, settings: Settings) -> bool:
    try:
        return media.probe(path).duration < settings.auto_min_duration
    except Exception:  # illisible pour l'instant : on laisse la main à l'utilisateur
        return True


def register(path: Path, auto: bool | None = None) -> dict | None:
    """`auto=None` : appel de la surveillance OBS. Les vidéos courtes (extraits, Kinevir…)
    restent alors dans « Dans tes dossiers OBS » sans être ajoutées ni analysées."""
    settings = Settings.load()
    if path.suffix.lower() not in VIDEO_EXT or not path.exists():
        return None
    if auto is None and too_short(path, settings):
        return None
    vid = pipeline.video_id(path)
    existing = library.get_video(vid)
    video = existing or library.add_video(vid, str(path), settings.default_game)
    previous = pipeline.load_analysis(vid) if existing is None else None
    if previous:  # analyse déjà faite (ex. en ligne de commande) : on la reprend telle quelle
        jobs._after_analysis(vid, previous)  # noqa: SLF001
        return library.get_video(vid)
    if existing is None and (settings.auto_process if auto is None else auto):
        jobs.enqueue("analyze", vid)
    return video


def _wait_and_register(path: Path) -> None:
    for _ in range(2000):  # jusqu'à ~4-5 h d'enregistrement
        if _is_finished(path):
            register(path)
            return


class _Handler(FileSystemEventHandler):
    def _handle(self, raw: str) -> None:
        path = Path(raw)
        if path.suffix.lower() in VIDEO_EXT:
            threading.Thread(target=_wait_and_register, args=(path,), daemon=True).start()

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):  # remux mkv -> mp4 d'OBS
        if not event.is_directory:
            self._handle(event.dest_path)


def start() -> None:
    global _observer
    stop()
    settings = Settings.load()
    _observer = Observer()
    for folder in settings.watch_folders:
        if Path(folder).is_dir():
            _observer.schedule(_Handler(), folder, recursive=False)
    _observer.start()


def stop() -> None:
    global _observer
    if _observer:
        _observer.stop()
        _observer = None


def scan_existing(folder: str, limit: int = 50) -> list[Path]:
    files = [p for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
