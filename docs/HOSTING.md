# Hosted website deployment

The Docker image runs the whole ClipDock website: browser interface, Python API, yt-dlp, Node.js, and FFmpeg. Visitors need no installation or terminal commands.

Version 0.9.1 includes yt-dlp's `curl-cffi` transport for sites that inspect browser TLS fingerprints. This also enables Instagram's public API extraction path. A cloud host's network address can still be rejected by a platform; verify real downloads after each deployment.

## Live demo

[Open ClipDock](https://clipdock-4mt9.onrender.com). It runs on Render's Free plan in Singapore, with manual deployments and temporary file storage.

Verified on **5 November 2026**:

| Platform | Result on this host |
| --- | --- |
| Pinterest | Sample downloaded through Chrome: 720 × 1280 MP4 with H.264 video and AAC audio, 57.7 seconds, 16.1 MiB. |
| YouTube | The supplied Short was rejected with a sign-in/rate-limit error. |
| Instagram | The supplied Reel was rejected with HTTP 429 (Too Many Requests). |

The same YouTube and Instagram links returned metadata successfully from the local app during this check. The Pinterest result verifies the hosted download pipeline. Availability can differ across platforms and videos; use the local app when a platform rejects the hosted service. Platform restrictions and free-host limits may change.

## Deploy on Render's free compute plan

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Golden-alt933/clipdock)

The repository includes `render.yaml` with `plan: free`. It creates one Docker web service, with no paid database, persistent disk, or background-worker service. Render generates the browser-session signing secret automatically. The public hostname is taken from `RENDER_EXTERNAL_HOSTNAME`.

1. Connect your Render account, or use the button above and sign in to Render.
2. Review the Blueprint and confirm the **Free** compute plan.
3. Deploy. Render builds the image, checks `/healthz`, and supplies the public HTTPS URL.
4. Test an actual download on that public URL before advertising the site as working. Successful local downloads do not establish that a cloud server can fetch the same video.

`autoDeployTrigger` is set to `off`, so updating this shared repository does not redeploy everyone's installation automatically. Trigger a new deploy on Render when you want to update your instance.

## Free-plan limits and billing

Render's free compute tier has idle shutdowns, temporary storage, and monthly usage limits. Its [free-tier documentation](https://render.com/docs/free) describes bandwidth/build charges when a payment method is attached, and suspension when it is not. Choose the free compute tier and review your account's usage/billing settings; the YAML compute plan alone is not an unlimited-bandwidth guarantee.

ClipDock adds conservative hobby-instance limits:

- One active worker; up to six queued/active jobs globally and two per browser session.
- Up to 10 minutes of known source duration and 100 MiB of downloaded media per job.
- A ten-minute job timeout, bounded lookup/download request rates, and expiring files.
- Generated files are removed after one hour when the service next handles jobs/files; Render may erase them sooner on idle shutdown or restart.
- An in-memory 1 GiB file-transfer allowance per calendar month per running instance. It resets when the service restarts and does not count other HTTP responses, so it supplements rather than replaces provider-level billing controls.
- Idle tabs poll less often to reduce request traffic.

The website does not collect account passwords or browser cookies for YouTube, Instagram, or Pinterest. Those services can reject cloud-hosted requests, require sign-in, or change how extraction works. Such failures are shown as download errors; the app does not promise every URL will work.

## Visitor privacy

Each browser receives a signed, HttpOnly, Secure, SameSite cookie. Its request token and download ownership are bound to that session. Visitors can see, download, or cancel only their own jobs. File paths and ownership identifiers are excluded from browser responses. The local shutdown/open-folder controls are disabled in hosted mode.

Media and source links are temporarily processed on the host. No local Windows history, downloaded videos, environment files, or credentials enter the Docker build; `.dockerignore` permits only the required application sources.

## Other container hosts

Run the same Docker image on a host that supports outbound HTTPS and a web port. Set:

- `PORT`: public service port (default `10000`).
- `CLIPDOCK_SESSION_SECRET`: a long random secret supplied through the host's secret manager.
- `CLIPDOCK_PUBLIC_HOST`: exact public hostname when not using Render.
- `CLIPDOCK_DATA_DIR`: a disposable directory for generated files.

Use one server process; the queue is process-local. The entry point is `python -m clipdock.web`, which enables hosted mode and listens on all container interfaces. HTTPS is required for the browser's Secure session cookie. Keep the host's external HTTPS URL in front of the container.
