"""One isolated yt-dlp operation. JSON on stdin; JSON events on stdout."""
import json
import re
import shutil
import sys
from pathlib import Path

import yt_dlp


def emit(event, **values):
    print(json.dumps({"event": event, **values}, ensure_ascii=True), flush=True)


class Logger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def first_video(info):
    if info and info.get("_type") in ("playlist", "multi_video"):
        info = next((x for x in info.get("entries", []) if x), None)
    if not info or not info.get("formats"):
        raise ValueError("No downloadable video found. Paste a single video, Reel, or video Pin.")
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
        raise ValueError("This is a live or upcoming stream. Try again after it has finished.")
    return info


def summary(info):
    heights = sorted({int(f["height"]) for f in info.get("formats", []) if f.get("height")})
    return {"title": info.get("title") or "Untitled video", "creator": info.get("uploader") or info.get("channel") or "",
            "duration": info.get("duration"), "thumbnail": info.get("thumbnail"), "heights": heights,
            "id": info.get("id"), "source": info.get("extractor_key", "")}


def run(data):
    options = {"quiet": True, "no_warnings": True, "logger": Logger(), "noplaylist": True,
               "playlist_items": "1", "socket_timeout": 25, "retries": 2, "fragment_retries": 2,
               "windowsfilenames": True, "cachedir": False, "js_runtimes": {"node": {}}}
    if data["mode"] == "inspect":
        with yt_dlp.YoutubeDL(options) as downloader:
            info = first_video(downloader.extract_info(data["url"], download=False))
            emit("metadata", **summary(info))
        return
    folder = Path(data["folder"]).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    last_emit = [0.0]
    completed = []

    def progress(d):
        import time
        if d["status"] == "downloading":
            now = time.monotonic()
            if now - last_emit[0] < 0.3:
                return
            last_emit[0] = now
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            emit("progress", downloaded=done, total=total, speed=d.get("speed"), eta=d.get("eta"),
                 percent=round(min(99.0, done / total * 100), 1) if total else None)
        elif d["status"] == "finished":
            emit("processing")

    options.update({"outtmpl": str(folder / "%(title).100s [%(id)s].%(ext)s"),
                    "progress_hooks": [progress], "overwrites": False,
                    "post_hooks": [lambda filename: completed.append(Path(filename))],
                    "postprocessor_hooks": [lambda d: emit("processing") if d["status"] == "started" else None]})
    if not shutil.which("ffmpeg"):
        raise ValueError("FFmpeg is missing. Install FFmpeg, then restart ClipDock.")
    if data["format"] == "mp3":
        options.update({"format": "bestaudio/best", "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
    else:
        cap = "" if data["quality"] == "best" else f"[height<={int(data['quality'])}]"
        options.update({"format": f"bv*{cap}[ext=mp4]+ba[ext=m4a]/b{cap}[ext=mp4]/bv*{cap}+ba/b{cap}",
                        "merge_output_format": "mp4", "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]})
    with yt_dlp.YoutubeDL(options) as downloader:
        info = first_video(downloader.extract_info(data["url"], download=False))
        emit("metadata", **summary(info))
        downloader.process_ie_result(info, download=True)
    extension = data["format"]
    files = [p for p in completed if p.is_file() and p.suffix == f".{extension}"]
    if not files:
        raise ValueError("Download finished without a usable output file. Try another quality.")
    result = max(files, key=lambda p: p.stat().st_mtime)
    emit("complete", filename=result.name, path=str(result.resolve()), size=result.stat().st_size)


def main():
    try:
        run(json.load(sys.stdin))
    except Exception as exc:
        message = re.sub(r"\x1b\[[0-9;]*m", "", str(exc))
        emit("error", message=message[:1400])
        sys.exit(1)


if __name__ == "__main__":
    main()
