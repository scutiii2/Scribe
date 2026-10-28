import shutil
import subprocess
import asyncio

import pytest

from src.engine import PCM_BYTES_PER_SECOND, WhisperEngine
from src.errors import AudioRejected, EngineFailed

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


async def test_decode_bounds_ffmpeg_output_and_rejects_long_audio(tmp_path, monkeypatch):
    class Process:
        returncode = 0
        async def communicate(self):
            return b"\0\0" * 48000, None
    async def spawn(*args, **kwargs):
        assert args[args.index("-t") + 1] == "3"
        assert kwargs["stderr"] == asyncio.subprocess.DEVNULL
        return Process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(AudioRejected):
        await WhisperEngine(tmp_path, "base.en", "ffmpeg", max_seconds=2).decode(tmp_path / "audio")


@pytest.mark.parametrize("cancel", [False, True])
async def test_decode_timeout_and_cancel_kill_and_reap_process(tmp_path, monkeypatch, cancel):
    class Process:
        returncode = None
        def __init__(self):
            self.started = asyncio.Event()
            self.killed = asyncio.Event()
            self.reaped = False
        async def communicate(self):
            self.started.set()
            await self.killed.wait()
            self.reaped = True
            self.returncode = -9
            return b"", None
        def kill(self):
            self.killed.set()
    process = Process()
    async def spawn(*args, **kwargs):
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    task = asyncio.create_task(WhisperEngine(tmp_path, "base.en", "ffmpeg", decode_timeout_s=0.02).decode(tmp_path / "audio"))
    await process.started.wait()
    if cancel:
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else EngineFailed):
        await task
    assert process.killed.is_set() and process.reaped
