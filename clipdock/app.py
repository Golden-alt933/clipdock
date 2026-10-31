"""ClipDock: a loopback-only video downloader with isolated cancellable jobs."""
import asyncio
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .paths import data_directory
from .urls import normalize_url
from . import __version__, hosting

ROOT = Path(__file__).resolve().parent
DATA = data_directory()
DOWNLOADS = DATA / "Downloads"
STATE = DATA / "history.json"
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.RLock()
POOL = ThreadPoolExecutor(max_workers=1 if hosting.HOSTED else 2, thread_name_prefix="clipdock")
INSPECTIONS = asyncio.Semaphore(2)
JOBS = {}
PROCESSES = {}
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
ACTIVE = {"queued", "starting", "downloading", "processing"}


def current_owner(request):
    return hosting.owner_id(request.state.session_cookie) if hosting.HOSTED else None


def owns_job(request, job):
    return job is not None and (not hosting.HOSTED or job.get("owner") == current_owner(request))


def browser_job(job):
    return {key:value for key, value in job.items() if key not in {"owner", "path"}}


def clean_expired():
    """Only delete generated, expired job folders inside hosted temporary storage."""
    if not hosting.HOSTED:
        return
    now = time.time()
    root = DOWNLOADS.resolve()
    with LOCK:
        expired = [key for key, job in JOBS.items() if job["status"] not in ACTIVE
                   and now - job.get("finished_at", job["created"]) > hosting.FILE_TTL]
        for key in expired:
            if not re.fullmatch(r"[a-f0-9]{32}", key):
                continue
            folder = (root / key).resolve()
            if folder.parent == root and folder.name == key and folder.is_dir():
                shutil.rmtree(folder)
            JOBS.pop(key, None)
        if expired:
            save_state()


def save_state():
    with LOCK:
        DATA.mkdir(parents=True, exist_ok=True)
        temporary = STATE.with_suffix(".tmp")
        temporary.write_text(json.dumps(list(JOBS.values()), ensure_ascii=True, indent=2), encoding="utf-8")
        temporary.replace(STATE)


def load_state():
    if STATE.exists():
        try:
            for item in json.loads(STATE.read_text(encoding="utf-8")):
                if not re.fullmatch(r"[a-f0-9]{32}", item.get("id", "")):
                    continue
                if item.get("status") in ACTIVE:
                    item.update(status="interrupted", error="The app closed before this download finished. Add the link again to retry.")
                JOBS[item["id"]] = item
        except (ValueError, KeyError, TypeError):
            pass


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, creationflags=NO_WINDOW, timeout=15)
    else:
        import signal
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def friendly_error(message):
    low = message.lower()
    if any(x in low for x in ("login required", "sign in", "log in", "cookies", "rate-limit", "rate limit")):
        return "The platform requires sign-in or is limiting requests for this link. Try a public video or try again later. ClipDock does not collect account passwords."
    if "private" in low:
        return "This video is private or restricted. Try a publicly accessible video."
    if "not available" in low or "unavailable" in low:
        return "This video is unavailable here. It may have been removed or restricted by its creator or region."
    return message.removeprefix("ERROR: ")[:900]


def run_job(job_id):
    with LOCK:
        job = JOBS[job_id]
        if job["status"] != "queued":
            return
        job.update(status="starting", error=None)
        save_state()
        try:
            process = subprocess.Popen([sys.executable, "-u", str(ROOT / "worker.py")], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                       encoding="utf-8", creationflags=NO_WINDOW, start_new_session=os.name != "nt")
        except OSError:
            job.update(status="error", error="Could not start the downloader. Restart ClipDock and try again.")
            save_state()
            return
        PROCESSES[job_id] = process
    watchdog = None
    if hosting.HOSTED:
        def timeout():
            with LOCK:
                if job["status"] not in ACTIVE:
                    return
                job.update(status="error", error="This download took too long. Try a shorter video.")
            stop_process(process)
        watchdog = threading.Timer(600, timeout)
        watchdog.daemon = True
        watchdog.start()
    try:
        process.stdin.write(json.dumps({"mode": "download", "url": job["url"], "format": job["format"],
                                       "quality": job["quality"], "audio_bitrate": job.get("audio_bitrate", "192"),
                                       "folder": str(DOWNLOADS / job_id),
                                       "max_bytes": hosting.MAX_BYTES if hosting.HOSTED else None,
                                       "max_duration": hosting.MAX_DURATION if hosting.HOSTED else None}) + "\n")
        process.stdin.close()
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            with LOCK:
                if job["status"] in {"cancelled", "interrupted", "error"}:
                    continue
                kind = event.pop("event", "")
                if kind == "metadata":
                    job.update({k: event[k] for k in ("title", "creator", "duration", "thumbnail")})
                elif kind == "progress":
                    job.update(status="downloading", **event)
                elif kind == "processing":
                    job.update(status="processing", speed=None, eta=None)
                elif kind == "complete":
                    job.update(status="complete", percent=100, finished_at=time.time(), **event)
                elif kind == "error":
                    job.update(status="error", error=friendly_error(event["message"]))
                if kind != "progress":
                    save_state()
        process.wait()
        with LOCK:
            if job["status"] in ACTIVE:
                job.update(status="error", error="The download stopped unexpectedly. Try the link again.")
    except Exception as exc:
        stop_process(process)
        with LOCK:
            if job["status"] not in {"cancelled", "interrupted"}:
                job.update(status="error", error=friendly_error(str(exc)))
    finally:
        if watchdog:
            watchdog.cancel()
        with LOCK:
            PROCESSES.pop(job_id, None)
            job.setdefault("finished_at", time.time())
            save_state()


