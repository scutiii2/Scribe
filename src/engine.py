"""Speech-to-text engines. ffmpeg decodes (async subprocess); the model runs in a worker thread."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.errors import AudioRejected, EngineFailed

PCM_BYTES_PER_SECOND = 16000 * 2  # 16 kHz, mono, 16-bit


@dataclass(frozen=True)
class Segment:
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True)
class Transcript:
    text: str
    segments: list[Segment]
    language: str


class SttEngine(Protocol):
    model_name: str

    async def decode(self, path: Path) -> bytes:
        """16 kHz mono s16le PCM. Raises AudioRejected when ffmpeg cannot read the file."""

    async def transcribe(self, pcm: bytes) -> Transcript:
        """Raises EngineFailed."""


class WhisperEngine:
    def __init__(self, models_dir: Path, model_name: str, ffmpeg: str) -> None:
        self.model_name = model_name
        self._models_dir = Path(models_dir)
        self._ffmpeg = ffmpeg
        self._model = None
        self._lock = asyncio.Lock()

    async def decode(self, path: Path) -> bytes:
        try:
            process = await asyncio.create_subprocess_exec(
                self._ffmpeg, "-v", "error", "-nostdin", "-i", str(path),
                "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise EngineFailed("Audio decoding is unavailable.") from error
        pcm, _ = await process.communicate()
        if process.returncode != 0 or not pcm:
            raise AudioRejected("That file is not audio Scribe can read.")
        return pcm

    def _load(self):
        from faster_whisper import WhisperModel  # heavy import, kept out of module load

        return WhisperModel(
            self.model_name, device="cpu", compute_type="int8", download_root=str(self._models_dir)
        )

    def _run(self, pcm: bytes) -> Transcript:
        import numpy as np

        audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
        segments, _ = self._model.transcribe(audio, language="en", beam_size=1)
        parts = [Segment(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments]
        return Transcript(" ".join(p.text for p in parts if p.text), parts, "en")

    async def transcribe(self, pcm: bytes) -> Transcript:
        try:
            async with self._lock:  # one model load, even for concurrent first calls
                if self._model is None:
                    self._model = await asyncio.to_thread(self._load)
            return await asyncio.to_thread(self._run, pcm)
        except Exception as error:  # model errors vary; never leak their text (may hold paths)
            raise EngineFailed("Transcription failed. Try again.") from error
