"""python scripts/bench.py <audio file>: seconds of audio per second of CPU time for small.en int8."""

import subprocess
import sys
import time

import numpy as np
from faster_whisper import WhisperModel

path = sys.argv[1]
pcm = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ar", "16000", "-ac", "1", "pipe:1"],
    capture_output=True, check=True,
).stdout
audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
seconds = len(audio) / 16000
t0 = time.perf_counter()
model = WhisperModel("small.en", device="cpu", compute_type="int8", download_root=".data/models")
t1 = time.perf_counter()
segments, _ = model.transcribe(audio, language="en", beam_size=1)
text = " ".join(s.text.strip() for s in segments)
t2 = time.perf_counter()
print(f"audio {seconds:.1f}s | model load {t1 - t0:.1f}s | transcribe {t2 - t1:.1f}s | speed x{seconds / (t2 - t1):.1f}")
print(text[:300])
