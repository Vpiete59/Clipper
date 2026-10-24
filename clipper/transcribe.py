"""Transcription française mot à mot : voix isolée → Whisper → recalage précis de chaque mot.

1. Demucs sépare les voix du reste (tirs, ambiance) : Whisper n'entend plus le jeu.
2. faster-whisper large-v3 transcrit par passages courts (≤ 15 s), avec un prompt en
   français naturel : il ponctue, et ne dérive plus sur les longs monologues.
3. L'aligneur MMS (torchaudio) recale chaque mot sur l'audio, comme WhisperX : le
   karaoké des sous-titres tombe pile sur la parole.
"""

from __future__ import annotations

import os
import re
import threading
import unicodedata
from pathlib import Path
from typing import Callable

import numpy as np

_model = None
_model_name = None
_aligner = None
_lock = threading.Lock()

SR = 16000


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


# ---------------------------------------------------------------- 1. voix isolée

def isolate_vocals(source_wav: Path, out_wav: Path, progress: Callable[[float], None] | None = None) -> Path:
    """Garde uniquement les voix (la tienne et celles de Discord) d'un WAV 44,1 kHz stéréo."""
    import soundfile as sf
    import torch
    import torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    model = get_model("htdemucs")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    audio, sr = sf.read(str(source_wav), dtype="float32", always_2d=True)
    wav = torch.from_numpy(audio.T)  # (canaux, échantillons)
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)
    vocals_idx = model.sources.index("vocals")
    chunk = sr * 60  # minute par minute : la mémoire reste raisonnable sur des sessions de 3 h
    out = []
    for i, start in enumerate(range(0, wav.shape[1], chunk)):
        piece = wav[:, start:start + chunk]
        ref = piece.mean(0)
        norm = (piece - ref.mean()) / (ref.std() + 1e-8)
        with torch.no_grad():
            sources = apply_model(model, norm[None].to(device), split=True, overlap=0.1, progress=False)[0]
        vocals = sources[vocals_idx].cpu() * (ref.std() + 1e-8) + ref.mean()
        out.append(vocals.mean(0))
        if progress:
            progress(min(1.0, (start + chunk) / wav.shape[1]))
    mono = torch.cat(out)[None]
    mono = torchaudio.functional.resample(mono, sr, SR)
    sf.write(str(out_wav), mono[0].numpy(), SR, subtype="PCM_16")
    return out_wav


# ---------------------------------------------------------------- 2. Whisper

def _prompt(vocabulary: list[str] | None) -> str:
    # un prompt écrit comme une vraie conversation ponctuée pousse Whisper à ponctuer et à rester en français
    base = "Bon, on part sur la carte ? Ouais, vas-y. Attention, il y a quelqu'un à droite ! Je l'ai eu, il est à terre."
    if vocabulary:
        base += " On parle de " + ", ".join(vocabulary[:40]) + "."
    return base


def _whisper(samples: np.ndarray, model_name: str, language: str | None, vocabulary: list[str] | None,
             progress: Callable[[float], None] | None) -> list[dict]:
    from faster_whisper import BatchedInferencePipeline

    model = _get_model(model_name)
    # mode par lots : chaque passage de parole (≤ 15 s) est transcrit séparément. En mode
    # classique, Whisper recolle tout en fenêtres de 30 s, perd la ponctuation et dérive.
    batched = BatchedInferencePipeline(model=model)
    segments, info = batched.transcribe(
        samples,
        language=None if language in (None, "", "auto") else language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200, "max_speech_duration_s": 15},
        chunk_length=15,
        batch_size=16,
        initial_prompt=_prompt(vocabulary),
        condition_on_previous_text=False,
        beam_size=5,
        temperature=[0.0, 0.2, 0.4],
        compression_ratio_threshold=2.2,
    )
    result = []
    for seg in segments:
        words = [
            {"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word.strip(), "prob": round(w.probability, 3)}
            for w in (seg.words or []) if w.word.strip()
        ]
        # Whisper invente parfois du texte sur du bruit pur : on jette les segments très peu sûrs
        if not words or (seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0):
            continue
        result.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "text": seg.text.strip(), "words": words})
        if progress and info.duration:
            progress(min(1.0, seg.end / info.duration))
    return result


# ---------------------------------------------------------------- 3. recalage des mots

def _get_aligner():
    global _aligner
    with _lock:
        if _aligner is None:
            import torch
            from torchaudio.pipelines import MMS_FA

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = MMS_FA.get_model(with_star=False).to(device).eval()
            _aligner = (model, MMS_FA.get_tokenizer(), MMS_FA.get_aligner(), device, set(MMS_FA.get_dict()))
        return _aligner


def _romanize(word: str, alphabet: set[str]) -> str:
    """« Désolé » → « desole » : l'aligneur MMS ne connaît que les lettres latines de base."""
    word = unicodedata.normalize("NFD", word.lower().replace("’", "'"))
    word = "".join(c for c in word if unicodedata.category(c) != "Mn")
    return "".join(c for c in word if c in alphabet)


