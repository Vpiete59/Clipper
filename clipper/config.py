"""Chemins, réglages persistants et détection de la config OBS."""

from __future__ import annotations

import configparser
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMES_DIR = ROOT / "games"
UI_DIST = ROOT / "ui" / "dist"

DATA_DIR = Path(os.environ.get("CLIPPER_DATA", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Clipper"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"
DB_FILE = DATA_DIR / "library.db"
ANALYSIS_DIR = DATA_DIR / "analysis"
ANALYSIS_DIR.mkdir(exist_ok=True)


def detect_obs_folders() -> list[str]:
    """Dossier d'enregistrement OBS + celui du plugin Vertical Canvas s'il est installé."""
    folders = []
    main = detect_obs_recording_folder()
    if main:
        folders.append(main)
    vc = Path(os.environ.get("APPDATA", "")) / "obs-studio" / "plugin_config" / "vertical-canvas" / "config.json"
    if vc.exists():
        try:
            text = vc.read_text(encoding="utf-8")
            for m in re.finditer(r'"record_path"\s*:\s*"([^"]+)"', text):
                p = str(Path(m.group(1)))
                if Path(p).is_dir() and p not in folders:
                    folders.append(p)
        except OSError:
            pass
    return folders


def detect_obs_recording_folder() -> str | None:
    """Lit le dossier d'enregistrement du profil OBS le plus récent."""
    profiles = Path(os.environ.get("APPDATA", "")) / "obs-studio" / "basic" / "profiles"
    inis = sorted(profiles.glob("*/basic.ini"), key=lambda p: p.stat().st_mtime, reverse=True)
    for ini in inis:
        cp = configparser.RawConfigParser(strict=False)
        try:
            cp.read(ini, encoding="utf-8-sig")
        except (configparser.Error, UnicodeDecodeError):
            continue
        mode = cp.get("Output", "Mode", fallback="Simple")
        if mode == "Advanced" and cp.get("AdvOut", "RecType", fallback="Standard") == "Standard":
            path = cp.get("AdvOut", "RecFilePath", fallback=None)
        else:
            path = cp.get("SimpleOutput", "FilePath", fallback=None)
        if path and Path(path).is_dir():
            return str(Path(path))
    return None


@dataclass
class Settings:
    watch_folders: list[str] = field(default_factory=list)
    output_folder: str = str(Path.home() / "Videos" / "Clipper")
    auto_process: bool = True
    auto_min_duration: float = 180.0  # en dessous (extraits, vidéos Kinevir…), pas de traitement automatique
    default_game: str = "hunt_showdown"
    language: str = "fr"  # "auto" pour laisser Whisper deviner
    whisper_model: str = "large-v3"
    audio_track: int = 0  # piste audio utilisée pour la transcription
    max_clips: int = 8
    clip_min_s: float = 8.0
    clip_max_s: float = 45.0
    min_score: float = 12.0
    story_only_worth: bool = True  # résumés auto seulement pour les parties gagnées ou à 2 kills et plus
    story_preset: str = "action"  # rythme des résumés de partie : recit | action | express
    title_style: str = "center"  # titres de chapitre : center | hunt | banner
    subtitle_style: str = "bold_pop"
    subtitle_y: float = 0.70  # sources 16:9 recadrées
    subtitle_y_portrait: float = 0.44  # sources déjà verticales : au-dessus du HUD et de la facecam
    layout: str = "center_crop"  # center_crop | blur_fit | facecam_split
    facecam_rect: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.25, 0.25])
    effects: dict = field(default_factory=lambda: {
        "punch_zoom": True,
        "slowmo": True,
        "flash": True,
        "shake": True,
        "hook_title": True,
        "progress_bar": True,
        "teaser": False,  # pas d'aperçu avant le clip par défaut
        "speed_ramp": True,
        "sfx": True,
    })
    custom_keywords: list[str] = field(default_factory=list)
    # phrases dites en jeu (tirées de tes VOD, à compléter dans les Réglages)
    alert_phrases: list[str] = field(default_factory=lambda: [
        "y a des gens", "il y a des gens", "des gens sur nous", "j'entends des gens", "j'ai entendu", "j'entends un mec",
        "tu entends", "t'entends", "des joueurs", "y a des joueurs", "un joueur", "quelqu'un", "attends chut", "chut",
        "ils arrivent", "ils viennent", "ils sont là", "il est là", "attention", "pas loin", "derrière nous",
        "une équipe", "ça tire", "on se fait tirer", "ils sont deux", "ils sont trois", "il campe", "il y en a encore", "y a un mec", "un mec ici", "il a un snipe"])
    ally_down_phrases: list[str] = field(default_factory=lambda: [
        "je suis down", "je suis à terre", "je suis mort", "il m'a tué", "il m'a eu", "rez moi", "relève moi",
        "tu peux rez", "il me touche", "je me fais", "je meurs", "faut m'aider", "aide moi"])
    enemy_down_phrases: list[str] = field(default_factory=lambda: [
        "je l'ai mis à terre", "il est down", "il est à terre", "un de moins", "j'en ai eu un", "il est mort",
        "bien joué", "je l'ai eu", "je l'ai tué", "dans la tête", "il en reste", "j'en ai sorti un", "un mec qui est mort", "il brûle", "il crame"])
    # publication
    extra_hashtags: list[str] = field(default_factory=list)
    publish_signature: str = ""

    @classmethod
    def load(cls) -> "Settings":
        data = {}
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        s = cls(**known)
        # nouveaux effets ajoutés après coup : activés par défaut sans écraser les choix existants
        s.effects = {**cls().effects, **s.effects}
        if not s.watch_folders:
            s.watch_folders = detect_obs_folders() or [str(Path.home() / "Videos")]
        return s

    def save(self) -> None:
        SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def update(self, patch: dict) -> "Settings":
        for k, v in patch.items():
            if k in self.__dataclass_fields__:
                setattr(self, k, v)
        self.save()
        return self
