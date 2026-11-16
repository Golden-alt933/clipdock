"""One isolated yt-dlp operation. JSON on stdin; JSON events on stdout."""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

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


def youtube_proxy(url):
    """Route only YouTube through CLIPDOCK_YOUTUBE_PROXY (for example a local WARP SOCKS proxy)."""
    proxy = os.environ.get("CLIPDOCK_YOUTUBE_PROXY", "").strip()
    if not proxy or not url.startswith("https://www.youtube.com/"):
        return None
    parts = urlsplit(proxy)
    if parts.hostname in ("127.0.0.1", "localhost") and parts.port:
        # A local proxy that is still starting (or crashed) would fail every request; go direct instead.
        try:
            socket.create_connection((parts.hostname, parts.port), timeout=1).close()
        except OSError:
            return None
    return proxy


COOKIES_DEFAULT = "/etc/secrets/youtube-cookies.txt"


def youtube_cookies(url):
    """Writable copy of the owner's YouTube cookies file, if one is configured; else None.

    yt-dlp rewrites its cookie file on exit, and secret mounts are read-only, so use a temp copy.
    """
    source = Path(os.environ.get("CLIPDOCK_YOUTUBE_COOKIES", COOKIES_DEFAULT))
    if not url.startswith("https://www.youtube.com/") or not source.is_file():
        return None
    import atexit
    import tempfile
    handle, copy = tempfile.mkstemp(prefix="clipdock-yt-", suffix=".txt")
    os.close(handle)
    shutil.copyfile(source, copy)
    os.chmod(copy, 0o600)
    atexit.register(lambda: os.path.exists(copy) and os.remove(copy))
    return copy


def youtube_options(url):
    """Network options for YouTube: signed-in cookies if configured, otherwise the WARP proxy."""
    cookies = youtube_cookies(url)
    if cookies:
        # Keep a signed-in session on one stable address; switching networks looks more suspicious.
        options = {"cookiefile": cookies}
        if os.environ.get("CLIPDOCK_COOKIES_VIA_PROXY") == "1" and youtube_proxy(url):
            options["proxy"] = youtube_proxy(url)
        return options
    proxy = youtube_proxy(url)
    return {"proxy": proxy} if proxy else {}


# Codecs that After Effects, Premiere Pro, DaVinci Resolve and Final Cut import without plugins.
# YouTube and Instagram often serve VP9/AV1 video (sometimes inside .mp4) and Opus audio, which
# those editors either reject or open as audio only.
EDITABLE_VIDEO = {"h264"}
EDITABLE_PIXEL_FORMATS = {"yuv420p", "yuvj420p"}
EDITABLE_AUDIO = {"aac", "mp3"}
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def probe_streams(path):
    """Return (video codec, pixel format, audio codec) of the first streams; None where absent."""
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,pix_fmt",
                             "-of", "json", str(path)], capture_output=True, text=True, creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise ValueError("FFprobe could not read the downloaded file.")
    streams = json.loads(result.stdout or "{}").get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    return video.get("codec_name"), video.get("pix_fmt"), audio.get("codec_name")


def make_editable(path):
    """Re-encode only what editing apps cannot read, so the MP4 opens with picture and sound.

    H.264 video and AAC audio are copied untouched; anything else (VP9, AV1, HEVC, Opus, 10-bit)
    becomes H.264 yuv420p / AAC. Returns True when the file was converted.
    """
    vcodec, pix_fmt, acodec = probe_streams(path)
    video_ok = vcodec is None or (vcodec in EDITABLE_VIDEO and pix_fmt in EDITABLE_PIXEL_FORMATS)
    audio_ok = acodec is None or acodec in EDITABLE_AUDIO
    if video_ok and audio_ok:
        return False
    emit("converting", video_codec=vcodec, audio_codec=acodec)
    temporary = path.with_name(path.stem + ".converting" + path.suffix)
    command = ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-map", "0:v:0?", "-map", "0:a:0?"]
    command += ["-c:v", "copy"] if video_ok else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
                                                  "-pix_fmt", "yuv420p"]
    command += ["-c:a", "copy"] if audio_ok else ["-c:a", "aac", "-b:a", "192k"]
    command += ["-movflags", "+faststart", str(temporary)]
    result = subprocess.run(command, capture_output=True, text=True, creationflags=NO_WINDOW)
    if result.returncode != 0 or not temporary.is_file():
        if temporary.exists():
            temporary.unlink()
        raise ValueError("Could not convert the video to H.264 for editing apps. " + result.stderr.strip()[-400:])
    os.replace(temporary, path)
    return True


def run(data):
    options = {"quiet": True, "no_warnings": True, "logger": Logger(), "noplaylist": True,
               "playlist_items": "1", "socket_timeout": 25, "retries": 2, "fragment_retries": 2,
               "windowsfilenames": True, "cachedir": False, "js_runtimes": {"node": {}}}
    options.update(youtube_options(data["url"]))
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
                        # At equal resolution, prefer H.264 + AAC so most downloads need no conversion.
                        "format_sort": ["res" if quality == "best" else f"res:{quality}", "vcodec:h264", "acodec:aac"],
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
    if output_format == "mp4" and data.get("editable", True):
        if not shutil.which("ffprobe"):
            raise ValueError("FFprobe is missing. Install FFmpeg (it includes FFprobe), then restart ClipDock.")
        make_editable(result)
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
