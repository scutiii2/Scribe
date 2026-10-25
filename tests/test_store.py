import pytest

from src.errors import QuotaExceeded
from src.store import AudioStore


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(tmp_path, ttl=100, quota=1000):
    clock = Clock()
    return AudioStore(tmp_path, ttl, quota, clock), clock


def test_id_is_stable_and_owner_specific():
    assert AudioStore.file_id("ann", b"x") == AudioStore.file_id("ann", b"x")
    assert AudioStore.file_id("ann", b"x") != AudioStore.file_id("bob", b"x")
    assert len(AudioStore.file_id("ann", b"x")) == 32


def test_put_then_get(tmp_path):
    store, _ = make(tmp_path)
    fid = AudioStore.file_id("ann", b"abc")
    stored = store.put("ann", fid, b"abc", "a.mp3", 1.5)
    got = store.get("ann", fid)
    assert got.path.read_bytes() == b"abc" and got.duration_s == 1.5 and got.filename == "a.mp3"
    assert store.expires_at(stored) == 1100.0


def test_other_owner_and_bad_id_are_not_found(tmp_path):
    store, _ = make(tmp_path)
    fid = AudioStore.file_id("ann", b"abc")
    store.put("ann", fid, b"abc", "a.mp3", 1.0)
    assert store.get("bob", fid) is None
    assert store.get("ann", "../../etc") is None
    assert store.get("ann", "g" * 32) is None


def test_expired_file_is_deleted_on_get(tmp_path):
    store, clock = make(tmp_path)
    fid = AudioStore.file_id("ann", b"abc")
    stored = store.put("ann", fid, b"abc", "a.mp3", 1.0)
    clock.now += 101
    assert store.get("ann", fid) is None
    assert not stored.path.exists()


def test_quota_blocks_a_write(tmp_path):
    store, _ = make(tmp_path, quota=10)
    store.put("ann", AudioStore.file_id("ann", b"1"), b"123456", "a", 1.0)
    with pytest.raises(QuotaExceeded):
        store.put("ann", AudioStore.file_id("ann", b"2"), b"123456", "b", 1.0)


def test_put_removes_expired_files_first(tmp_path):
    store, clock = make(tmp_path, quota=10)
    store.put("ann", AudioStore.file_id("ann", b"1"), b"123456", "a", 1.0)
    clock.now += 101
    store.put("ann", AudioStore.file_id("ann", b"2"), b"123456", "b", 1.0)


def test_transcript_cache_is_keyed_by_model(tmp_path):
    store, _ = make(tmp_path)
    fid = AudioStore.file_id("ann", b"abc")
    store.put("ann", fid, b"abc", "a.mp3", 1.0)
    store.put_transcript("ann", fid, "base.en", {"text": "hi", "segments": []})
    assert store.get_transcript("ann", fid, "base.en")["text"] == "hi"
    assert store.get_transcript("ann", fid, "small.en") is None


def test_sweep_removes_expired_and_transcripts(tmp_path):
    store, clock = make(tmp_path)
    fid = AudioStore.file_id("ann", b"abc")
    stored = store.put("ann", fid, b"abc", "a.mp3", 1.0)
    store.put_transcript("ann", fid, "base.en", {"text": "hi", "segments": []})
    clock.now += 101
    assert store.sweep() == 1
    assert list(stored.path.parent.iterdir()) == []
