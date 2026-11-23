# Excel Yield Analyzer — V1.8 Debug

## Run from source on Python 3.15

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -v
python engineering_chart_analyzer_v18_debug.py
```

## Build the macOS `.app` bundle

Run on macOS with Python 3.15 available as `python3.15`:

```bash
git pull --ff-only
python3.15 build_macos_app.py
open "dist/Excel Yield Analyzer V1.8.app"
```

The generated bundle is written to:

```text
dist/Excel Yield Analyzer V1.8.app
```

A first build may require macOS privacy prompts or Xcode Command Line Tools. The script uses PyInstaller and installs its build dependency without changing application logic.
