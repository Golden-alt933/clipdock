"""Hosted browser sessions and conservative limits for the free web service."""
import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict, deque

HOSTED = os.environ.get("CLIPDOCK_HOSTED") == "1"
SECRET = os.environ.get("CLIPDOCK_SESSION_SECRET", secrets.token_urlsafe(48)).encode()
COOKIE = "clipdock_session"
MAX_BYTES = 100 * 1024 * 1024
MAX_DURATION = 600
FILE_TTL = 3600
MONTHLY_BYTES = 1024 * 1024 * 1024
_LOCK = threading.Lock()
_REQUESTS = defaultdict(deque)
_TRANSFER = {"month": "", "bytes": 0}


def session_identity(request):
    cookie = request.cookies.get(COOKIE, "")
    parts = cookie.split(".")
    if len(parts) == 2 and len(parts[0]) == 64:
        expected = hmac.new(SECRET, parts[0].encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(parts[1], expected):
            return cookie, False
    random = secrets.token_hex(32)
    signature = hmac.new(SECRET, random.encode(), hashlib.sha256).hexdigest()
    return random + "." + signature, True


def owner_id(cookie):
    return hmac.new(SECRET, ("owner:" + cookie).encode(), hashlib.sha256).hexdigest()


def csrf_token(cookie):
    return hmac.new(SECRET, ("csrf:" + cookie).encode(), hashlib.sha256).hexdigest()


def rate_allowed(identity, action):
    limit = 6 if action == "download" else 20
    now = time.monotonic()
    with _LOCK:
        if len(_REQUESTS) > 10000:
            for key in list(_REQUESTS):
                if not _REQUESTS[key] or _REQUESTS[key][-1] < now - 600:
                    _REQUESTS.pop(key, None)
        events = _REQUESTS[(identity, action)]
        while events and events[0] < now - 600:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)
        return True


def reserve_transfer(size):
    """A per-instance cap supplements the host's own usage limits."""
    month = time.strftime("%Y-%m", time.gmtime())
    with _LOCK:
        if _TRANSFER["month"] != month:
            _TRANSFER.update(month=month, bytes=0)
        if _TRANSFER["bytes"] + size > MONTHLY_BYTES:
            return False
        _TRANSFER["bytes"] += size
        return True
