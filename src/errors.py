"""Stable, coded failures. Messages are safe to show a user: no paths, no secrets."""


class ScribeError(Exception):
    code = "scribe_error"


class AudioRejected(ScribeError):
    code = "audio_rejected"


class FileNotFound(ScribeError):
    code = "file_not_found"


class QuotaExceeded(ScribeError):
    code = "quota_exceeded"


class EngineFailed(ScribeError):
    code = "engine_failed"


class IdentityRequired(ScribeError):
    code = "identity_required"
