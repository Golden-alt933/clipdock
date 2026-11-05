# YouTube on Render

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

The token provider was `bgutil-ytdlp-pot-provider` **2.0.2**, running entirely on Render. Its Node runtime required `libatomic1` in the test image; after that startup dependency was added, the provider was healthy and produced tokens successfully. The remaining failures therefore cannot be attributed solely to the provider failing to start or tokens never being generated.

These are extraction tests. A successful provider health check or generated token is not a successful download. The original Singapore deployment also rejects the supplied Short.

## What this means

The website's browser interface sends requests to ClipDock. YouTube sees the network address of the machine fetching its page and media, which is Render in this deployment. Another downloader website can use a different network route or extraction service; its visible page does not establish that it uses the same backend as ClipDock.

[yt-dlp recommends a PO-token provider with the `mweb` client](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide). The [provider's verification guide](https://github.com/Brainicism/bgutil-ytdlp-pot-provider#verification) also explains that a token does not remove IP-based login restrictions. The tests above reproduced that distinction.

Keeping the website on Render is compatible with an operator-supplied outbound proxy or managed extraction API. Either would need its own working access and an end-to-end test from Render; a free quota is a usage limit, not unlimited free downloads. Neither integration is configured in the public demo. The owner's PC does not need to become a worker.

The diagnostic startup command was removed, its service configuration restored to `main`, and the temporary instance suspended after testing. The production site retains its stable downloader and working Instagram transport.
