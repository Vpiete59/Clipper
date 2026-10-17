"""Transcription mot à mot avec faster-whisper (GPU)."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

_model = None
_model_name = None
_lock = threading.Lock()


def _expose_torch_cuda_dlls() -> None:
    """CTranslate2 cherche cublas/cuDNN dans le PATH : on lui prête ceux livrés avec PyTorch."""
    import torch

    lib = Path(torch.__file__).parent / "lib"
    if lib.is_dir():
        os.add_dll_directory(str(lib))
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")


def _get_model(name: str):
    global _model, _model_name
    with _lock:
        if _model is None or _model_name != name:
            _expose_torch_cuda_dlls()
            from faster_whisper import WhisperModel

            try:
                _model = WhisperModel(name, device="cuda", compute_type="float16")
            except Exception:  # pas de CUDA utilisable : repli CPU, plus lent
                _model = WhisperModel(name, device="cpu", compute_type="int8")
            _model_name = name
        return _model


def transcribe(
    wav: Path,
    model_name: str = "large-v3",
    language: str | None = "fr",
    vocabulary: list[str] | None = None,
    progress: Callable[[float], None] | None = None,
) -> list[dict]:
    """Renvoie une liste de segments {start, end, text, words:[{start,end,word,prob}]}.

    `vocabulary` (noms propres du jeu) est injecté dans le prompt initial : c'est ce qui
    évite à Whisper d'écrire « butcher » ou « bounty » de travers.
    """
    model = _get_model(model_name)
    prompt = None
    if vocabulary:
        prompt = "Partie de jeu vidéo commentée. Vocabulaire : " + ", ".join(vocabulary) + "."
    from .media import load_wav

    samples, _ = load_wav(wav)  # WAV 16 kHz mono déjà prêt : on évite le décodage PyAV
    segments, info = model.transcribe(
        samples,
        language=None if language in (None, "", "auto") else language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        initial_prompt=prompt,
        condition_on_previous_text=False,  # limite les hallucinations en boucle sur les bruits de jeu
        beam_size=5,
    )
    result = []
    for seg in segments:
        words = [
            {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip(), "prob": round(w.probability, 3)}
            for w in (seg.words or [])
            if w.word.strip()
        ]
        # Whisper invente parfois du texte sur du bruit pur : on jette les segments très peu sûrs
        if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
            continue
        result.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip(), "words": words})
        if progress and info.duration:
            progress(min(1.0, seg.end / info.duration))
    return result
