"""Tests for Insight Raw reader with a user-selected header row."""
import pandas as pd
import pytest

from insight_raw_reader import read_insight_raw_sheet


@pytest.mark.parametrize("header_row", [2, 5, 8, 12])
def test_user_selected_header_row_is_used_and_column_c_cleanup_applies(monkeypatch, header_row):
    raw_sheet = pd.DataFrame([[None] * 4 for _ in range(header_row + 4)], dtype=object)
    raw_sheet.iloc[header_row - 1] = ["Serial Number", "Vendor", "Measurement", "Meta"]
    raw_sheet.iloc[header_row] = ["000123", "V1", "1.25", "keep"]
    raw_sheet.iloc[header_row + 1] = ["000124", "V2", "2.50", None]
    raw_sheet.iloc[header_row + 2] = ["000125", "V3", "3.75", "   "]
    raw_sheet.iloc[header_row + 3] = ["000126", "V4", "4.00", ""]
    seen = {}

    def fake_read_excel(file_path, **kwargs):
        seen.update(kwargs)
        return raw_sheet.copy()

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    result = read_insight_raw_sheet("insight.xlsx", "Raw", header_row)

    assert seen == {"sheet_name": "Raw", "header": None, "dtype": object}
    assert list(result.columns) == ["Serial Number", "Vendor", "Measurement", "Meta"]
    assert result["Serial Number"].tolist() == ["000123", "000124"]
    assert result.index.tolist() == [0, 1]
    assert pd.to_numeric(result["Measurement"], errors="coerce").tolist() == [1.25, 2.5]


def test_insight_raw_rejects_out_of_bounds_and_blank_header(monkeypatch):
    raw_sheet = pd.DataFrame([[None, None, None], [None, None, None], ["A", "B", "C"]], dtype=object)
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: raw_sheet.copy())
    with pytest.raises(ValueError, match="outside the worksheet"):
        read_insight_raw_sheet("bad.xlsx", "Raw", 4)
    with pytest.raises(ValueError, match="header row 2 is empty"):
        read_insight_raw_sheet("bad.xlsx", "Raw", 2)


def test_insight_raw_wraps_excel_loading_errors(monkeypatch):
    def fail_read(*args, **kwargs):
        raise OSError("corrupt workbook")

    monkeypatch.setattr(pd, "read_excel", fail_read)
    with pytest.raises(ValueError, match="Could not read Insight Raw"):
        read_insight_raw_sheet("bad.xlsx", "Raw", 2)