@asynccontextmanager
async def lifespan(app):
    DOWNLOADS.mkdir(parents=True, exist_ok=True)
    load_state()
    clean_expired()
    yield
    with LOCK:
        processes = list(PROCESSES.values())
        for job in JOBS.values():
            if job["status"] in ACTIVE:
                job.update(status="interrupted", error="App closed. Add this link again to retry.")
        save_state()
    for process in processes:
        stop_process(process)
    POOL.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="ClipDock", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
allowed_hosts = ["127.0.0.1", "localhost", "testserver"]
if hosting.HOSTED:
    external_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME") or os.environ.get("CLIPDOCK_PUBLIC_HOST")
    if external_host:
        allowed_hosts.append(external_host)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


@app.middleware("http")
async def local_access(request: Request, call_next):
    if hosting.HOSTED:
        cookie, new_cookie = hosting.session_identity(request)
        request.state.session_cookie = cookie
        expected_token = hosting.csrf_token(cookie)
    else:
        new_cookie = False
        expected_token = TOKEN
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if not secrets.compare_digest(request.headers.get("x-clipdock-token", ""), expected_token):
            return JSONResponse({"detail": "Refresh ClipDock and try again."}, status_code=403)
    response = await call_next(request)
    if new_cookie:
        response.set_cookie(hosting.COOKIE, cookie, max_age=86400, httponly=True, secure=True, samesite="strict")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


class Link(BaseModel):
    url: str = Field(max_length=2000)


class Download(Link):
    format: str = "mp4"
    quality: str = "1080"
    audio_bitrate: str = "320"


@app.get("/healthz")
def health():
    return {"status":"ok", "version":__version__}


@app.get("/api/config")
def config(request: Request):
    import yt_dlp.version
    return {"app": "ClipDock", "token": hosting.csrf_token(request.state.session_cookie) if hosting.HOSTED else TOKEN,
            "hosted":hosting.HOSTED, "downloads": None if hosting.HOSTED else str(DOWNLOADS),
            "limits": {"minutes":10,"megabytes":100,"retention_minutes":60} if hosting.HOSTED else None,
            "ffmpeg": bool(shutil.which("ffmpeg")), "node": bool(shutil.which("node")), "engine": yt_dlp.version.__version__}


