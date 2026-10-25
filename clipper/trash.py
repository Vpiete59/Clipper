"""Suppressions : tout part dans la corbeille Windows, jamais en suppression définitive.

Chaque fonction vérifie que le fichier visé appartient bien à Clipper (dossier de sortie,
vidéo de la bibliothèque, dossier surveillé) avant d'y toucher.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from send2trash import send2trash

from . import library, pipeline
from .config import Settings

SIDECARS = (".ass", ".json")  # sous-titres et métadonnées rendus à côté de chaque clip


def _inside(path: Path, folders: list[str]) -> bool:
    p = path.resolve()
    return any(p.is_relative_to(Path(f).resolve()) for f in folders if f)


def to_trash(path: Path) -> bool:
    if path.exists():
        send2trash(str(path))
        return True
    return False


def delete_render(path: str) -> None:
    p = Path(path)
    if not _inside(p, [Settings.load().output_folder]):
        raise PermissionError("Ce fichier n'est pas un clip rendu par Clipper")
    to_trash(p)
    for ext in SIDECARS:
        to_trash(p.with_suffix(ext))
    library.delete_render(path)


def delete_video(vid: str, source: bool, clips: bool) -> dict:
    """Retire la vidéo de la bibliothèque ; en option, met à la corbeille la source et/ou ses clips."""
    v = library.get_video(vid)
    if v is None:
        raise KeyError(vid)
    trashed = []
    if clips:
        for r in library.list_renders(vid):
            delete_render(r["path"])
            trashed.append(r["path"])
        out_dir = Path(Settings.load().output_folder) / v["name"]
        if out_dir.is_dir() and not any(out_dir.iterdir()):
            out_dir.rmdir()
    if source and to_trash(Path(v["path"])):
        trashed.append(v["path"])
    # le cache d'analyse (audio, voix, empreintes) se recrée : inutile de l'envoyer à la corbeille
    shutil.rmtree(pipeline.work_dir(vid), ignore_errors=True)
    library.delete_video(vid)
    return {"trashed": trashed}


def delete_inbox_file(path: str) -> None:
    """Enregistrement pas encore analysé, dans un dossier surveillé : directement à la corbeille."""
    p = Path(path)
    if not _inside(p, Settings.load().watch_folders):
        raise PermissionError("Ce fichier n'est pas dans un dossier surveillé")
    to_trash(p)
