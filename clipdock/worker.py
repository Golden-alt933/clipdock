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
    transferred = {}
    max_bytes = data.get("max_bytes")

    def progress(d):
        import time
        if d["status"] == "downloading":
            if max_bytes:
                transferred[d.get("filename", "media")] = d.get("downloaded_bytes", 0)
                if sum(transferred.values()) > max_bytes:
                    raise ValueError("This video exceeds the hosted site's 100 MB file limit.")
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

    output_format = data["format"]
    bitrate = str(data.get("audio_bitrate", "320"))
    if output_format not in {"mp4", "mp3", "audio"} or bitrate not in {"128", "192", "256", "320"}:
        raise ValueError("Choose a supported format and MP3 bitrate.")
    suffix = f" [{bitrate}kbps]" if output_format == "mp3" else " [source]" if output_format == "audio" else ""
    options.update({"outtmpl": str(folder / ("%(title).100s [%(id)s]" + suffix + ".%(ext)s")),
                    "progress_hooks": [progress], "overwrites": False,
                    "post_hooks": [lambda filename: completed.append(Path(filename))],
                    "postprocessor_hooks": [lambda d: emit("processing") if d["status"] == "started" else None]})
    if max_bytes:
        options["max_filesize"] = max_bytes
    if not shutil.which("ffmpeg"):
        raise ValueError("FFmpeg is missing. Install FFmpeg, then restart ClipDock.")
    if output_format == "mp3":
        options.update({"format": "bestaudio/best", "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": bitrate}]})
    elif output_format == "audio":
        options.update({"format": "bestaudio/best", "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "best"}]})
    else:
        quality = data["quality"]
        if quality not in {"best", "360", "720", "1080", "2160"}:
            raise ValueError("Choose a supported video quality.")
        options.update({"format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
                        "format_sort": ["res" if quality == "best" else f"res:{quality}"],
                        "merge_output_format": "mp4", "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]})
    with yt_dlp.YoutubeDL(options) as downloader:
        info = first_video(downloader.extract_info(data["url"], download=False))
        if data.get("max_duration") and (info.get("duration") or 0) > data["max_duration"]:
            raise ValueError("The free hosted site supports videos up to 10 minutes long.")
        emit("metadata", **summary(info))
        downloader.process_ie_result(info, download=True)
    files = [p for p in completed if p.is_file() and (output_format == "audio" or p.suffix == f".{output_format}")]
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
