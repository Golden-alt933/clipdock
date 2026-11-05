"""Temporary production-image audit; public media only, no credentials logged."""
import importlib.metadata
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
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


def probe_companion():
    key = secrets.token_hex(8)
    environment = {
        "PATH": os.environ.get("PATH", ""), "HOST": "127.0.0.1", "PORT": "8282",
        "SERVER_SECRET_KEY": key, "SERVER_BASE_PATH": "/companion", "CACHE_ENABLED": "false",
        "CACHE_DIRECTORY": "/var/tmp", "YOUTUBE_SESSION_OAUTH_ENABLED": "false",
        "JOBS_YOUTUBE_SESSION_PO_TOKEN_ENABLED": "true", "NETWORKING_FETCH_TIMEOUT_MS": "20000",
        "NETWORKING_FETCH_RETRY_ENABLED": "false", "CAPTIONS_ENABLED": "false",
    }
    backend = subprocess.Popen(["/opt/companion/invidious_companion"], cwd="/opt/companion", env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace")

    def read_log():
        markers = {
            "Successfully generated PO token": "session_ready",
            "Successfully validated PO token": "session_media_validated",
            "Failed to validate PO token": "session_validation_failed",
            "Sign in to confirm": "youtube_login_required",
            "error while loading shared libraries": "runtime_library_missing",
            "GLIBC_": "runtime_library_mismatch",
        }
        seen = set()
        details = 0
        for line in backend.stdout:
            if "Using Invidious companion version" in line:
                report(engine="companion", version=safe(line.strip()))
            if details < 6 and any(marker in line for marker in ("err:", "Error:", "Got status", "No valid format")):
                message = safe(line.strip().replace(key, "<PRIVATE>"))
                message = re.sub(r"(?i)((?:cookie|authorization|po.?token|visitor.?data|secret.?key)\s*[:=]\s*)[^,}]+", r"\1<PRIVATE>", message)
                report(engine="companion", diagnostic=message)
                details += 1
            for marker, stage in markers.items():
                if marker in line and stage not in seen:
                    seen.add(stage)
                    report(engine="companion", stage=stage)

    threading.Thread(target=read_log, daemon=True).start()
    deadline = time.monotonic() + 180
    try:
        while time.monotonic() < deadline:
            if backend.poll() is not None:
                report(engine="companion", result="FAIL", stage="startup", exit=backend.returncode)
                return
            try:
                request = urllib.request.Request("http://127.0.0.1:8282/companion/youtubei/v1/player",
                    data=json.dumps({"videoId": "q6ZqeyEh64A"}).encode(),
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    info = json.load(response)
                status = info.get("playabilityStatus", {})
                reason = str(status.get("reason", ""))
                if "Companion is starting" in reason:
                    time.sleep(5)
                    continue
                stream = info.get("streamingData", {})
                formats = stream.get("formats", []) + stream.get("adaptiveFormats", [])
                report(engine="companion", result="PASS" if status.get("status") == "OK" and formats else "FAIL",
                       stage="extract", status=status.get("status"), reason=safe(reason), formats=len(formats))
                if status.get("status") != "OK" or not formats:
                    return
                progressive = [f for f in stream.get("formats", [])
                               if f.get("url") and f.get("mimeType", "").startswith("video/mp4")]
                if not progressive:
                    report(engine="companion", stage="transfer", result="NEEDS_ADAPTIVE_MERGE")
                    return
                media = urllib.parse.urlsplit(progressive[0]["url"])
                if media.scheme != "https" or not (media.hostname or "").endswith(".googlevideo.com"):
                    report(engine="companion", stage="transfer", result="FAIL", reason="Unexpected media host")
                    return
                query = urllib.parse.parse_qsl(media.query, keep_blank_values=True)
                query.append(("host", media.hostname))
                relay = "http://127.0.0.1:8282/companion/videoplayback?" + urllib.parse.urlencode(query)
                total = 0
                destination = Path("/tmp/companion-public-test.mp4")
                with urllib.request.urlopen(relay, timeout=30) as response, destination.open("wb") as output:
                    while chunk := response.read(65536):
                        total += len(chunk)
                        if total > 100 * 1024 * 1024:
                            raise RuntimeError("Transfer exceeded test limit")
                        output.write(chunk)
                check = execute(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height",
                                 "-show_entries", "format=duration,size", "-of", "json", str(destination)])
                report(engine="companion", stage="transfer", result="PASS" if check.returncode == 0 else "FAIL",
                       bytes=total, media=json.loads(check.stdout) if check.returncode == 0 else None)
                return
            except urllib.error.HTTPError as exc:
                report(engine="companion", stage="request", status=exc.code, result="FAIL")
                return
            except urllib.error.URLError:
                time.sleep(5)
        report(engine="companion", stage="session_initialization", result="TIMEOUT")
    except Exception as exc:
        report(engine="companion", result="FAIL", error=safe(exc))
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            backend.kill()


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
            ("public_control_video", "https://www.youtube.com/watch?v=jNQXAC9IVRw")]
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
    probe_companion()
    report(stage="complete")


if __name__ == "__main__":
    threading.Thread(target=probe, daemon=True).start()
    from clipdock.web import main
    main()
