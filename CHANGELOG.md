# Changelog

## 0.8.0 — 2026-11-01

- Slight independent swaying of the existing cloud areas while the statue stays still.
- Marble eyes track the cursor across the whole page using photo-textured, feathered eye layers.
- Eye and cloud layers stay aligned with the background when resizing or changing device orientation.
- Eye tracking shares the existing cursor animation loop and respects pause, reduced-motion, hidden tabs, and touch input.

## 0.7.0 — 2026-11-01

- Dark graphite camera with layered lens optics, mechanical keycaps with RGB lighting, and a dark editing timeline with colored tracks.
- Wider floating paths and smooth cursor-driven tilt, nearby-cursor repulsion, and lighting response.
- Cursor effects stop when settled and respect the motion toggle, reduced-motion settings, hidden tabs, and touch input.
- Updated README preview for the darker RGB background objects.

## 0.6.0 — 2026-11-01

- Full-screen Apollo sky background with slow camera movement and floating camera, keyboard, and timeline illustrations.
- Light frosted-glass panels and pill controls, with the background visible throughout the workspace.
- Self-hosted Manrope variable font with its bundled Open Font License.
- Background-motion pause/resume control, saved preference, reduced-motion support, and animation pausing in hidden tabs.
- Updated README preview and packaged assets for browser and CLI installs.

## 0.5.0 — 2026-11-01

- Sky-blue and cloud-white accents over deep navy, with bundled Apollo-inspired artwork.
- Decorative editing monitor, video tracks, audio waveform, and animated playhead.
- Glass-style pill URL field, rounded controls, and refined focus and hover feedback.
- Scroll-triggered section reveals and preview transitions, with reduced-motion and unsupported-browser fallbacks.
- Compressed local artwork ships with both the website and installed CLI package; no external image service is needed at runtime.

## 0.4.0 — 2026-11-01

- Dark creator workspace with warm orange accents, editorial typography, and responsive desktop/mobile layouts.
- Search saved media by title, platform, or output format, alongside the existing download filters.
- Paste-link button with a keyboard fallback when clipboard access is unavailable.
- Clear source-reading and connection states, keyboard focus styles, and reduced-motion support.
- Updated the README screenshot to match the new interface.
- Removed the three-step onboarding section and its sidebar shortcut for a more compact workspace.

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
