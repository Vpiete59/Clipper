"""Accès aux médias via ffmpeg/ffprobe : infos, audio, échantillonnage d'images."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class MediaInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    audio_tracks: int


def probe(path: str | Path) -> MediaInfo:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True, creationflags=NO_WINDOW,
    ).stdout
    data = json.loads(out)
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    num, den = (int(x) for x in video.get("r_frame_rate", "30/1").split("/"))
    return MediaInfo(
        path=str(path),
        duration=float(data["format"]["duration"]),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=num / den if den else 30.0,
        audio_tracks=sum(1 for s in data["streams"] if s["codec_type"] == "audio"),
    )


def extract_audio(path: str | Path, out_wav: Path, track: int = 0, sample_rate: int = 16000, channels: int = 1) -> Path:
    """Extrait une piste audio en WAV (16 kHz mono pour Whisper, 44,1 kHz stéréo pour Demucs)."""
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-i", str(path), "-map", f"0:a:{track}",
         "-ac", str(channels), "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(out_wav)],
        check=True, creationflags=NO_WINDOW,
    )
    return out_wav


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    import soundfile as sf

    audio, sr = sf.read(str(path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio, sr


def sample_frames(path: str | Path, fps: float, width: int, height: int) -> Iterator[tuple[float, np.ndarray]]:
    """Décode la vidéo à `fps` images/s et renvoie (temps, image RGB) au fil de l'eau."""
    cmd = [FFMPEG, "-v", "error", "-hwaccel", "auto", "-i", str(path),
           "-vf", f"fps={fps},scale={width}:{height}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    frame_size = width * height * 3
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    try:
        index = 0
        while True:
            buf = proc.stdout.read(frame_size)
            if len(buf) < frame_size:
                break
            yield index / fps, np.frombuffer(buf, np.uint8).reshape(height, width, 3)
            index += 1
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def thumbnail(path: str | Path, at: float, out: Path, width: int = 480) -> Path:
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-ss", f"{at:.2f}", "-i", str(path), "-frames:v", "1",
         "-vf", f"scale={width}:-2", str(out)],
        check=True, creationflags=NO_WINDOW,
    )
    return out
