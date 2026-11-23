# Excel Yield Analyzer — v1.8 Debug

V1.8 debug launcher retains the existing compact interface and import templates, keeps passing units on every chart, and adds only selected failing SN units to the chart. The Fail SN List occupies the former commonality-panel space. Target/Nominal keeps its green line and displays only its numeric value.

## Run with Python 3.15

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -v
python engineering_chart_analyzer_v18_debug.py
```
