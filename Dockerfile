# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 SCRIBE_DATA_DIR=/data SCRIBE_HOST=0.0.0.0
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

EXPOSE 8091
# The model downloads into the /data volume on first start; later starts reuse it (and still boot offline).
CMD ["sh", "-c", "python -c \"from faster_whisper import WhisperModel; WhisperModel('${SCRIBE_MODEL:-base.en}', device='cpu', compute_type='int8', download_root='/data/models')\"; exec python -m src.run"]
