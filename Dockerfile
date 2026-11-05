FROM node:22-bookworm-slim AS node-runtime
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CLIPDOCK_HOSTED=1 \
    CLIPDOCK_DATA_DIR=/tmp/clipdock \
    CLIPDOCK_WARP=1 \
    PORT=10000

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
# wgcf + wireproxy: user-space Cloudflare WARP proxy for YouTube (see docs/YOUTUBE-HOSTING.md).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl \
    && curl -fsSL -o /usr/local/bin/wgcf https://github.com/ViRb3/wgcf/releases/download/v2.3.1/wgcf_2.3.1_linux_amd64 \
    && echo "4fb7a136aa470ece11d17949c7db07b040ec9c604742dc8680bcf1889f85d0c8  /usr/local/bin/wgcf" | sha256sum -c - \
    && curl -fsSL -o /tmp/wireproxy.tar.gz https://github.com/whyvl/wireproxy/releases/download/v1.1.3/wireproxy_linux_amd64.tar.gz \
    && echo "e88c1d090740373fc606c1bafd81d9a5eadc642cce5667616e20e9d7a444f51c  /tmp/wireproxy.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/wireproxy.tar.gz -C /usr/local/bin wireproxy \
    && chmod 755 /usr/local/bin/wgcf /usr/local/bin/wireproxy \
    && rm /tmp/wireproxy.tar.gz \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 clipdock

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY clipdock ./clipdock
COPY scripts/warp-proxy.sh scripts/start-hosted.sh ./scripts/
RUN python -m pip install --no-cache-dir .
USER clipdock
EXPOSE 10000
CMD ["sh", "/app/scripts/start-hosted.sh"]
