"""Temporary Render probe: public video only; never prints media URLs or cookies."""
import json
import re
import threading
import time

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget


def safe(message):
    return re.sub(r"https?://\S+", "<URL>", str(message))[:600]


def report(**data):
    print("[CD-YT-PROBE] " + json.dumps(data, ensure_ascii=True), flush=True)


class Log:
    def __init__(self):
        self.warnings = []

    def debug(self, message):
        pass

    def warning(self, message):
        self.warnings.append(safe(message))

    def error(self, message):
        pass


def probe(only=None):
    cases = [
        ("default", {}),
        ("chrome", {"impersonate": ImpersonateTarget(client="chrome")}),
        ("web_safari", {"impersonate": ImpersonateTarget(client="safari"),
                        "extractor_args": {"youtube": {"player_client": ["web_safari"]}}}),
        ("web_embedded", {"impersonate": ImpersonateTarget(client="chrome"),
                          "extractor_args": {"youtube": {"player_client": ["web_embedded"]}}}),
        ("tv", {"extractor_args": {"youtube": {"player_client": ["tv"]}}}),
        ("mweb", {"impersonate": ImpersonateTarget(client="chrome"),
                  "extractor_args": {"youtube": {"player_client": ["mweb"]}}}),
    ]
    report(stage="start", cases=len(cases))
    for name, extra in cases:
        if only and name not in only:
            continue
        logger = Log()
        options = {"quiet": True, "no_warnings": True, "logger": logger, "noplaylist": True,
                   "socket_timeout": 12, "retries": 0, "extractor_retries": 0,
                   "cachedir": False, "js_runtimes": {"node": {}}, **extra}
        started = time.monotonic()
        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info("https://www.youtube.com/shorts/q6ZqeyEh64A", download=False)
            report(client=name, result="PASS", formats=len(info.get("formats", [])),
                   title=info.get("title"), seconds=round(time.monotonic() - started, 1),
                   warnings=logger.warnings[-3:])
        except Exception as exc:
            report(client=name, result="FAIL", error=safe(exc),
                   seconds=round(time.monotonic() - started, 1), warnings=logger.warnings[-3:])
        time.sleep(3)
    report(stage="complete")


if __name__ == "__main__":
    threading.Thread(target=probe, daemon=True).start()
    from clipdock.web import main
    main()
