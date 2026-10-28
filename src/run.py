"""python -m src.run"""

from __future__ import annotations

import sys

import uvicorn

from src.app import build_app
from src.config import load_settings


def main() -> None:
    settings = load_settings()
    if settings.exposed_without_token:
        sys.exit("Scribe refuses to start: SCRIBE_HOST is not a loopback address and INTERNAL_API_TOKEN is empty.")
    uvicorn.run(
        build_app(settings), host=settings.host, port=settings.port, log_level="info",
        ws="websockets", ws_max_size=settings.stream_max_frame_bytes, ws_max_queue=4,
    )


if __name__ == "__main__":
    main()