def align(samples: np.ndarray, segments: list[dict]) -> list[dict]:
    """Recale le début et la fin de chaque mot sur l'audio (les mots non alignables gardent l'heure Whisper)."""
    import torch

    model, tokenizer, aligner, device, alphabet = _get_aligner()
    alphabet.discard("*")
    for seg in segments:
        # groupes de mots séparés par les pauses que Whisper a vues : sur un long bloc plein de
        # silences, l'aligneur pourrait sinon accrocher un mot 20 s trop tôt
        groups: list[list[int]] = []
        for i, w in enumerate(seg["words"]):
            if groups and w["start"] - seg["words"][groups[-1][-1]]["end"] < 1.0:
                groups[-1].append(i)
            else:
                groups.append([i])
        for idx in groups:
            words = [seg["words"][i] for i in idx]
            a = max(0, int((words[0]["start"] - 0.4) * SR))
            b = min(len(samples), int((words[-1]["end"] + 0.4) * SR))
            clip = samples[a:b]
            keys = [(i, _romanize(seg["words"][i]["word"], alphabet)) for i in idx]
            keys = [(i, k) for i, k in keys if k.strip("'")]
            if not keys or len(clip) < SR * 0.2:
                continue
            try:
                with torch.inference_mode():
                    emission, _ = model(torch.from_numpy(clip)[None].to(device))
                spans = aligner(emission[0], tokenizer([k for _, k in keys]))
            except Exception:  # texte impossible à aligner (bruit, mot inventé) : on garde Whisper
                continue
            ratio = len(clip) / emission.shape[1] / SR
            for (i, _), span in zip(keys, spans):
                w = seg["words"][i]
                start = a / SR + span[0].start * ratio
                end = a / SR + span[-1].end * ratio
                if abs(start - w["start"]) < 1.5:  # garde-fou : un recalage énorme est une erreur d'alignement
                    w["start"], w["end"] = round(start, 3), round(end, 3)
        # les mots non alignés (chiffres…) se calent entre leurs voisins
        ws = seg["words"]
        for i, w in enumerate(ws):
            prev_end = ws[i - 1]["end"] if i else seg["start"]
            if w["start"] < prev_end:
                w["start"] = prev_end
            if w["end"] <= w["start"]:
                w["end"] = round(w["start"] + 0.12, 3)
        seg["start"], seg["end"] = ws[0]["start"], ws[-1]["end"]
    return segments


def _merge_punctuation(segments: list[dict]) -> None:
    """« ? » ou « ! » seul (Whisper en fait parfois un mot) est rattaché au mot d'avant."""
    for seg in segments:
        merged: list[dict] = []
        for w in seg["words"]:
            if merged and re.fullmatch(r"[?!.,:;…]+", w["word"]):
                merged[-1]["word"] += w["word"]
                merged[-1]["end"] = max(merged[-1]["end"], w["end"])
            else:
                merged.append(w)
        seg["words"] = merged


def _fix_orphans(segments: list[dict]) -> None:
    """Whisper date parfois le 1er mot d'une phrase (« Il ») à la fin du passage d'avant, 20 s trop tôt :
    un mot isolé, sans ponctuation finale, loin de la suite, est recollé juste avant le mot suivant."""
    for seg in segments:
        ws = seg["words"]
        for i in range(len(ws) - 1):
            w, nxt = ws[i], ws[i + 1]
            gap = nxt["start"] - w["end"]
            prev_gap = w["start"] - ws[i - 1]["end"] if i else 0.0
            if gap > 1.5 and not w["word"].endswith((".", "!", "?", "…", ",")) and len(w["word"]) <= 4 and prev_gap < 1.0:
                length = max(0.12, min(0.4, w["end"] - w["start"]))
                w["end"] = round(nxt["start"] - 0.02, 3)
                w["start"] = round(w["end"] - length, 3)


def split_sentences(segments: list[dict], max_len: float = 12.0) -> list[dict]:
    """Une phrase par segment (fin de phrase ou silence > 0,8 s) : la timeline et les coupes restent précises."""
    out: list[dict] = []
    for seg in segments:
        cur: list[dict] = []
        for i, w in enumerate(seg["words"]):
            cur.append(w)
            nxt = seg["words"][i + 1] if i + 1 < len(seg["words"]) else None
            ends = w["word"].endswith((".", "!", "?", "…"))
            pause = nxt is not None and nxt["start"] - w["end"] > 0.8
            too_long = cur[-1]["end"] - cur[0]["start"] > max_len and w["word"].endswith(",")
            if nxt is None or ends or pause or too_long:
                text = " ".join(x["word"] for x in cur)
                text = re.sub(r" (?=['’,.…]|-\w)", "", text)  # « peut -être » → « peut-être »
                out.append({"start": cur[0]["start"], "end": cur[-1]["end"], "text": text, "words": cur})
                cur = []
    return out


def transcribe(
    wav: Path,
    model_name: str = "large-v3",
    language: str | None = "fr",
    vocabulary: list[str] | None = None,
    progress: Callable[[float], None] | None = None,
    vocals: Path | None = None,
) -> list[dict]:
    """Segments {start, end, text, words:[{start,end,word,prob}]}.

    `vocals` : WAV 16 kHz des voix isolées (meilleur), sinon on transcrit `wav` tel quel.
    """
    from .media import load_wav

    samples, _ = load_wav(vocals or wav)
    segments = _whisper(samples, model_name, language, vocabulary, progress)
    try:
        segments = align(samples, segments)
    except Exception:  # l'alignement est un bonus : sans lui, on garde l'horodatage Whisper
        pass
    _merge_punctuation(segments)
    _fix_orphans(segments)
    segments = split_sentences(segments)
    for seg in segments:
        seg["text"] = re.sub(r"\s+", " ", seg["text"]).strip()
    return segments
