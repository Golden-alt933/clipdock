"""Temporary owner-only verification of an anonymous Render browser.

Diagnostic branch only. The browser has no personal profile or account, is
sandboxed, and is limited to the supplied public video and Google's challenge.
"""
import asyncio
import base64
import json
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from pydantic import BaseModel, Field

from . import hosting
from .app import app, current_owner

KEY = os.environ.get("CLIPDOCK_VERIFY_KEY", "")
PROFILE = "/tmp/clipdock-owner-guest-profile"
VIDEO = "https://www.youtube.com/watch?v=q6ZqeyEh64A&hl=en"
LOCK = threading.RLock()
OWNER = None
EXPIRES = 0
PROCESS = None
SOCKET = None
SEQUENCE = 0
RESULT = {"status": "idle"}
ATTEMPTS = 0


def cdp(method, params=None):
    global SEQUENCE
    if SOCKET is None:
        raise RuntimeError("The verification browser is not running.")
    SEQUENCE += 1
    identifier = SEQUENCE
    SOCKET.send(json.dumps({"id": identifier, "method": method, "params": params or {}}))
    while True:
        message = json.loads(SOCKET.recv())
        if message.get("id") == identifier:
            if "error" in message:
                raise RuntimeError("The verification browser could not complete this action.")
            return message.get("result", {})


def stop_browser():
    global SOCKET, PROCESS
    with LOCK:
        if SOCKET is not None:
            try:
                cdp("Browser.close")
            except Exception:
                pass
            SOCKET.close()
            SOCKET = None
        if PROCESS is not None:
            try:
                PROCESS.wait(timeout=5)
            except subprocess.TimeoutExpired:
                terminate(PROCESS)
            PROCESS = None


def terminate(process):
    """Reap the entire bounded diagnostic process tree."""
    if process.poll() is not None:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
            process.wait(timeout=5)
            return
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            continue


def allowed_page():
    result = cdp("Runtime.evaluate", {"expression": "location.href", "returnByValue": True})
    url = urlsplit(result.get("result", {}).get("value", ""))
    allowed = url.scheme == "https" and ((url.hostname == "www.youtube.com" and url.path in ("/watch", "/sorry/index")) or (
        url.hostname in {"www.google.com", "google.com"} and url.path.startswith(("/sorry", "/recaptcha")))
    )
    if not allowed:
        stop_browser()
        raise RuntimeError("Verification stopped: account sign-in and other destinations are disabled.")


def start_browser():
    global PROCESS, SOCKET
    import websocket
    arguments = ["chromium", "--headless=new", "--disable-gpu", "--disable-dev-shm-usage", "--no-first-run",
                 "--no-default-browser-check", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9222",
                 "--user-data-dir=" + PROFILE, "--window-size=1280,720", "about:blank"]
    PROCESS = subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=True)
    for _ in range(60):
        if PROCESS.poll() is not None:
            raise RuntimeError("The sandboxed verification browser could not start.")
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=2) as response:
                targets = json.load(response)
            target = next(target for target in targets if target.get("type") == "page")
            endpoint = target["webSocketDebuggerUrl"]
            if urlsplit(endpoint).hostname not in {"127.0.0.1", "localhost"}:
                raise RuntimeError("Unexpected browser connection.")
            SOCKET = websocket.create_connection(endpoint, timeout=15, suppress_origin=True)
            cdp("Page.enable")
            cdp("Emulation.setDeviceMetricsOverride", {"width": 1280, "height": 720, "deviceScaleFactor": 1, "mobile": False})
            cdp("Page.navigate", {"url": VIDEO})
            for _ in range(50):
                location = cdp("Runtime.evaluate", {"expression": "location.href", "returnByValue": True})
                if location.get("result", {}).get("value", "about:blank") != "about:blank":
                    allowed_page()
                    return
                time.sleep(0.2)
            raise RuntimeError("The verification page did not load.")
        except (OSError, StopIteration):
            time.sleep(1)
    raise RuntimeError("The verification browser took too long to start.")


def authorize(request):
    if not KEY or not OWNER or current_owner(request) != OWNER or time.monotonic() > EXPIRES:
        raise HTTPException(403, "Owner verification access is required.")


class Unlock(BaseModel):
    key: str = Field(max_length=128)


class Click(BaseModel):
    x: int = Field(ge=0, le=1279)
    y: int = Field(ge=0, le=719)


