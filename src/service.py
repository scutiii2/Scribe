"""Upload and transcribe: validate, store, cache lookup, transcribe under a semaphore."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from src.config import Settings
from src.contract import SegmentOut, TranscribeResult
from src.engine import PCM_BYTES_PER_SECOND, SttEngine
from src.errors import AudioRejected, EngineFailed, FileNotFound, IdentityRequired
from src.store import AudioStore, StoredAudio


class ScribeService:
    def __init__(self, engine: SttEngine, store: AudioStore, settings: Settings) -> None:
        self._engine, self._store, self._settings = engine, store, settings
        self._slots = asyncio.Semaphore(settings.concurrency)
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    async def upload(self, owner: str, filename: str, data: bytes) -> tuple[StoredAudio, float]:
        if not owner:
            raise IdentityRequired("Scribe needs to know who is asking.")
        duration = await self._probe(data)
        if duration > self._settings.max_seconds:
            raise AudioRejected(f"That audio is longer than {self._settings.max_seconds} seconds.")
        file_id = AudioStore.file_id(owner, data)
        stored = await asyncio.to_thread(self._store.put, owner, file_id, data, filename, duration)
        return stored, self._store.expires_at(stored)

    async def _probe(self, data: bytes) -> float:
        """Decode a temporary copy: ffmpeg needs a seekable file for some formats (m4a)."""
        staging = self._settings.staging_dir
        await asyncio.to_thread(staging.mkdir, parents=True, exist_ok=True)

        def write() -> Path:
            handle = tempfile.NamedTemporaryFile(dir=staging, delete=False)
            with handle:
                handle.write(data)
            return Path(handle.name)

        path = await asyncio.to_thread(write)
        try:
            return len(await self._engine.decode(path)) / PCM_BYTES_PER_SECOND
        finally:
            await asyncio.to_thread(path.unlink, missing_ok=True)

    async def transcribe(self, owner: str, file_id: str, timestamps: bool) -> TranscribeResult:
        if not owner:
            raise IdentityRequired("Scribe needs to know who is asking.")
        key = (owner, file_id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                stored = await asyncio.to_thread(self._store.get, owner, file_id)
                if stored is None:
                    raise FileNotFound("That audio file expired or does not exist. Attach it again.")
                payload = await asyncio.to_thread(self._store.get_transcript, owner, file_id, self._engine.model_name)
                cached = payload is not None
                if payload is None:
                    payload = await self._run(owner, stored)
        finally:
            if not lock.locked() and not getattr(lock, "_waiters", None):
                self._locks.pop(key, None)
        segments = [SegmentOut(**s) for s in payload["segments"]] if timestamps else None
        return TranscribeResult(
            text=payload["text"], duration_s=stored.duration_s, language=payload["language"],
            segments=segments, cached=cached,
            message=f"Transcribed {stored.duration_s:.0f} s of audio ({len(payload['text'].split())} words).",
        )

    async def _run(self, owner: str, stored: StoredAudio) -> dict:
        pcm = await self._engine.decode(stored.path)
        try:
            async with self._slots:
                transcript = await asyncio.wait_for(self._engine.transcribe(pcm), self._settings.timeout_s)
        except TimeoutError as error:
            raise EngineFailed("Transcription took too long. Try a shorter file.") from error
        payload = {
            "text": transcript.text, "language": transcript.language,
            "segments": [{"start_s": s.start_s, "end_s": s.end_s, "text": s.text} for s in transcript.segments],
        }
        await asyncio.to_thread(self._store.put_transcript, owner, stored.file_id, self._engine.model_name, payload)
        return payload
