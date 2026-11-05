"""Try several YouTube routes/clients from the server against one fixed public video.

Used by /api/route/probe to find which configuration a host can use. No user input reaches it.
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def _trace(proxy):
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL({"proxy": proxy, "quiet": True, "no_warnings": True, "socket_timeout": 10}) as ydl:
            text = ydl.urlopen("https://www.cloudflare.com/cdn-cgi/trace").read().decode()
        fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        return {k: fields.get(k) for k in ("ip", "colo", "warp")}
    except Exception as exc:
        return {"error": type(exc).__name__}


def _try(name, options):
    import yt_dlp
    base = {"quiet": True, "no_warnings": True, "socket_timeout": 20, "noplaylist": True,
            "cachedir": False, "js_runtimes": {"node": {}}}
    base.update(options)
    started = time.monotonic()
    try:
        with yt_dlp.YoutubeDL(base) as ydl:
            info = ydl.extract_info(VIDEO, download=False)
        formats = info.get("formats") or []
        heights = sorted({f["height"] for f in formats if f.get("height")})
        outcome = f"ok: {len(formats)} formats, heights {heights[-3:]}"
    except Exception as exc:
        outcome = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).replace(VIDEO, "")[:160]
    return name, f"{outcome} ({time.monotonic() - started:.1f}s)"


def run():
    proxy = os.environ.get("CLIPDOCK_YOUTUBE_PROXY", "").strip()
    remote = proxy.replace("socks5://", "socks5h://", 1) if proxy.startswith("socks5://") else None
    variants = [("direct", {})]
    if proxy:
        variants.append(("warp", {"proxy": proxy}))
        if remote:
            variants.append(("warp_remote_dns", {"proxy": remote}))
        for client in ("tv", "tv_simply", "android_vr", "ios", "mweb", "web_safari", "web_embedded", "visionos"):
            variants.append((f"warp_{client}", {"proxy": proxy,
                                                "extractor_args": {"youtube": {"player_client": [client]}}}))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(pool.map(lambda v: _try(*v), variants))
    return {"egress": {"direct": _trace(None), "warp": _trace(proxy) if proxy else None,
                       "warp_remote_dns": _trace(remote) if remote else None},
            "youtube": results}
