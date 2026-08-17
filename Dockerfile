FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libgl1 libglib2.0-0 tini curl \
    && rm -rf /var/lib/apt/lists/*

FROM base AS runtime

COPY pyproject.toml ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install .

COPY src ./src
COPY scripts ./scripts
COPY config ./config
COPY models ./models

RUN mkdir -p /app/data/snapshots /app/data/clips /app/data/baseline /app/data/reports

EXPOSE 8080

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
