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
| Sandboxed Chromium inside Render | Google's CAPTCHA was completed by the owner. YouTube's webpage then loaded, but its video player still displayed “Sign in to confirm you're not a bot.” |
| Download with the CAPTCHA-verified Render guest profile | No completed video was produced. Clearing Google's traffic check did not clear YouTube's player restriction. |

Singapore, Frankfurt and Ohio have all rejected direct YouTube extraction. The results establish a cloud-side request restriction; they do not identify which part of Google's private detection system caused it. Some browser/session-engine experiments also exceeded the Free instance's 512 MB memory limit. Those experiments are not suitable production changes.

## Verification experiment

The diagnostic viewer controls a fresh anonymous Chromium profile inside the Ohio test service. It requires a private deployment key plus the owning browser's signed session and CSRF token. Access expires after 15 minutes; other visitors cannot access frames, inputs or results. Account sign-in and unrelated destinations are disabled. It does not import anyone's personal browser profile or Google account cookies.

The owner completed Google's CAPTCHA, and the bounded download test used only that server-created guest profile. The test failed. The browser screenshot independently confirms that YouTube still required sign-in after the CAPTCHA. The test's minimal response does not expose yt-dlp's internal failure details, so it cannot establish whether cookie extraction introduced an additional failure.

This is **not a working fix**. The temporary Ohio service was suspended and its source/startup settings restored. Browser-control code remains on the diagnostic branch; it was not merged into production. No Google account was signed in, and account-authenticated operation remains untested. No diagnostic change should reach production until the original public download succeeds end to end.

All media fetching remains on Render. No external download API, proxy, paid resource or owner-PC worker is part of this experiment.
