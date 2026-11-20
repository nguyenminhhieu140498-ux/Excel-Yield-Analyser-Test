# Excel Yield Analyzer — v1.6

The v1.6 launcher keeps the existing workflow while using a compact chart toolbar. Zoom is available from the toolbar's magnifier icons and with the mouse wheel/trackpad on the chart. Hold **Control** while scrolling over a table to zoom its text; a trackpad pinch also zooms table text. Normal table scrolling is unchanged. The version label displays `v1.6` without the DEBUG suffix.

## Run with Python 3.15

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -v
python engineering_chart_analyzer_v16_compact.py
```
