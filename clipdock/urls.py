"""Accept individual video links from the three supported services."""
import re
from urllib.parse import parse_qs, urlencode, urlsplit


def normalize_url(value):
    value = value.strip()
    if len(value) > 2000:
        raise ValueError("That link is too long.")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("Paste an HTTPS video link from YouTube, Instagram, or Pinterest.")
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [""])[0]
        else:
            match = re.fullmatch(r"/(?:shorts|embed|live)/([\w-]{11})", path)
            video_id = match[1] if match else ""
        if not re.fullmatch(r"[\w-]{11}", video_id):
            raise ValueError("Paste one YouTube video or Short, rather than a channel or playlist.")
        return f"https://www.youtube.com/watch?{urlencode({'v': video_id})}", "YouTube"
    if host in ("youtu.be", "www.youtu.be") and re.fullmatch(r"/[\w-]{11}", path):
        return f"https://www.youtube.com/watch?v={path[1:]}", "YouTube"
    if host in ("instagram.com", "www.instagram.com", "m.instagram.com"):
        if not re.fullmatch(r"/(?:reel|reels|p|tv)/[\w-]+", path):
            raise ValueError("Paste an Instagram Reel or post link.")
        return f"https://www.instagram.com{path.replace('/reels/', '/reel/', 1)}/", "Instagram"
    pinterest_hosts = {"pinterest.com", "pinterest.in", "pinterest.co.uk", "pinterest.ca", "pinterest.com.au"}
    pin = re.fullmatch(r"/pin/(?:[\w-]+--)?(\d+)", path)
    if host.removeprefix("www.") in pinterest_hosts and pin:
        return f"https://{host}/pin/{pin[1]}/", "Pinterest"
    if host == "pin.it" and re.fullmatch(r"/[A-Za-z0-9]+", path):
        return f"https://pin.it{path}", "Pinterest"
    raise ValueError("Use a YouTube video, Instagram Reel/post, or Pinterest video Pin link.")
