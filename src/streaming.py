"""Bounded LocalAgreement state and the live PCM transport."""
from __future__ import annotations

import asyncio
import json
import time

from starlette.websockets import WebSocket, WebSocketDisconnect

from src.engine import PCM_BYTES_PER_SECOND, Segment, Transcript
from src.errors import AudioRejected, ScribeError


class LocalAgreement:
    def __init__(self, max_seconds: float = 150, window_seconds: float = 30):
        self.pcm = b""
        self.total_bytes = 0
        self._max_bytes = int(max_seconds * PCM_BYTES_PER_SECOND)
        self._window_bytes = int(window_seconds * PCM_BYTES_PER_SECOND)
        self._previous: list[Segment] = []
        self._committed: list[str] = []

    def append(self, data: bytes) -> None:
        if len(data) % 2:
            raise AudioRejected("PCM frames must contain complete 16-bit samples.")
        if self.total_bytes + len(data) > self._max_bytes:
            raise AudioRejected("That audio is too long.")
        if len(self.pcm) + len(data) > self._window_bytes:
            raise AudioRejected("Speech could not stabilize. Stop and try a shorter dictation.")
        self.total_bytes += len(data)
        self.pcm += data

    def update(self, result: Transcript) -> str:
        # Only genuine word timestamps (or single-word segments) permit trimming.
        words = result.words or (result.segments if all(len(s.text.split()) == 1 for s in result.segments) else [])
        count = 0
        for old, new in zip(self._previous, words):
            if old.text.casefold().strip() != new.text.casefold().strip():
                break
            count += 1
        text = " ".join([*self._committed, result.text]).strip()
        if count:
            end = min(len(self.pcm), max(0, int(words[count - 1].end_s * PCM_BYTES_PER_SECOND)))
            end -= end % 2
            if end:
                self._committed.extend(w.text for w in words[:count])
                self.pcm = self.pcm[end:]
                shift = end / PCM_BYTES_PER_SECOND
                self._previous = [Segment(w.start_s - shift, w.end_s - shift, w.text) for w in words[count:]]
                return text
        self._previous = words
        return text

    def finish(self, result: Transcript) -> str:
        return " ".join([*self._committed, result.text]).strip()


async def serve_stream(ws: WebSocket, service, settings) -> None:
    owner = ws.headers.get("x-requester-username", "").strip()
    if not owner:
        await ws.close(code=1008)
        return
    if not service.acquire_live():
        await ws.accept()
        await ws.close(code=1013)
        return
    key = object()
    try:
        await service.reserve(key, owner, 0)
        await ws.accept()
        state = LocalAgreement(min(150, settings.max_seconds), settings.stream_window_s)
        last_pass = 0
        deadline = time.monotonic() + min(150, settings.max_seconds) + settings.timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AudioRejected("Dictation time limit reached.")
            message = await asyncio.wait_for(ws.receive(), min(settings.stream_idle_s, remaining))
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is not None:
                if len(data) > settings.stream_max_frame_bytes:
                    await ws.send_json({"type": "error", "message": "Audio frame is too large."})
                    await ws.close(code=1009)
                    return
                if state.total_bytes + len(data) > settings.max_bytes:
                    raise AudioRejected("That audio is too large.")
                await service.reserve(key, owner, state.total_bytes + len(data))
                state.append(data)
                if state.total_bytes - last_pass >= PCM_BYTES_PER_SECOND:
                    result = await asyncio.wait_for(service.infer(state.pcm), max(0.001, deadline - time.monotonic()))
                    last_pass = state.total_bytes
                    await ws.send_json({"type": "partial", "text": state.update(result)})
            else:
                text = message.get("text", "")
                if len(text) > 256:
                    raise AudioRejected("Invalid stream command.")
                try:
                    command = json.loads(text)
                except ValueError:
                    raise AudioRejected("Invalid stream command.") from None
                if not isinstance(command, dict) or command.get("type") != "stop":
                    raise AudioRejected("Invalid stream command.")
                result = await asyncio.wait_for(service.infer(state.pcm), max(0.001, deadline - time.monotonic())) if state.pcm else Transcript("", [], "en")
                await ws.send_json({"type": "final", "text": state.finish(result)})
                await ws.close()
                return
    except WebSocketDisconnect:
        pass
    except Exception as error:
        # Neither engine exception text nor temporary file paths cross this boundary.
        message = "Dictation timed out." if isinstance(error, TimeoutError) else "Dictation failed. Try again."
        if isinstance(error, ScribeError):
            message = "Audio or quota limit reached. Try a shorter dictation."
        if ws.application_state.name == "CONNECTED":
            await ws.send_json({"type": "error", "message": message})
            await ws.close(code=1008)
        else:
            await ws.close(code=1008)
    finally:
        service.unreserve(key)
        service.release_live()
