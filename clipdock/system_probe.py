"""Temporary production-image audit; public media only, no credentials logged."""
import importlib.metadata
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

from clipdock import __version__


def safe(value):
    return re.sub(r"[A-Za-z0-9_-]{50,}", "<DATA>",
                  re.sub(r"https?://\S+", "<URL>", str(value)))[:750]


def report(**values):
    print("[CD-SYSTEM-PROBE] " + json.dumps(values, ensure_ascii=True), flush=True)


def execute(arguments, **kwargs):
    return subprocess.run(arguments, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=150, **kwargs)


def probe():
    report(stage="start", python=sys.version.split()[0], app=__version__,
           packages={name: importlib.metadata.version(name)
                     for name in ("yt-dlp", "yt-dlp-ejs", "curl-cffi")})
    for binary, argument in (("node", "--version"), ("ffmpeg", "-version"), ("ffprobe", "-version")):
        try:
            result = execute([binary, argument])
            output = result.stdout or result.stderr
            report(binary=binary, exit=result.returncode, output=safe(output.splitlines()[0] if output else ""))
        except Exception as exc:
            report(binary=binary, result="FAIL", error=safe(exc))

    urls = [("supplied_short", "https://www.youtube.com/shorts/q6ZqeyEh64A"),
            ("upstream_test_video", "https://www.youtube.com/watch?v=BaW_jenozKc")]
    for name, url in urls:
        try:
            result = execute([sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-cache-dir",
                              "--no-playlist", "--socket-timeout", "12", "--retries", "0",
                              "--extractor-retries", "0", "--js-runtimes", "node", "--verbose",
                              "--simulate", "--dump-single-json", url])
            signals = [safe(line) for line in result.stderr.splitlines()
                       if any(marker in line for marker in ("JS runtimes:", "Optional libraries:",
                                                            "ERROR:", "WARNING:", "playability status:"))]
            if result.returncode:
                report(test=name, mode="standalone_yt_dlp", result="FAIL", exit=result.returncode,
                       signals=signals[-7:])
                continue
            info = json.loads(result.stdout)
            report(test=name, mode="standalone_yt_dlp", result="PASS", formats=len(info.get("formats", [])),
                   duration=info.get("duration"), signals=signals[-7:])
            folder = Path("/tmp/clipdock-system-check") / name
            worker = execute([sys.executable, "-m", "clipdock.worker"], input=json.dumps({
                "mode": "download", "url": url, "folder": str(folder), "format": "mp4", "quality": "720",
                "audio_bitrate": "320", "max_bytes": 100 * 1024 * 1024, "max_duration": 600}))
            events = [json.loads(line) for line in worker.stdout.splitlines() if line.startswith("{")]
            final = next((event for event in reversed(events) if event.get("event") in {"complete", "error"}), {})
            report(test=name, mode="clipdock_worker", result="PASS" if final.get("event") == "complete" else "FAIL",
                   size=final.get("size"), error=safe(final.get("message", "")))
        except Exception as exc:
            report(test=name, result="FAIL", error=safe(exc))
    report(stage="complete")


if __name__ == "__main__":
    threading.Thread(target=probe, daemon=True).start()
    from clipdock.web import main
    main()
