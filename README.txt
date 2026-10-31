CLIPDOCK

Full documentation: README.md
https://github.com/Golden-alt933/clipdock

WINDOWS
Double-click Start ClipDock.cmd to set up the app and open its local interface.
Double-click Stop ClipDock.cmd to stop the background service.
The Windows launcher keeps Downloads and history.json beside this file.
Python 3.11+, FFmpeg/FFprobe, and Node.js 22+ must be available on PATH.

LINUX / MACOS / TERMINAL
Install the package in a virtual environment, then use:
  clipdock doctor
  clipdock serve --open
  clipdock download "VIDEO_URL" --quality 1080
  clipdock download "VIDEO_URL" --format mp3

Or, with uv installed:
  uvx --from git+https://github.com/Golden-alt933/clipdock.git clipdock serve --open

This is a local web app. GitHub shares the source; it does not host a running
public downloader. See README.md for installation, storage, privacy, and limits.
