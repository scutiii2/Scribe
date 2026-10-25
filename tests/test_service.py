import asyncio

import pytest

from src.errors import AudioRejected, EngineFailed, FileNotFound, IdentityRequired
from src.service import ScribeService
from src.store import AudioStore
from tests.conftest import FakeEngine, audio


def make(settings, engine):
    store = AudioStore(settings.audio_dir, settings.ttl_seconds, settings.quota_bytes)
    return ScribeService(engine, store, settings)


async def test_upload_returns_duration_and_id(settings, engine):
    service = make(settings, engine)
    stored, expires_at = await service.upload("ann", "a.wav", audio(2.0))
    assert stored.duration_s == pytest.approx(2.0) and expires_at > stored.created_at


async def test_upload_needs_identity(settings, engine):
    with pytest.raises(IdentityRequired):
        await make(settings, engine).upload("", "a.wav", audio())


async def test_upload_rejects_unreadable_audio(settings, engine):
    with pytest.raises(AudioRejected):
        await make(settings, engine).upload("ann", "a.wav", audio(bad=True))


async def test_upload_rejects_audio_over_the_duration_cap(settings, engine):
    with pytest.raises(AudioRejected, match="longer"):
        await make(settings, engine).upload("ann", "a.wav", audio(11.0))


async def test_transcribe_then_cache_hit(settings, engine):
    service = make(settings, engine)
    stored, _ = await service.upload("ann", "a.wav", audio())
    first = await service.transcribe("ann", stored.file_id, timestamps=False)
    second = await service.transcribe("ann", stored.file_id, timestamps=True)
    assert first.text == "hello world" and first.cached is False and first.segments is None
    assert second.cached is True and [s.text for s in second.segments] == ["hello", "world"]
    assert engine.transcribe_calls == 1


async def test_unknown_or_foreign_file_is_not_found(settings, engine):
    service = make(settings, engine)
    stored, _ = await service.upload("ann", "a.wav", audio())
    with pytest.raises(FileNotFound):
        await service.transcribe("bob", stored.file_id, timestamps=False)
    with pytest.raises(FileNotFound):
        await service.transcribe("ann", "0" * 32, timestamps=False)


async def test_concurrent_identical_requests_transcribe_once(settings):
    engine = FakeEngine(delay=0.05)
    service = make(settings, engine)
    stored, _ = await service.upload("ann", "a.wav", audio())
    results = await asyncio.gather(*(service.transcribe("ann", stored.file_id, False) for _ in range(3)))
    assert engine.transcribe_calls == 1 and {r.text for r in results} == {"hello world"}


async def test_engine_timeout_is_engine_failed(settings):
    engine = FakeEngine(delay=5)
    service = make(settings, engine)
    stored, _ = await service.upload("ann", "a.wav", audio())
    with pytest.raises(EngineFailed):
        await service.transcribe("ann", stored.file_id, False)  # settings.timeout_s is 2


async def test_engine_failure_is_not_cached(settings):
    engine = FakeEngine(fail=True)
    service = make(settings, engine)
    stored, _ = await service.upload("ann", "a.wav", audio())
    with pytest.raises(EngineFailed):
        await service.transcribe("ann", stored.file_id, False)
    engine.fail = False
    assert (await service.transcribe("ann", stored.file_id, False)).cached is False
