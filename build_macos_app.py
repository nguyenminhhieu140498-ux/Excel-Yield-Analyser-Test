"""Build a macOS .app bundle for the Engineering Chart Analyzer V1.8 launcher.

Run from the repository root on macOS:
    python3.15 build_macos_app.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "Excel Yield Analyzer V1.8"
ENTRYPOINT = "engineering_chart_analyzer_v18_debug.py"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> int:
    if sys.platform != "darwin":
        print("This build script can only create a macOS .app bundle.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parent
    entrypoint = root / ENTRYPOINT
    if not entrypoint.exists():
        print(f"Missing entrypoint: {entrypoint}", file=sys.stderr)
        return 2

    python = shutil.which("python3.15")
    if python is None:
        print("Python 3.15 was not found. Install it first and ensure python3.15 is on PATH.", file=sys.stderr)
        return 2

    run([python, "-m", "pip", "install", "--upgrade", "pip"])
    run([python, "-m", "pip", "install", "pyinstaller", "-r", str(root / "requirements.txt")])

    command = [
        python,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--osx-bundle-identifier",
        "com.hironguyen.excelyieldanalyzerv18",
        "--collect-submodules",
        "matplotlib",
        "--collect-submodules",
        "PySide6",
        "--add-data",
        f"{root / 'insight_raw_reader.py'}:.",
        str(entrypoint),
    ]
    run(command)

    app = root / "dist" / f"{APP_NAME}.app"
    if not app.exists():
        print("PyInstaller completed, but the expected .app bundle was not found.", file=sys.stderr)
        return 1

    print(f"Created: {app}")
    print("Open it with:")
    print(f"open \"{app}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