class TextInput(BaseModel):
    text: str = Field(max_length=40, pattern=r"^[A-Za-z0-9 ]*$")


@app.get("/owner-verification", response_class=HTMLResponse)
def owner_page():
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>ClipDock · Owner verification</title><link rel="stylesheet" href="/owner-verification/style.css">
<main><p class="eyebrow">CLIPDOCK / OWNER ONLY</p><h1>Verify the Render browser.</h1>
<p>This is an anonymous browser on the Render test server. Complete Google's human verification if it offers one. Account sign-in is disabled.</p>
<form id="unlock"><label>Owner verification key<input id="key" type="password" autocomplete="off" required></label><button>Open verification</button></form>
<p id="status" role="status">Enter the owner key to begin. This page expires after 15 minutes.</p>
<section id="viewer" hidden><p>Click the browser image to interact with Google's challenge.</p><img id="frame" alt="Live anonymous Render browser" width="1280" height="720">
<form id="text-form"><label>CAPTCHA text, if requested<input id="text" maxlength="40" autocomplete="off"></label><button>Enter text</button></form>
<button id="test">Check download after verification</button><a id="save" hidden>Save test video</a></section></main>
<script src="/owner-verification/client.js"></script></html>'''


@app.get("/owner-verification/style.css")
def owner_style():
    return Response('''body{margin:0;background:#101923;color:#e9f4ff;font:16px/1.6 system-ui,sans-serif}main{max-width:1280px;margin:40px auto;padding:0 24px}h1{font-size:36px;letter-spacing:-1px}.eyebrow{color:#9bcaf5;font-size:12px;letter-spacing:2px}input,button,a{border-radius:12px;padding:12px 18px;font:inherit}input{display:block;background:#172737;border:1px solid #52708b;color:white;max-width:440px}button,a{display:inline-block;background:#b7dcff;border:0;color:#102438;cursor:pointer;margin:12px 12px 12px 0}img{width:100%;height:auto;background:white;border-radius:12px;cursor:crosshair}label{display:block}form{margin:18px 0}[hidden]{display:none!important}#status{color:#b8d4e9}''', media_type="text/css")


@app.get("/owner-verification/client.js")
def owner_script():
    return Response('''let token, timer, busy=false;const status=document.querySelector('#status');async function api(path,data){if(!token){const c=await(await fetch('/api/config')).json();token=c.token}const r=await fetch('/owner-verification/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-ClipDock-Token':token},body:JSON.stringify(data||{})});let d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'Request failed');return d}async function refresh(){if(busy)return;busy=true;try{const r=await fetch('/owner-verification/frame');if(!r.ok){clearInterval(timer);throw Error((await r.json()).detail)}const blob=await r.blob(),img=document.querySelector('#frame'),reader=new FileReader();reader.onload=()=>{img.src=reader.result};reader.readAsDataURL(blob)}catch(e){status.textContent=e.message}finally{busy=false}}document.querySelector('#unlock').onsubmit=async e=>{e.preventDefault();try{status.textContent='Starting the Render browser…';await api('unlock',{key:document.querySelector('#key').value});document.querySelector('#key').value='';document.querySelector('#unlock').hidden=true;document.querySelector('#viewer').hidden=false;status.textContent='Complete the verification in the browser image below.';await refresh();timer=setInterval(refresh,2500)}catch(e){status.textContent=e.message}};document.querySelector('#frame').onclick=async e=>{try{const r=e.target.getBoundingClientRect();await api('click',{x:Math.min(1279,Math.floor((e.clientX-r.left)*1280/r.width)),y:Math.min(719,Math.floor((e.clientY-r.top)*720/r.height))});await refresh()}catch(e){status.textContent=e.message}};document.querySelector('#text-form').onsubmit=async e=>{e.preventDefault();try{await api('text',{text:document.querySelector('#text').value});document.querySelector('#text').value='';await refresh()}catch(e){status.textContent=e.message}};document.querySelector('#test').onclick=async()=>{try{clearInterval(timer);status.textContent='Checking whether the verified session can download your video…';const d=await api('test');status.textContent=d.message;if(d.ready){const save=document.querySelector('#save');save.href='/owner-verification/result';save.textContent='Save test video';save.hidden=false}}catch(e){status.textContent=e.message}};''', media_type="application/javascript")


@app.post("/owner-verification/unlock")
async def unlock(data: Unlock, request: Request):
    global OWNER, EXPIRES, ATTEMPTS
    if not hosting.HOSTED:
        raise HTTPException(404)
    with LOCK:
        ATTEMPTS += 1
        if ATTEMPTS > 10:
            raise HTTPException(429, "Verification unlock attempts exhausted for this test deployment.")
    if not KEY or not secrets.compare_digest(data.key, KEY):
        raise HTTPException(403, "Incorrect owner key.")
    with LOCK:
        if OWNER and OWNER != current_owner(request):
            raise HTTPException(403, "This verification is already bound to its owner browser.")
        if OWNER:
            authorize(request)
            return {"ready": SOCKET is not None}
        OWNER = current_owner(request)
        EXPIRES = time.monotonic() + 900
    try:
        def start():
            with LOCK:
                start_browser()
        await asyncio.to_thread(start)
    except Exception as exc:
        stop_browser()
        raise HTTPException(503, str(exc)) from None
    timer = threading.Timer(900, stop_browser)
    timer.daemon = True
    timer.start()
    return {"ready": True}


@app.get("/owner-verification/frame")
def frame(request: Request):
    authorize(request)
    with LOCK:
        try:
            allowed_page()
            result = cdp("Page.captureScreenshot", {"format": "jpeg", "quality": 65, "captureBeyondViewport": False})
            return Response(base64.b64decode(result["data"]), media_type="image/jpeg", headers={"Cache-Control": "no-store"})
        except Exception as exc:
            raise HTTPException(503, str(exc)) from None


@app.post("/owner-verification/click")
def click(data: Click, request: Request):
    authorize(request)
    with LOCK:
        allowed_page()
        for kind in ("mousePressed", "mouseReleased"):
            cdp("Input.dispatchMouseEvent", {"type": kind, "x": data.x, "y": data.y, "button": "left", "clickCount": 1})
    return {"ok": True}


@app.post("/owner-verification/text")
def enter_text(data: TextInput, request: Request):
    authorize(request)
    with LOCK:
        allowed_page()
        cdp("Input.insertText", {"text": data.text})
    return {"ok": True}


@app.post("/owner-verification/test")
async def test_download(request: Request):
    authorize(request)
    with LOCK:
        if RESULT["status"] != "idle":
            raise HTTPException(409, "This deployment allows one verification download test.")
        allowed_page()
        RESULT.update(status="running", path=None)
        stop_browser()
    destination = Path("/tmp/clipdock-owner-result")
    destination.mkdir(exist_ok=True)
    arguments = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-cache-dir", "--no-playlist",
                 "--js-runtimes", "node", "--cookies-from-browser", "chromium:" + PROFILE,
                 "--socket-timeout", "25", "--retries", "0", "--max-filesize", "100M",
                 "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b", "-S", "res:720",
                 "--merge-output-format", "mp4", "--remux-video", "mp4", "-o", str(destination / "test.%(ext)s"), VIDEO]
    def run():
        process = subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True)
        try:
            process.wait(timeout=150)
            file = destination / "test.mp4"
            ready = process.returncode == 0 and file.is_file() and 0 < file.stat().st_size <= 100 * 1024 * 1024
            RESULT.update(status="complete" if ready else "error", path=str(file) if ready else None)
            return {"ready": ready, "message": "The Render download completed. You can save the test video below." if ready else
                    "YouTube still rejected this verified guest session. No working download was produced."}
        except subprocess.TimeoutExpired:
            terminate(process)
            RESULT.update(status="error", path=None)
            return {"ready": False, "message": "The download test timed out."}
    return await asyncio.to_thread(run)


@app.get("/owner-verification/result")
def result_file(request: Request):
    authorize(request)
    if RESULT.get("status") != "complete":
        raise HTTPException(404, "No completed test video.")
    path = Path(RESULT["path"])
    if not hosting.reserve_transfer(path.stat().st_size):
        raise HTTPException(429, "Transfer allowance reached.")
    return FileResponse(path, filename="ClipDock YouTube test.mp4", media_type="video/mp4")


if __name__ == "__main__":
    if not hosting.HOSTED or len(KEY) < 32:
        raise SystemExit("Private verification requires hosted mode and an owner key of at least 32 characters.")
    from .web import main
    main()
