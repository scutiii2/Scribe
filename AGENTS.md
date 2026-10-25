# Scribe

Speech-to-text MCP server for Citadel and Ember. A standalone service on port 8091, registered in Armory as the `scribe` extension. Design: `Python/Citadel/docs/superpowers/specs/2026-10-25-scribe-design.md`. Plan: `Python/Citadel/docs/superpowers/plans/2026-10-25-scribe.md`. Counterpart of Bard (text to speech, `../Bard`).

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands (from this folder, venv `.venv_scribe`)
- Install: `python -m venv .venv_scribe`, then `.venv_scribe/Scripts/python.exe -m pip install -e ".[dev]"`
- Test: `.venv_scribe/Scripts/python.exe -m pytest -q`
- Run: `.venv_scribe/Scripts/python.exe -m src.run` (the model downloads into `.data/models` on first transcription)
- Benchmark: `.venv_scribe/Scripts/python.exe scripts/bench.py <audio file>`

## Rules
- Never read or print `.env`.
- Logic lives in `service.py`, `engine.py`, `store.py`; `app.py` is glue. Tools never call an AI.
- Every blocking call (model, file IO) runs through `asyncio.to_thread`; ffmpeg runs as an asyncio subprocess.
- `INTERNAL_API_TOKEN` guards `/mcp` and `/api/*`; an exposed bind without it must refuse to start.
- Result models end with `message`. Error messages never contain paths.
- The owner key is the username (`_meta.requester` for tools, `X-Requester-Username` for HTTP).
- Defaults are tuned to the Armory call timeout (120 s): `base.en`, 150 s of audio, 110 s transcribe timeout. Measured here: `small.en` x0.5 real time, `base.en` x1.6 (6-core CPU). Raise model and caps together, only after benchmarking.
- Uploaded audio is kept 24 hours on this machine, then deleted.
