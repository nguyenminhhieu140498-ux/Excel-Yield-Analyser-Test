"""Raw-cell reader for Fleet Data - Insight Raw workbooks."""
from __future__ import annotations

import pandas as pd


def read_insight_raw_sheet(file_path, sheet_name, header_row):
    """Load cells as objects and use the user-selected 1-based Excel header row."""
    try:
        raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, dtype=object)
    except Exception as exc:
        raise ValueError(f"Could not read Insight Raw worksheet '{sheet_name}': {exc}") from exc

    if not isinstance(raw, pd.DataFrame):
        raise ValueError("Insight Raw worksheet did not produce a tabular result.")
    try:
        row_number = int(header_row)
    except (TypeError, ValueError) as exc:
        raise ValueError("Header row must be a whole-number Excel row index.") from exc
    if row_number < 1 or row_number > len(raw.index):
        raise ValueError(f"Header row {row_number} is outside the worksheet (1–{len(raw.index)}).")
    if raw.shape[1] < 3:
        raise ValueError("Insight Raw worksheet must have at least three columns (A-C).")

    header_index = row_number - 1
    header = raw.iloc[header_index].tolist()
    if all(pd.isna(value) or not str(value).strip() for value in header):
        raise ValueError(f"Insight Raw header row {row_number} is empty.")

    column_names = []
    for index, value in enumerate(header):
        if pd.isna(value) or not str(value).strip():
            column_names.append(f"Unnamed: {index}")
        else:
            column_names.append(str(value).strip())
    if len(set(column_names)) != len(column_names):
        raise ValueError(f"Insight Raw header row {row_number} contains duplicate column names.")

    # Keep the selected row as column names; only subsequent data rows are cleaned.
    data = raw.iloc[header_index + 1:].copy()
    column_c = data.iloc[:, 2]
    keep = column_c.notna() & column_c.astype(str).str.strip().ne("")
    data = data.loc[keep].copy()
    data.columns = column_names
    return data.reset_index(drop=True)
