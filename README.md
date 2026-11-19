# Excel Yield Analyzer — test repository

This private repository is a test workspace for automatic serial/unit mapping and vendor breakdown charts. The original `Excel-Yield-Analyser` repository remains the backup and is not modified by these changes.

## Run

Python 3.12 is recommended on macOS. From this repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -v
python engineering_chart_analyzer.py
```

In the chart window:

1. Open the measurement workbook and choose its worksheet.
2. Open the unit mapping workbook (serial number → Vendor / Build Matrix / Product metadata).
3. Review the auto-detected serial/unit key columns, then click **Auto-map units before charting**. Matching normalizes case, whitespace, and punctuation; duplicate mapping keys keep their first row. The status shows matched/unmatched units.
4. Select vendor for columns, and optional Product/Build Matrix/Station facet for rows, then select numeric measurement points. Enter USL/LSL/target if needed and build the chart.
5. Save as PNG/PDF or export Excel. Export includes the chart, statistics, vendor summary, and a `MappedUnits` worksheet.

The offset-style multi-line view draws one line per unit, failing units in red and passing units in translucent blue, with spec bands/lines repeated in each vendor/facet panel. The display samples a bounded number of units per panel; calculations use all rows. It is not a validated SPC/W.E. rules package; capability values should be reviewed by a quality engineer.
