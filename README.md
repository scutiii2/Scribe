# Scribe

Speech to text for Citadel and Ember. A user attaches an English audio file (mp3, wav, m4a, ogg, flac, webm) in chat; the agent calls `scribe__tool_scribe_transcribe` and answers with the transcript. Runs locally with faster-whisper on CPU.

- Upload: `POST /api/files` (raw bytes, `X-Requester-Username`, `X-Filename`), reached only through ember_api.
- Tool: `tool_scribe_transcribe(file_id, timestamps=false)` over MCP at `/mcp`.
- Limits: 25 MB, 150 s of audio, 200 MB per user. Uploads and transcripts are deleted after 24 hours.
- Run: `.venv_scribe/Scripts/python.exe -m src.run`. Docker: `docker compose up -d --build` (the Citadel network must exist).
- Privacy: user audio sits on this machine for 24 hours.
