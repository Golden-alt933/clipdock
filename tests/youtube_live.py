"""Live check against a running hosted container: YouTube inspect + full download.

Makes real requests to YouTube. Used by the manual WARP workflow, not the unit tests.
Usage: python tests/youtube_live.py [base_url] [youtube_url]
"""
import json
import sys
import time
import urllib.error
import urllib.request

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:10000"
video = sys.argv[2] if len(sys.argv) > 2 else "https://www.youtube.com/shorts/q6ZqeyEh64A"


def call(path, payload=None, headers=None, timeout=150):
    request = urllib.request.Request(base + path, headers=headers or {},
                                     data=None if payload is None else json.dumps(payload).encode())
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(request, timeout=timeout)


for _ in range(60):
    try:
        call("/healthz", timeout=2).close()
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("Container did not become healthy.")
time.sleep(5)  # give the WARP proxy a moment to register and connect

with call("/api/config") as response:
    config = json.load(response)
    cookie = response.headers["Set-Cookie"].split(";")[0]
auth = {"Cookie": cookie, "X-ClipDock-Token": config["token"]}

try:
    with call("/api/inspect", {"url": video}, auth) as response:
        meta = json.load(response)
except urllib.error.HTTPError as error:
    raise SystemExit(f"Inspect failed: HTTP {error.code} {error.read().decode()[:400]}")
print(f"Inspect OK: {meta['title']!r}, {meta['duration']}s, heights {meta['heights']}")

with call("/api/jobs", {"url": video, "format": "mp4", "quality": "720"}, auth) as response:
    job = json.load(response)
job_id = job["id"]
for _ in range(180):
    with call("/api/jobs", headers=auth) as response:
        job = next(j for j in json.load(response) if j["id"] == job_id)
    if job["status"] in ("complete", "error", "cancelled"):
        break
    time.sleep(1)
if job["status"] != "complete":
    raise SystemExit(f"Download did not complete: {job}")
print(f"Download OK: {job.get('filename')} ({job.get('size')} bytes)")

with call(f"/api/jobs/{job_id}/file", headers=auth) as response:
    body = response.read()
assert len(body) == job.get("size"), (len(body), job.get("size"))
with open("youtube-live.mp4", "wb") as handle:
    handle.write(body)
print(f"File transfer OK: {len(body)} bytes saved to youtube-live.mp4")
