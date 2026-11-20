# Excel Yield Analyzer Test — v1.4

Original backup repository remains unchanged. This test repository includes unit/vendor mapping, charts, summary, guide tooling, and the requested workflow updates.

## Run with Python 3.15

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -v
python engineering_chart_analyzer.py
```

The measurement import keeps ordinary row-1 headers. Raw sheets with unnamed columns locate a header within the first 10 rows by the first non-empty cell in column C. Select multiple sheets to open separate application windows.

Duplicate unit handling defaults to **Keep last + NG**; alternate choices are Keep last and Keep first. You can select multiple chart types and use the preview arrows to page between them. The vendor summary labels the vendor and breakdown values; the separate Fail SN list shows SN, failed measurement position, and value.

Single Spec remains the default. Multi Spec supports editable/importable/exportable CSV ranges with X-axis validation and non-overlap checks. PDF and Excel exports offer selectable report content; PNG saves only the current chart.

