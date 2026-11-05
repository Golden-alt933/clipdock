FROM node:22-bookworm-slim AS node-runtime
FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLIPDOCK_HOSTED=1 \
    CLIPDOCK_DATA_DIR=/tmp/clipdock \
    PORT=10000

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates libatomic1 chromium chromium-sandbox \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 clipdock

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY clipdock ./clipdock
RUN python -m pip install --no-cache-dir . websocket-client==1.9.0
USER clipdock
EXPOSE 10000
CMD ["python", "-m", "clipdock.web"]
