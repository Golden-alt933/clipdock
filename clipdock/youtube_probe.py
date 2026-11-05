"""Temporary Render probe: public video only; never prints media URLs or cookies."""
import json
import re
import subprocess
import threading
import time
import urllib.request

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget


def safe(message):
    return re.sub(r"[A-Za-z0-9_-]{50,}", "<DATA>", re.sub(r"https?://\S+", "<URL>", str(message)))[:600]


def report(**data):
    print("[CD-YT-PROBE] " + json.dumps(data, ensure_ascii=True), flush=True)


class Log:
    def __init__(self):
        self.warnings = []
        self.tokens = []

    def debug(self, message):
        for context in ("player", "gvs"):
            if f"Retrieved a {context} PO Token" in message:
                self.tokens.append(context)

    def warning(self, message):
        self.warnings.append(safe(message))

    def error(self, message):
        pass


def probe(only=None):
    from yt_dlp.plugins import load_all_plugins
    load_all_plugins()
    from yt_dlp_plugins.extractor.getpot_bgutil import BgUtilPTPBase
    BgUtilPTPBase._GETPOT_TIMEOUT = 60
    for attempt in range(240):
        try:
            with urllib.request.urlopen("http://127.0.0.1:4416/ping", timeout=2) as response:
                report(provider_ready=True, version=json.load(response)["version"])
            break
        except Exception:
            if provider.poll() is not None:
                report(provider_ready=False, exit=provider.returncode, error=safe(provider.stderr.read().decode(errors="replace")))
                return
            time.sleep(0.5)
    else:
        report(provider_ready=False)
        return
    cases = [
        ("visionos_googleapis", {"extractor_args": {"youtube": {
            "player_client": ["visionos"], "innertube_host": ["youtubei.googleapis.com"],
            "player_skip": ["webpage", "configs"]}}}),
        ("mweb_googleapis_pot", {"impersonate": ImpersonateTarget(client="chrome"), "extractor_args": {"youtube": {
            "player_client": ["mweb"], "innertube_host": ["youtubei.googleapis.com"],
            "fetch_pot": ["always"], "player_skip": ["webpage", "configs"]}}}),
        ("embedded_nocookie", {"impersonate": ImpersonateTarget(client="chrome"), "extractor_args": {"youtube": {
            "player_client": ["web_embedded"], "innertube_host": ["www.youtube-nocookie.com"],
            "player_skip": ["webpage", "configs"]}}}),
    ]
    report(stage="start", cases=len(cases))
    for name, extra in cases:
        if only and name not in only:
            continue
        logger = Log()
        options = {"quiet": True, "verbose": True, "no_warnings": True, "logger": logger, "noplaylist": True,
                   "socket_timeout": 12, "retries": 0, "extractor_retries": 0,
                   "cachedir": False, "js_runtimes": {"node": {}}, **extra}
        started = time.monotonic()
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info("https://www.youtube.com/shorts/q6ZqeyEh64A", download=False)
            report(client=name, result="PASS", formats=len(info.get("formats", [])),
                   title=info.get("title"), seconds=round(time.monotonic() - started, 1),
                   tokens=logger.tokens, warnings=logger.warnings[-4:])
        except Exception as exc:
            report(client=name, result="FAIL", error=safe(exc),
                   seconds=round(time.monotonic() - started, 1), tokens=logger.tokens, warnings=logger.warnings[-4:])
        time.sleep(3)
    report(stage="complete")


if __name__ == "__main__":
    provider = subprocess.Popen(["node", "/opt/bgutil/build/main.js", "--host", "127.0.0.1"],
                                cwd="/opt/bgutil", stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    threading.Thread(target=probe, daemon=True).start()
    from clipdock.web import main
    main()
