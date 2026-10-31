# Platform setup

The same `clipdock` commands work on Windows, macOS, and Linux. Install the system tools below, then install ClipDock once. FFprobe is included with FFmpeg.

## Windows PowerShell

Using Windows Package Manager:

```powershell
winget install --id astral-sh.uv -e
winget install --id Git.Git -e
winget install --id Gyan.FFmpeg -e
winget install --id OpenJS.NodeJS.LTS -e
```

Open a new PowerShell window, then:

```powershell
uv tool install --python 3.13 git+https://github.com/Golden-alt933/clipdock.git
clipdock doctor
clipdock download "VIDEO_URL"
clipdock serve --open
```

If the installed command is not found, run `uv tool update-shell`, then reopen PowerShell.

## macOS Terminal

With [Homebrew](https://brew.sh/) installed:

```sh
brew install uv git ffmpeg node
uv tool install --python 3.13 git+https://github.com/Golden-alt933/clipdock.git
clipdock doctor
clipdock download "VIDEO_URL"
clipdock serve --open
```

## Linux

On Ubuntu/Debian:

```sh
sudo apt update
sudo apt install git ffmpeg
```

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Node.js 22+](https://nodejs.org/en/download), then:

```sh
uv tool install --python 3.13 git+https://github.com/Golden-alt933/clipdock.git
clipdock doctor
clipdock download "VIDEO_URL"
clipdock serve --open
```

On a headless computer, use `clipdock download` directly; a browser is not required. Check `node --version` because some Linux distributions provide an older version by default.

## Without uv

With Python 3.11+, Git, Node.js 22+, and FFmpeg installed:

```sh
git clone https://github.com/Golden-alt933/clipdock.git
cd clipdock
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
clipdock doctor
clipdock serve --open
```

On Windows, use `py -m venv .venv`, followed by `.venv\Scripts\python.exe -m pip install .` and `.venv\Scripts\clipdock.exe serve --open` instead of the activation commands above. The Windows **Start ClipDock.cmd** launcher is another option; use **Stop ClipDock.cmd** to stop its background service.

## Storage

Direct terminal downloads go to `./Downloads`, or the directory given to `--output`.

Browser-app downloads and `history.json` are stored under:

| System / launcher | Data directory |
| --- | --- |
| Windows installed command | `%LOCALAPPDATA%\ClipDock` |
| Windows double-click launcher | The source folder |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/clipdock` |
| macOS | `~/Library/Application Support/ClipDock` |

Choose another location with `clipdock serve --data-dir PATH`. The service listens only on `127.0.0.1` for local use. Cancelled/interrupted partial files are kept locally; the local app does not delete them automatically.

## Updating

For a uv tool installation, run `uv tool upgrade clipdock`. For source/virtual-environment use, update the checkout and reinstall with `python -m pip install .`; update extraction independently with `python -m pip install --upgrade "yt-dlp[default]"`. The Windows launcher setup also provides **Update downloader.cmd**.
