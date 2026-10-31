# Changelog

## 0.3.0 — 2026-11-01

- Complete hosted website mode with bundled Python, Node.js, FFmpeg, and browser interface.
- Render free-plan Blueprint and Docker deployment, with a health endpoint.
- Separate signed browser sessions, private job lists/files/cancellation, and disabled local-machine controls online.
- Hosted file expiry, media size/duration limits, job timeout, request limits, and a supplementary transfer allowance.
- Website copy and Save file controls for visitors who have no local installation.
- Hosted privacy/limit tests and Docker build/smoke checks in CI.

## 0.2.0 — 2026-11-01

- MP3 bitrate selection: 128, 192, 256, or 320 kbps; new downloads default to 320 kbps.
- Best source audio output preserves the available native audio codec instead of converting to MP3.
- Added `--audio-bitrate` and `--format audio` to the CLI, with matching browser controls and history labels.
- MP3 filenames include bitrate to avoid reusing an older lower-bitrate CLI download.
- Fixed Instagram portrait Reels failing with "Requested format is not available": quality selection now uses the shorter video dimension and falls back when a preferred resolution is unavailable.
- Added regression tests for portrait selection, bitrate handling, source audio, and audio file delivery.
- Added explicit PowerShell/macOS CLI setup examples and macOS CI coverage.

## 0.1.0 — 2026-11-01

- Initial public release with a local browser interface.
- Public YouTube, Instagram, and Pinterest video extraction through yt-dlp.
- MP4/MP3, quality selection, two concurrent downloads, history, and cancellation.
- Cross-platform `clipdock serve`, `download`, and `doctor` commands.
- Installable Python package with bundled browser assets.
- Windows launch/stop/update shortcuts and Linux/macOS setup instructions.
- Offline tests and a Windows/Linux GitHub Actions matrix.
