# Excel Yield Analyzer — V1.8 Debug

Excel Yield Analyzer analyzes measurement workbooks, compares measurement distributions, applies specification limits, and generates chart/report exports on macOS or Python 3.15.

## Latest V1.8 workflow

1. Open **Fleet Data** with `Open measurements…`.
2. Select **Fleet Data - PE Format** or **Fleet Data - Insight Raw**.
3. Select one or more worksheets.
4. For Insight Raw, enter the Excel row containing the real column headers.
5. Review the recognized unit key, vendor field, breakdown field, and numeric measurement columns.
6. Configure a single specification or add multiple specification ranges.
7. Build the charts and use the Fail SN table for focused analysis.

## Measurement import

### Fleet Data - PE Format

The existing PE-format parser and column-recognition workflow are preserved. The application reads the worksheet using the established PE detection algorithm.

### Fleet Data - Insight Raw

Insight Raw is read without automatic dataframe dtype inference. The application prompts for the **Excel row number** containing the column headers.

- Example: enter `2`, `5`, `8`, or `12`.
- The selected row becomes the dataframe header.
- Data begins on the next row.
- Rows with a blank, empty, whitespace-only, or NaN column C are removed.
- The cleaned dataframe is reset with `reset_index(drop=True)`.
- Measurement values are converted to numeric only when chart/statistical functions require it.

## Pass/Fail chart behavior

With **Show Fail / out-of-spec units** enabled:

- Default: all Pass Units remain visible and no Fail Units are shown.
- Select one Fail SN: all Pass Units remain visible; only that Fail SN is added/retained.
- Select multiple Fail SNs: all Pass Units remain visible; only selected Fail SNs are shown.
- Clear the Fail SN selection: return to Pass Units only.

The chart uses Pass Units as the stable baseline population. Fail SNs are highlighted as foreground overlay units.

## Main controls

- **Unit/serial key:** identifies each unit in the Fail SN table and deduplication logic.
- **Vendor field:** selects grouping/vendor values and chart facets.
- **Breakdown field:** selects breakdown rows or units.
- **Vendor values / Breakdown values:** filter the chart population.
- **Numeric measurement columns:** select the measurement points to plot.
- **Single Spec:** enter USL, Target/Nominal, and LSL.
- **Multi Spec:** import/add specification ranges between named Start Point and End Point measurement columns.
- **Fail SN table:** select one or multiple failing serial numbers.
- **Build chart:** regenerates charts and summary tables.
- **Save PNG / Save PDF / Export Excel:** exports the current chart or report contents.

## Vendor Pass/Fail Commonality

The Vendor Pass/Fail Commonality table remains visible and retains its existing Pass N, Fail N, percentages, and total calculations. It provides a consistent count check with the chart population.

## Target/Nominal

A green line represents the Target/Nominal value. Only the numeric Target/Nominal value is printed beside the line; the chart does not add the text `Target/Nominal:`.

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

```bash
python3.15 build_macos_app.py
open "dist/Excel Yield Analyzer V1.8.app"
```

The generated bundle is written to:

```text
dist/Excel Yield Analyzer V1.8.app
```

## Generate this User Guide as a PowerPoint file

```bash
python3.15 generate_user_guide_ppt.py
open "Excel_Yield_Analyzer_V1.8_User_Guide.pptx"
```

The generator creates `Excel_Yield_Analyzer_V1.8_User_Guide.pptx` in the repository root.
