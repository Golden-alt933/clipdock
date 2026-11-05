# YouTube system audit

Status: **unresolved on Render**, 5 November 2026. The production website remains on 0.9.1. Experiments are isolated on `diagnose/youtube-render` and a separate Free test service.

## Reproduction

The supplied Short is `https://www.youtube.com/shorts/q6ZqeyEh64A`. The public control is `https://www.youtube.com/watch?v=jNQXAC9IVRw`.

| Check | Observed result |
| --- | --- |
| Local ClipDock worker, supplied Short, hosted size/duration limits | Complete MP4: 5,916,143 bytes, 720 × 1280, AV1 + AAC, 24.96 seconds. Full FFmpeg decode succeeded. |
| Production Render API, supplied Short | HTTP 422 at metadata inspection; YouTube sign-in/rate-limit error. |
| Production-image runtime on Ohio | Python 3.13.18, yt-dlp 2026.10.26, EJS 0.8.0, curl-cffi 0.17.0. Node 22.23.4, FFmpeg and FFprobe all executed successfully. |
| Standalone yt-dlp in that image, outside ClipDock's worker | Both public videos rejected with `LOGIN_REQUIRED`; supplied Short's webpage returned HTTP 429. |
| Matched anonymous visitor data and PO tokens | Three mweb/Safari variants rejected at inspection, including session and per-video token paths. |
| Current self-hosted Invidious Companion, entirely inside Render | Failed session validation; no usable formats, initialization timed out. Not a working fallback. |
| Sandboxed Chromium inside Render | Reached Google's unusual-traffic page. A real reCAPTCHA checkbox loaded in the private test viewer. |

Singapore, Frankfurt and Ohio have all rejected direct YouTube extraction. The results establish a cloud-side request restriction; they do not identify which part of Google's private detection system caused it. Some browser/session-engine experiments also exceeded the Free instance's 512 MB memory limit. Those experiments are not suitable production changes.

## Verification experiment

The diagnostic viewer controls a fresh anonymous Chromium profile inside the Ohio test service. It requires a private deployment key plus the owning browser's signed session and CSRF token. Access expires after 15 minutes; other visitors cannot access frames, inputs or results. Account sign-in and unrelated destinations are disabled. It does not import anyone's personal browser profile or Google account cookies.

Google human verification is pending. If it completes, a single bounded download test will use only that server-created guest profile. A successful CAPTCHA alone does **not** establish that YouTube extraction, stream transfer or future anonymous visitor downloads will work. No diagnostic change should reach production until the original public download succeeds end to end.

All media fetching remains on Render. No external download API, proxy, paid resource or owner-PC worker is part of this experiment.
