"""Try several YouTube routes against one fixed public video from the server.

Used by /api/route/probe to find which configuration a host can use. No user input reaches it,
and it never returns cookie contents.
"""
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def _trace(proxy):
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL({"proxy": proxy, "quiet": True, "no_warnings": True, "socket_timeout": 8}) as ydl:
            text = ydl.urlopen("https://www.cloudflare.com/cdn-cgi/trace").read().decode()
        fields = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
        return {k: fields.get(k) for k in ("colo", "warp")}
    except Exception as exc:
        return {"error": type(exc).__name__}


def _try(name, options):
    import yt_dlp
    base = {"quiet": True, "no_warnings": True, "socket_timeout": 10, "retries": 0, "extractor_retries": 0,
            "noplaylist": True, "cachedir": False, "js_runtimes": {"node": {}}}
    base.update(options)
    started = time.monotonic()
    try:
        with yt_dlp.YoutubeDL(base) as ydl:
            info = ydl.extract_info(VIDEO, download=False)
        outcome = f"ok: {len(info.get('formats') or [])} formats"
    except Exception as exc:
        outcome = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).replace(VIDEO, "")[:140]
    return name, f"{outcome} ({time.monotonic() - started:.1f}s)"


def run():
    from .worker import youtube_cookies, youtube_proxy
    proxy = youtube_proxy(VIDEO)
    cookies = youtube_cookies(VIDEO)
    variants = [("direct", {})]
    if proxy:
        variants += [("warp", {"proxy": proxy}),
                     ("warp_tv", {"proxy": proxy, "extractor_args": {"youtube": {"player_client": ["tv"]}}})]
    if cookies:
        variants += [("cookies", {"cookiefile": cookies}),
                     ("cookies_tv", {"cookiefile": cookies, "extractor_args": {"youtube": {"player_client": ["tv"]}}}),
                     ("cookies_web_safari", {"cookiefile": cookies,
                                             "extractor_args": {"youtube": {"player_client": ["web_safari"]}}})]
        if proxy:
            variants.append(("cookies_warp", {"cookiefile": cookies, "proxy": proxy}))
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(pool.map(lambda v: _try(*v), variants))
    return {"cookies_configured": bool(cookies), "warp": _trace(proxy) if proxy else None, "youtube": results}
