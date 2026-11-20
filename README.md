## v1.4 DEBUG fixes

The existing interface and behavior are preserved. For this DEBUG build, use the patched launcher below so the control pane is scrollable and spec ranges are validated by X-axis positions rather than CSV row order.

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -v
python engineering_chart_analyzer_v14_debug.py
```

In Multi Spec mode, the spec table supports direct cell editing (double-click a cell or select it and type). CSV rows may be in any order; each Start/End range is placed using the selected measurement X-axis. True overlaps still produce an error. CSV import also detects comma/semicolon/tab delimiters and decimal commas for semicolon-separated Excel CSV files.
