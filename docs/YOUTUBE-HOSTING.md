# YouTube on Render

## Fix: Cloudflare WARP for YouTube (added 5 November 2026)

YouTube blocks most cloud server addresses. The hosted image now starts a free, user-space [Cloudflare WARP](https://one.one.one.one/) proxy (`wgcf` + `wireproxy`, no root or kernel module) at `127.0.0.1:40000`, and the worker sends **only YouTube** requests through it. Instagram and Pinterest stay direct. If the proxy is not listening, YouTube falls back to the direct route instead of failing.

Verified on a GitHub-hosted Azure runner (`.github/workflows/warp-youtube.yml`):

| Route | Result |
| --- | --- |
| Direct from the runner | `Sign in to confirm you're not a bot` (the same block Render gets). |
| yt-dlp through WARP | Both test videos inspected; the Short downloaded as 720 × 1280 AV1 + AAC, 24.96 s, 5,916,127 bytes. |
| The hosted Docker image through WARP | `/api/inspect`, a full download job and the browser file transfer all succeeded with the same file. |

Not yet verified on Render itself: WARP needs outbound UDP to Cloudflare (port 2408). Deploy, then test a YouTube link on the public site. Set `CLIPDOCK_WARP=0` to turn it off, or set `CLIPDOCK_YOUTUBE_PROXY` to use a different proxy. Cloudflare could start being blocked by YouTube in future; this is a workaround, not a guarantee.

The investigation below predates this fix.

Tested **5 November 2026**, using the supplied public Short `q6ZqeyEh64A`.

**Status: direct YouTube extraction is still blocked from the tested Render networks.** Instagram and Pinterest downloads have passed on the public demo; this investigation does not establish a working hosted YouTube download.

## Reproduction

An anonymous session on the public ClipDock site submits the URL to `/api/inspect`. The response is HTTP 422 with ClipDock's sign-in/rate-limit message. The downloader's underlying responses on the isolated Render test instance include:

- HTTP 429 (`Too Many Requests`) when fetching the YouTube page.
- A player response requiring sign-in to confirm the request is not from a bot.
- No usable media formats, so there is no media file to merge or transfer.

The same URL returns metadata locally. With Chrome-compatible transport, the local probe returned 51 formats. This difference points to cloud-request filtering rather than a broken URL field or FFmpeg conversion.

## Tests on Render

Tests ran on a separate Free instance in Frankfurt. No visitor passwords, personal browser cookies, or external proxies were used. The playback-token server bound only to `127.0.0.1` inside the container.

| Downloader and configuration | Observed result |
| --- | --- |
| Stable `2026.10.26`: default clients | HTTP 429 and sign-in/bot rejection. |
| Stable: default clients with Chrome TLS transport | Same rejection. |
| Stable: explicit `web_safari`, `web_embedded`, `tv`, or `mweb` | Each rejected before usable formats were returned. |
| Stable: `mweb` with automatic PO-token fetching | Rejected before a token was requested. Installing the provider alone did not fix it. |
| Stable: forced player PO tokens with `mweb` and `web_safari` | Player tokens were generated and supplied; both requests were still rejected. |
| Stable: forced player PO token with `mweb`, skipping webpage/config requests | A player token was supplied; the direct player request still required sign-in. |
| Nightly `2026.11.04.232659`: Chrome transport, automatic tokens, forced tokens, and webpage-skipping variants | All five configurations failed. The three forced-token variants confirmed player-token generation. |
| Nightly: `visionos` and token-backed `mweb` through `youtubei.googleapis.com`, skipping webpage/config requests | Both player requests required sign-in; `mweb` confirmed a generated player token. |
| Nightly: embedded player through `www.youtube-nocookie.com` | The player refused the supplied video with error `152 - 18`. |
| Nightly: embedded player with ClipDock's real HTTPS origin/referrer, with and without a forced player token | Both returned the same `152 - 18` error. Supplying a valid referrer and generated token did not resolve the refusal. |

The token provider was `bgutil-ytdlp-pot-provider` **2.0.2**, running entirely on Render. Its Node runtime required `libatomic1` in the test image; after that startup dependency was added, the provider was healthy and produced tokens successfully. The remaining failures therefore cannot be attributed solely to the provider failing to start or tokens never being generated.

These 20 configurations are extraction tests. A successful provider health check or generated token is not a successful download. The original Singapore deployment also rejects the supplied Short. A third Free deployment in **Ohio**, running the stable production build, returned HTTP 422 with the same sign-in/rate-limit message through both `/api/inspect` and the browser interface.

The local production worker was rechecked after these tests and still returned the supplied video's 25-second duration and available resolutions. The `visionos`/Google API candidate also failed locally, so that candidate alone does not isolate a Render-specific cause; the local/cloud comparison uses the unmodified production worker.

## What this means

The website's browser interface sends requests to ClipDock. YouTube sees the network address of the machine fetching its page and media, which is Render in this deployment. Another downloader website can use a different network route or extraction service; its visible page does not establish that it uses the same backend as ClipDock.

[yt-dlp recommends a PO-token provider with the `mweb` client](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide). The [provider's verification guide](https://github.com/Brainicism/bgutil-ytdlp-pot-provider#verification) also explains that a token does not remove IP-based login restrictions. The tests above reproduced that distinction.

The current deployment must keep video fetching on Render. No managed extraction API or external proxy is configured. The owner's PC does not become a worker.

Render documents that its default [outbound IP ranges are shared](https://render.com/docs/outbound-ip-addresses). Its [dedicated outbound IPs](https://render.com/docs/dedicated-ips) require a Pro workspace and an additional monthly fee, and can still fall within its default ranges. Dedicated IPs have not been tested for this project and are not a verified YouTube fix. No paid resources were provisioned.

The diagnostic startup command was removed, the Frankfurt service configuration restored to `main`, and both Frankfurt and Ohio test instances suspended after testing. The production site retains its stable downloader and working Instagram transport. YouTube remains unresolved under the current free, Render-only requirements.
