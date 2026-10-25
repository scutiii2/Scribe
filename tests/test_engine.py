import shutil
import subprocess

import pytest

from src.engine import PCM_BYTES_PER_SECOND, WhisperEngine
from src.errors import AudioRejected

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


@needs_ffmpeg
async def test_decode_a_generated_tone(tmp_path):
    wav = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(wav)], check=True
    )
    pcm = await WhisperEngine(tmp_path, "base.en", "ffmpeg").decode(wav)
    assert abs(len(pcm) / PCM_BYTES_PER_SECOND - 1.0) < 0.1


@needs_ffmpeg
async def test_decode_rejects_garbage(tmp_path):
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"not audio at all")
    with pytest.raises(AudioRejected):
        await WhisperEngine(tmp_path, "base.en", "ffmpeg").decode(junk)
