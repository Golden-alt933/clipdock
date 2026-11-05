"""One isolated, sandboxed browser check in Render; no personal profile or account."""
import json
import os
import re
import signal
import subprocess
import threading


def report(**values):
    print("[CD-BROWSER-PROBE] " + json.dumps(values, ensure_ascii=True), flush=True)


def safe(value):
    return re.sub(r"[A-Za-z0-9_-]{50,}", "<DATA>", re.sub(r"https?://\S+", "<URL>", str(value)))[:700]


def probe():
    version = subprocess.run(["chromium", "--version"], capture_output=True, text=True, timeout=10)
    report(stage="start", chromium=version.stdout.strip(), sandbox_enabled=True)
    arguments = ["chromium", "--headless=new", "--disable-gpu", "--disable-dev-shm-usage", "--no-first-run",
                 "--no-default-browser-check", "--user-data-dir=/tmp/clipdock-anonymous-browser-test",
                 "--timeout=60000", "--dump-dom", "https://www.youtube.com/watch?v=q6ZqeyEh64A&hl=en"]
    process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               encoding="utf-8", errors="replace", start_new_session=True)
    try:
        html, errors = process.communicate(timeout=100)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            html, errors = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            html, errors = process.communicate()
        report(result="TIMEOUT", sandbox_enabled=True)
        return
    signals = [safe(line) for line in errors.splitlines()
               if any(term in line.lower() for term in ("sandbox", "namespace", "fatal", "zygote", "err_"))][:5]
    if process.returncode:
        report(result="FAIL", stage="browser_start", exit=process.returncode, signals=signals)
        return
    decoded = None
    for pattern in (r"ytInitialPlayerResponse\s*=\s*", r'window\["ytInitialPlayerResponse"\]\s*=\s*'):
        match = re.search(pattern, html)
        if match:
            try:
                decoded, _ = json.JSONDecoder().raw_decode(html[match.end():])
                break
            except ValueError:
                continue
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    if decoded:
        status = decoded.get("playabilityStatus", {})
        stream = decoded.get("streamingData", {})
        count = len(stream.get("formats", [])) + len(stream.get("adaptiveFormats", []))
        report(result="PASS" if status.get("status") == "OK" and count else "FAIL", stage="player",
               status=status.get("status"), reason=safe(status.get("reason", "")), formats=count)
    else:
        report(result="FAIL", stage="page", title=safe(title.group(1) if title else ""),
               verification_required=any(term in html.lower() for term in ("captcha", "not a bot", "unusual traffic")),
               bytes=len(html), signals=signals)
    report(stage="complete")


if __name__ == "__main__":
    threading.Thread(target=probe, daemon=True).start()
    from clipdock.web import main
    main()
