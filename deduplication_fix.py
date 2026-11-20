"""Robust duplicate-unit handling for the v1.4 DEBUG launcher.

The failure mask is positional and is always paired with the original rows
before filtering; blank unit keys are retained as independent rows.
"""
from __future__ import annotations

import re
import numpy as np
import pandas as pd


def _normalize_unit_key(value) -> str:
    if pd.isna(value):
        return ""
    text = re.sub(r"\.0+$", "", str(value).strip().upper())
    return re.sub(r"[^A-Z0-9]", "", text)


def deduplicate_units(data: pd.DataFrame, key_column: str, mode: str = "Keep last + NG", fail_mask=None) -> pd.DataFrame:
    """Deduplicate SN rows without applying a full-length mask to filtered rows.

    Keep last + NG keeps the last failing measurement for a repeated SN when
    any retest failed; otherwise it keeps that SN's last measurement. Empty SN
    values are not duplicates and are all retained.
    """
    if not key_column or key_column not in data.columns:
        return data.copy()
    if mode not in {"Keep first", "Keep last", "Keep last + NG"}:
        raise ValueError(f"Unsupported duplicate handling mode: {mode}")

    row_count = len(data)
    if fail_mask is None:
        failures = np.zeros(row_count, dtype=bool)
    elif isinstance(fail_mask, pd.Series):
        if len(fail_mask) != row_count:
            raise ValueError(f"Fail mask has {len(fail_mask)} rows but input data has {row_count} rows.")
        failures = fail_mask.to_numpy(dtype=bool)
    else:
        failures = np.asarray(fail_mask, dtype=bool)
        if failures.ndim != 1 or len(failures) != row_count:
            raise ValueError(f"Fail mask must contain exactly {row_count} values; got {len(failures)}.")

    normalized = data[key_column].map(_normalize_unit_key).to_numpy()
    grouped_positions: dict[str, list[int]] = {}
    blank_positions = []
    for position, key in enumerate(normalized):
        if key:
            grouped_positions.setdefault(key, []).append(position)
        else:
            blank_positions.append(position)

    keep_positions = list(blank_positions)
    for positions in grouped_positions.values():
        if mode == "Keep first":
            keep_positions.append(positions[0])
        elif mode == "Keep last":
            keep_positions.append(positions[-1])
        else:
            failed_positions = [position for position in positions if failures[position]]
            keep_positions.append(failed_positions[-1] if failed_positions else positions[-1])

    return data.iloc[sorted(keep_positions)].copy().reset_index(drop=True)
