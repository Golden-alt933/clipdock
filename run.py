"""Compatibility launcher: keep the existing Windows downloads in this folder."""
from pathlib import Path
from clipdock.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["serve", "--data-dir", str(Path(__file__).resolve().parent)]))
