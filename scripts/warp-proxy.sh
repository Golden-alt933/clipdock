#!/bin/sh
# Start a local SOCKS5 proxy that sends traffic through Cloudflare WARP (free).
# Runs entirely in user space: no root, no kernel WireGuard, no NET_ADMIN.
# Usage: warp-proxy.sh   (listens on 127.0.0.1:${WARP_SOCKS_PORT:-40000})
set -eu

dir="${WARP_DIR:-/tmp/clipdock-warp}"
port="${WARP_SOCKS_PORT:-40000}"
mkdir -p "$dir"
cd "$dir"

if [ ! -s wgcf-profile.conf ]; then
    # Registers an anonymous free WARP device; no Cloudflare account is needed.
    tries=0
    until wgcf register --accept-tos >/dev/null 2>&1; do
        tries=$((tries + 1))
        [ "$tries" -ge 5 ] && { echo "warp-proxy: WARP registration failed" >&2; exit 1; }
        sleep $((tries * 3))
    done
    wgcf generate >/dev/null
fi

# wireproxy reads a normal WireGuard profile plus a [Socks5] section.
cp wgcf-profile.conf wireproxy.conf
printf '\n[Socks5]\nBindAddress = 127.0.0.1:%s\n' "$port" >> wireproxy.conf

exec wireproxy -c wireproxy.conf
