# Clipper

Clipping automatique de tes parties : Clipper surveille tes dossiers OBS, repère les moments forts,
sous-titre en français et rend des clips verticaux 9:16 avec effets de rétention, plus un montage auto.

Le pipeline s'inspire de l'architecture de Powder (abandonné), démontée à partir de l'install locale,
mais tout repose sur des briques libres et des modèles publics. Aucun modèle Powder n'est réutilisé.

## Lancer

Double-clic sur `Clipper.cmd`. La première fois, il installe Python 3.12 + CUDA et télécharge les modèles (~4 Go).

En développement :

```bash
uv run python -m clipper.app --no-window
```

```bash
cd ui && npm run dev
```

En ligne de commande :

```bash
uv run python -m clipper.cli render "D:\Streaming\partie.mkv" --game hunt_showdown --montage
```

## Pipeline

| Étape | Brique | Fichier |
|---|---|---|
| Transcription mot à mot | faster-whisper large-v3 (GPU), vocabulaire du jeu injecté | `clipper/transcribe.py` |
| Sons (rires, cris, tirs, explosions) | AST AudioSet (`MIT/ast-finetuned-audioset`) | `clipper/cues/audio.py` |
| Pics de volume | RMS vs niveau ambiant glissant | `clipper/cues/audio.py` |
| Mots-clés, débit de parole | transcription | `clipper/cues/speech.py` |
| HUD du jeu | EasyOCR sur des zones définies par jeu | `clipper/cues/visual.py` |
| Fusion → moments | scores, combos, alignement sur les phrases | `clipper/scoring.py` |
| Rendu 9:16 | ffmpeg + NVENC : ralenti, zoom punch, tremblement, flash, sous-titres ASS animés, accroche, barre de progression | `clipper/render/` |

## Ajouter un jeu

Copier `games/hunt_showdown.json`, puis renseigner :
- `ocr_zones` : rectangles (fractions de l'image) où le jeu affiche du texte, avec les motifs à reconnaître ;
- `keywords` : expressions qui signalent un moment fort ;
- `vocabulary` : noms propres pour aider Whisper ;
- `events` : score, marges avant/après et effets de chaque événement.

`"extends": "generic"` hérite de la détection audio et vocale de base.
