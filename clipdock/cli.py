"""Cross-platform commands for the local interface and direct downloads."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .urls import normalize_url


def parser():
    result = argparse.ArgumentParser(prog="clipdock", description="Save public YouTube, Instagram, and Pinterest videos locally.")
    result.add_argument("--version", action="version", version=f"ClipDock {__version__}")
    commands = result.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Start the local browser interface")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--open", action="store_true", help="Open your default browser")
    serve.add_argument("--data-dir", type=Path, help="Directory for history and the Downloads folder")
    download = commands.add_parser("download", help="Download directly from the terminal")
    download.add_argument("url")
    download.add_argument("--format", choices=("mp4", "mp3"), default="mp4")
    download.add_argument("--quality", choices=("best", "360", "720", "1080", "2160"), default="1080")
    download.add_argument("--output", "-o", type=Path, default=Path.cwd() / "Downloads", help="Destination directory")
    download.add_argument("--json", action="store_true", help="Print newline-delimited JSON events")
    commands.add_parser("doctor", help="Check Python, FFmpeg, FFprobe, and Node.js")
    return result


def doctor():
    print(f"ClipDock {__version__} / Python {sys.version.split()[0]}")
    missing = []
    for tool in ("ffmpeg", "ffprobe", "node"):
        path = shutil.which(tool)
        print(f"{tool}: {path or 'MISSING'}")
        if not path:
            missing.append(tool)
    print("Install missing tools and open a new terminal before trying again." if missing else "Ready to download.")
    return 1 if missing else 0


def download(args):
    try:
        url, platform = normalize_url(args.url)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("FFmpeg and FFprobe are required. Run: clipdock doctor", file=sys.stderr)
        return 2
    options = {"mode": "download", "url": url, "format": args.format, "quality": args.quality,
               "folder": str(args.output.expanduser().resolve())}
    process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).with_name("worker.py"))],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8",
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                               start_new_session=os.name != "nt")
    try:
        process.stdin.write(json.dumps(options) + "\n")
        process.stdin.close()
        complete = False
        for line in process.stdout:
            if args.json:
                print(line.rstrip(), flush=True)
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event["event"] == "complete":
                complete = True
            if args.json:
                continue
            kind = event["event"]
            if kind == "metadata":
                print(f"{platform}: {event['title']}", flush=True)
            elif kind == "progress":
                value = event.get("percent")
                print(f"Downloading: {value:.1f}%" if value is not None else "Downloading…", flush=True)
            elif kind == "processing":
                print("Finishing file…", flush=True)
            elif kind == "complete":
                print(f"Saved: {event['path']}", flush=True)
            elif kind == "error":
                print(f"Error: {event['message']}", file=sys.stderr)
        code = process.wait()
        return 0 if complete and code == 0 else (code or 1)
    except KeyboardInterrupt:
        if process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                import signal
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            process.wait()
        print("Cancelled. Partial files are kept in the output folder.", file=sys.stderr)
        return 130


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = parser().parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "download":
        return download(args)
    if not 1 <= args.port <= 65535:
        parser().error("--port must be between 1 and 65535")
    if args.data_dir:
        os.environ["CLIPDOCK_DATA_DIR"] = str(args.data_dir.expanduser().resolve())
    import uvicorn
    from .app import app
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning", access_log=False))
    app.state.server = server
    url = f"http://127.0.0.1:{args.port}"
    print(f"ClipDock is starting at {url}\nPress Ctrl+C to stop.", flush=True)
    if args.open:
        timer = threading.Timer(1.5, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    server.run()
    return 0
