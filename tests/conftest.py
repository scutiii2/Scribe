import asyncio
from pathlib import Path

import pytest

from src.config import Settings
from src.engine import PCM_BYTES_PER_SECOND, Segment, Transcript
from src.errors import AudioRejected, EngineFailed


def audio(seconds: float = 1.0, bad: bool = False) -> bytes:
    """Fake 'audio': the bytes are the PCM the fake engine 'decodes'."""
    return b"BAD" if bad else b"\x01\x00" * int(PCM_BYTES_PER_SECOND / 2 * seconds)


class FakeEngine:
    model_name = "fake.en"

    def __init__(self, delay: float = 0.0, fail: bool = False):
        self.transcribe_calls = 0
        self.delay, self.fail = delay, fail

    async def decode(self, path: Path) -> bytes:
        data = path.read_bytes()
        if data.startswith(b"BAD"):
            raise AudioRejected("That file is not audio Scribe can read.")
        return data

    async def transcribe(self, pcm: bytes) -> Transcript:
        self.transcribe_calls += 1
        await asyncio.sleep(self.delay)
        if self.fail:
            raise EngineFailed("Transcription failed. Try again.")
        return Transcript("hello world", [Segment(0.0, 1.0, "hello"), Segment(1.0, 2.0, "world")], "en")


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, max_seconds=10, max_bytes=1_000_000, timeout_s=2)


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine()
