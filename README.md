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
| Voix isolées | Demucs htdemucs (GPU) : le jeu et les tirs sont retirés avant transcription | `clipper/transcribe.py` |
| Transcription française | faster-whisper large-v3 par passages ≤ 15 s, prompt français ponctué | `clipper/transcribe.py` |
| Recalage des mots | aligneur forcé MMS (torchaudio), typographie française dans les sous-titres | `clipper/transcribe.py`, `clipper/render/subtitles.py` |
| Sons + empreintes | AST AudioSet : rires, cris, tirs, explosions, et empreinte de chaque demi-seconde | `clipper/cues/audio.py` |
| Sons appris | cri de mort (Hunt) appris par l'exemple, avec contre-exemples 👍/👎 | `clipper/sounds.py` |
| HUD du jeu | EasyOCR plein écran 1×/s, lignes gardées avec leur position, règles par zone | `clipper/cues/visual.py` |
| Fusion → moments | scores, combos, combats JcJ (cri + tirs), alignement sur les phrases | `clipper/scoring.py` |
| Parties | début « La chasse est ouverte », fin « Résumé de mission » ; chapitres du résumé | `clipper/scoring.py` |
| Rendu 9:16 | NVENC : teaser, ralenti, accélération des temps morts, zoom, tremblement, flash, sons d'impact, sous-titres animés | `clipper/render/vertical.py` |
| Chat Twitch | export TwitchDownloader posé à côté de la VOD : pics de messages = moments forts | `clipper/cues/chat.py` |
| Résumé de partie (short) | chapitres titrés (indices, boss trouvé/tué, prime, confrontations, kills, extraction), compteur de kills, whoosh | `clipper/render/story.py` |
| Vidéo longue YouTube | partie en 16:9, chapitres YouTube, .srt, miniature | `clipper/render/longform.py` |
| Publication | textes par plateforme, ouverture de la page d'upload, suivi | `clipper/publish.py` |

## Chat Twitch (optionnel)

Télécharge le chat de ta VOD avec [TwitchDownloader](https://github.com/lay295/TwitchDownloader)
(« Chat Download », format JSON) et pose le fichier à côté de la vidéo, avec le même nom
(`ma-vod.json` pour `ma-vod.mp4`) ou un nom contenant « chat ». Clipper le lit au prochain
recalcul : les pics de messages deviennent des moments « Le chat s'enflamme ».

## Ajouter un jeu

Copier `games/hunt_showdown.json`, puis renseigner :
- `ocr_rules` (16:9, plein écran) ou `ocr_zones` (vertical) : textes du jeu à reconnaître et zone de l'écran ;
- `events` : score, marges avant/après, effets, `merge_s` (texte qui reste affiché), `highlight` ;
- `keywords`, `vocabulary`, `hashtags`, `learned_sounds`.

`"extends": "generic"` hérite de la détection audio et vocale de base. Les règles OCR se
ré-appliquent sans relancer l'analyse : corriger un motif puis « Recalculer » suffit.
