# Contributing

Use Python 3.11+ and install the project in a virtual environment:

```bash
python -m pip install -e ".[test]"
python -m unittest discover -s tests -v
```

Keep changes focused, describe the resulting behavior, and include how you verified it. Add tests for URL validation, queue/cancellation behavior, filesystem handling, or CLI behavior when changing them. Avoid tests that require real accounts or live social-media services.

Never commit downloaded videos, browser cookies, access tokens, history files, local logs, virtual environments, or personally identifying file paths. For a bug report, include your OS, Python version, `clipdock doctor` output with personal paths removed, and a public reproducible link only if you have permission to share it.

## Source layout

- `clipdock/cli.py`: commands, diagnostics, terminal download output.
- `clipdock/app.py`: local API, queue, history, file delivery, cancellation.
- `clipdock/worker.py`: isolated extraction/download and FFmpeg processing.
- `clipdock/urls.py`: allowed URL normalization.
- `clipdock/paths.py`: platform-specific writable storage.
- `clipdock/hosting.py` and `clipdock/web.py`: hosted sessions, quotas, and container entry point.
- `clipdock/static/`: browser interface, no build step.
- `tests/`: offline tests; GitHub Actions runs them on Linux, Windows, and macOS.
- `run.py` and the `.cmd`/`.ps1` files: Windows double-click compatibility.
- `Dockerfile`, `render.yaml`, and `docs/HOSTING.md`: full hosted website deployment.

Start with `python -m clipdock serve --data-dir ./dev-data`. Do not put private videos or history into screenshots. Run live platform checks manually when appropriate and report them separately from the offline suite.
