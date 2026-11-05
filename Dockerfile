FROM quay.io/invidious/invidious-companion@sha256:55f0bc1002c0edbe4e8163d503c7d797ed919e5861e2c0d0f829ae80138237a4 AS companion-runtime
FROM node:22-bookworm-slim AS node-runtime
FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLIPDOCK_HOSTED=1 \
    CLIPDOCK_DATA_DIR=/tmp/clipdock \
    PORT=10000

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=companion-runtime /app/invidious_companion /opt/companion/invidious_companion
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 clipdock \
    && mkdir -p /var/tmp/youtubei.js \
    && chown clipdock:clipdock /var/tmp/youtubei.js

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY clipdock ./clipdock
RUN python -m pip install --no-cache-dir .
USER clipdock
EXPOSE 10000
CMD ["python", "-m", "clipdock.web"]
