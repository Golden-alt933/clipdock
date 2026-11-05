#!/bin/sh
# Hosted entry point. YouTube blocks most cloud server addresses, so unless
# CLIPDOCK_WARP=0 (or a proxy is already configured), YouTube requests go out
# through a local Cloudflare WARP proxy. Instagram and Pinterest stay direct.
if [ "${CLIPDOCK_WARP:-1}" = "1" ] && [ -z "${CLIPDOCK_YOUTUBE_PROXY:-}" ]; then
    port="${WARP_SOCKS_PORT:-40000}"
    export WARP_SOCKS_PORT="$port"
    export CLIPDOCK_YOUTUBE_PROXY="socks5://127.0.0.1:$port"
    # Keep the proxy running; if it exits, start it again.
    (while true; do sh /app/scripts/warp-proxy.sh; sleep 15; done) &
fi
exec python -m clipdock.web
