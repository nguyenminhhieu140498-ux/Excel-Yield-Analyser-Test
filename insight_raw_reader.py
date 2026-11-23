"""Raw-cell reader for Fleet Data - Insight Raw workbooks."""
from __future__ import annotations

import pandas as pd


def read_insight_raw_sheet(file_path, sheet_name):
    """Load cells as objects, use zero-based Excel row index 2 as the header."""
    try:
        raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None, dtype=object)
    except Exception as exc:
        raise ValueError(f"Could not read Insight Raw worksheet '{sheet_name}': {exc}") from exc

    if not isinstance(raw, pd.DataFrame):
        raise ValueError("Insight Raw worksheet did not produce a tabular result.")
    if raw.shape[0] <= 2:
        raise ValueError("Insight Raw worksheet must contain its header at row index 2 and data after it.")
    if raw.shape[1] < 3:
        raise ValueError("Insight Raw worksheet must have at least three columns (A-C).")

    header = raw.iloc[2].tolist()
    if all(pd.isna(value) or not str(value).strip() for value in header):
        raise ValueError("Insight Raw header at row index 2 is empty.")

    column_names = []
    for index, value in enumerate(header):
        if pd.isna(value) or not str(value).strip():
            column_names.append(f"Unnamed: {index}")
        else:
            column_names.append(str(value).strip())
    if len(set(column_names)) != len(column_names):
        raise ValueError("Insight Raw header at row index 2 contains duplicate column names.")

    # Row index 2 is retained as the header; only following rows are filtered.
    data = raw.iloc[3:].copy()
    column_c = data.iloc[:, 2]
    keep = column_c.notna() & column_c.astype(str).str.strip().ne("")
    data = data.loc[keep].copy()
    data.columns = column_names
    return data.reset_index(drop=True)
