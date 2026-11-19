# Excel Yield Analyzer Test — v1.3

This test repository preserves the original application layout and adds only requested controls and reporting behavior. The backup repository is separate and unchanged.

## Run with Python 3.15

```bash
python3.15 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python check_syntax.py
python -m pytest -v
python engineering_chart_analyzer.py
```

If `python3.15` is not installed, install Python 3.15 first or substitute the installed `python3` command. The UI provides measurement and mapping workbook selection, exact/optional fuzzy unit mapping, vendor/facet category checklists including blank values, a searchable measurement-column list, chart build/reset, and PNG/PDF/Excel export. PDF is a complete report; PNG contains only the chart; Excel includes the selected chart, mapped data and vendor Pass/Fail commonality summary. A confirmation dialog appears before report exports.

Version label: version 1.3 - designed and developed by Hiro Nguyen.
