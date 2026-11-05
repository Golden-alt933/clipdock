"""Check matched anonymous visitor data and PO tokens entirely inside Render."""
import json
import re
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget


def report(**data):
    print("[CD-GUEST-PAIR] " + json.dumps(data, ensure_ascii=True), flush=True)


def safe(value):
    return re.sub(r"[A-Za-z0-9_-]{40,}", "<DATA>", re.sub(r"https?://\S+", "<URL>", str(value)))[:650]


class Log:
    def __init__(self):
        self.tokens = []
        self.warnings = []

    def debug(self, message):
        for context in ("player", "gvs"):
            if f"Retrieved a {context} PO Token" in message:
                self.tokens.append(context)

    def warning(self, message):
        self.warnings.append(safe(message))

    def error(self, message):
        pass


def probe():
    provider = subprocess.Popen(["node", "/opt/bgutil/build/main.js", "--host", "127.0.0.1"],
                                cwd="/opt/bgutil", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for attempt in range(60):
            if provider.poll() is not None:
                report(stage="provider", result="FAIL", exit=provider.returncode)
                return
            try:
                with urllib.request.urlopen("http://127.0.0.1:4416/ping", timeout=2):
                    break
            except OSError:
                time.sleep(1)
        else:
            report(stage="provider", result="TIMEOUT")
            return
        request = urllib.request.Request("http://127.0.0.1:4416/get_pot", data=b"{}",
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            session = json.load(response)
        visitor = session["contentBinding"]
        token = session["poToken"]
        report(stage="matched_session_created", visitor_length=len(visitor), token_present=bool(token))
        cases = [("mweb_matched_auto", "mweb", False),
                 ("mweb_matched_gvs", "mweb", True),
                 ("safari_matched_auto", "web_safari", False)]
        for name, client, explicit_gvs in cases:
            logger = Log()
            args = {"player_client": [client], "player_skip": ["webpage", "configs"],
                    "visitor_data": [visitor], "fetch_pot": ["always"]}
            if explicit_gvs:
                args["po_token"] = [client + ".gvs+" + token]
            folder = Path("/tmp/clipdock-matched-session") / name
            folder.mkdir(parents=True, exist_ok=True)
            options = {"quiet": True, "verbose": True, "no_warnings": True, "logger": logger,
                "noplaylist": True, "socket_timeout": 25, "retries": 0, "extractor_retries": 0,
                "cachedir": False, "js_runtimes": {"node": {}},
                "impersonate": ImpersonateTarget(client="safari" if client == "web_safari" else "chrome"),
                "extractor_args": {"youtube": args}, "outtmpl": str(folder / "%(id)s.%(ext)s"),
                "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b", "format_sort": ["res:720"],
                "merge_output_format": "mp4", "max_filesize": 100 * 1024 * 1024,
                "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]}
            stage = "inspect"
            try:
                with yt_dlp.YoutubeDL(options) as downloader:
                    info = downloader.extract_info("https://www.youtube.com/shorts/q6ZqeyEh64A", download=False)
                    report(case=name, stage=stage, result="PASS", formats=len(info.get("formats", [])), tokens=logger.tokens)
                    if not 0 < (info.get("duration") or 0) <= 600:
                        raise RuntimeError("Invalid test duration")
                    stage = "download"
                    downloader.process_ie_result(info, download=True)
                files = list(folder.glob("*.mp4"))
                if not files:
                    raise RuntimeError("No completed MP4")
                result = max(files, key=lambda file: file.stat().st_mtime)
                check = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height",
                    "-show_entries", "format=duration,size", "-of", "json", str(result)],
                    capture_output=True, text=True, timeout=20)
                report(case=name, stage="download", result="PASS" if check.returncode == 0 else "FAIL",
                       bytes=result.stat().st_size, media=json.loads(check.stdout) if check.returncode == 0 else None)
                return
            except Exception as exc:
                report(case=name, stage=stage, result="FAIL", error=safe(exc), tokens=logger.tokens, warnings=logger.warnings[-3:])
            time.sleep(3)
        report(stage="complete")
    except Exception as exc:
        report(stage="session", result="FAIL", error=safe(exc))
    finally:
        provider.terminate()
        try:
            provider.wait(timeout=10)
        except subprocess.TimeoutExpired:
            provider.kill()


if __name__ == "__main__":
    threading.Thread(target=probe, daemon=True).start()
    from clipdock.web import main
    main()