@app.post("/api/inspect")
async def inspect_link(data: Link, request: Request):
    if hosting.HOSTED and not hosting.rate_allowed(request.client.host, "inspect"):
        raise HTTPException(429, "Please wait a few minutes before looking up more videos.")
    try:
        url, platform = normalize_url(data.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    async with INSPECTIONS:
        def extract():
            try:
                result = subprocess.run([sys.executable, "-u", str(ROOT / "worker.py")],
                                        input=json.dumps({"mode": "inspect", "url": url}), text=True,
                                        encoding="utf-8", capture_output=True, timeout=120, creationflags=NO_WINDOW)
                events = []
                for line in result.stdout.splitlines():
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        pass
                meta = next((x for x in events if x.get("event") == "metadata"), None)
                if meta:
                    return {**meta, "url": url, "platform": platform}
                error = next((x["message"] for x in events if x.get("event") == "error"), "Could not read this video.")
                raise HTTPException(422, friendly_error(error))
            except subprocess.TimeoutExpired:
                raise HTTPException(504, "The platform took too long to respond. Try again in a moment.")
        return await asyncio.to_thread(extract)


@app.get("/api/jobs")
def jobs(request: Request):
    clean_expired()
    with LOCK:
        return list(reversed([browser_job(job) for job in JOBS.values() if owns_job(request, job)]))


@app.post("/api/jobs", status_code=202)
def add_job(data: Download, request: Request):
    clean_expired()
    if hosting.HOSTED and not hosting.rate_allowed(request.client.host, "download"):
        raise HTTPException(429, "You have started several downloads. Please wait a few minutes before adding more.")
    try:
        url, platform = normalize_url(data.url)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if (data.format not in ("mp4", "mp3", "audio")
            or data.quality not in ("best", "360", "720", "1080", "2160")
            or data.audio_bitrate not in ("128", "192", "256", "320")):
        raise HTTPException(400, "Choose one of the available format and quality options.")
    if not shutil.which("ffmpeg"):
        raise HTTPException(503, "FFmpeg is missing. Install FFmpeg, then restart ClipDock.")
    with LOCK:
        if hosting.HOSTED:
            if sum(j["status"] in ACTIVE and owns_job(request, j) for j in JOBS.values()) >= 2:
                raise HTTPException(429, "Please let your current downloads finish first.")
            if sum(j["status"] in ACTIVE for j in JOBS.values()) >= 6:
                raise HTTPException(429, "The download queue is busy. Try again shortly.")
        if sum(j["status"] in ACTIVE for j in JOBS.values()) >= 20:
            raise HTTPException(429, "The queue is full. Let a few downloads finish first.")
        job = {"id": uuid.uuid4().hex, "url": url, "platform": platform, "format": data.format,
               "quality": data.quality, "audio_bitrate": data.audio_bitrate,
               "status": "queued", "percent": 0, "created": time.time(),
               "title": "Reading video…", "error": None}
        if hosting.HOSTED:
            job["owner"] = current_owner(request)
        JOBS[job["id"]] = job
        save_state()
        POOL.submit(run_job, job["id"])
        return browser_job(job)


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    with LOCK:
        job = JOBS.get(job_id)
        if not owns_job(request, job):
            raise HTTPException(404, "Download not found.")
        if job["status"] not in ACTIVE:
            return browser_job(job)
        job.update(status="cancelled", error=None)
        process = PROCESSES.get(job_id)
        save_state()
    if process:
        stop_process(process)
    return browser_job(job)


@app.get("/api/jobs/{job_id}/file")
def get_file(job_id: str, request: Request):
    clean_expired()
    with LOCK:
        job = JOBS.get(job_id)
        if not owns_job(request, job) or job["status"] != "complete" or not job.get("filename"):
            raise HTTPException(404, "This download is not ready yet.")
        folder = (DOWNLOADS / job_id).resolve()
        path = (folder / job["filename"]).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise HTTPException(404, "The file has been moved or is no longer available.")
        if hosting.HOSTED and not hosting.reserve_transfer(path.stat().st_size):
            raise HTTPException(503, "This free instance has reached its transfer allowance. Please try again later.")
    media_types = {".mp3":"audio/mpeg", ".m4a":"audio/mp4", ".opus":"audio/ogg", ".ogg":"audio/ogg"}
    content_type = media_types.get(path.suffix, "audio/webm" if job["format"] == "audio" and path.suffix == ".webm"
                                   else mimetypes.guess_type(path.name)[0] or "application/octet-stream")
    return FileResponse(path, filename=path.name, media_type=content_type)


@app.post("/api/open-folder")
def open_folder():
    if hosting.HOSTED:
        raise HTTPException(404, "Not available on the hosted website.")
    if os.name == "nt":
        os.startfile(str(DOWNLOADS))
        return {"ok": True}
    opener = shutil.which("open" if sys.platform == "darwin" else "xdg-open")
    if opener and (sys.platform == "darwin" or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        subprocess.Popen([opener, str(DOWNLOADS)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return {"ok": True}
    return {"ok": False, "path": str(DOWNLOADS)}


@app.post("/api/shutdown")
def shutdown():
    if hosting.HOSTED:
        raise HTTPException(404, "Not available on the hosted website.")
    server = getattr(app.state, "server", None)
    if server:
        def finish():
            server.should_exit = True
        threading.Timer(0.4, finish).start()
    return {"ok": bool(server)}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
