"""Regression tests for raw Insight Raw import and defensive validation."""
import pandas as pd
import pytest

from insight_raw_reader import read_insight_raw_sheet


def test_insight_raw_reads_raw_objects_uses_row_index_2_and_filters_only_data(monkeypatch):
    raw_sheet = pd.DataFrame([
        ["preamble", "preamble", "preamble"],
        ["secondary", "secondary", "secondary"],
        ["Serial Number", "Vendor", "Measurement", "Count"],
        ["000123", "V1", "1.25", "7"],
        ["000124", "V2", "2.50", None],
        ["000125", "V3", "3.75", "   "],
        ["000126", "V4", "4.00", ""],
    ], dtype=object)
    seen = {}

    def fake_read_excel(file_path, **kwargs):
        seen["file_path"] = file_path
        seen.update(kwargs)
        return raw_sheet.copy()

    monkeypatch.setattr(pd, "read_excel", fake_read_excel)
    result = read_insight_raw_sheet("insight.xlsx", "Raw")

    assert seen == {
        "file_path": "insight.xlsx", "sheet_name": "Raw", "header": None, "dtype": object
    }
    assert list(result.columns) == ["Serial Number", "Vendor", "Measurement", "Count"]
    assert result["Serial Number"].tolist() == ["000123", "000124"]
    assert result.index.tolist() == [0, 1]
    assert all(isinstance(value, str) for value in result["Measurement"])
    converted_measurements = pd.to_numeric(result["Measurement"], errors="coerce")
    assert converted_measurements.tolist() == [1.25, 2.5]


def test_insight_raw_rejects_malformed_sheet_without_dataframe_inference(monkeypatch):
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: pd.DataFrame([["too", "short"]]))
    with pytest.raises(ValueError, match="at least three columns"):
        read_insight_raw_sheet("bad.xlsx", "Raw")


def test_insight_raw_wraps_excel_loading_errors(monkeypatch):
    def fail_read(*args, **kwargs):
        raise OSError("corrupt workbook")

    monkeypatch.setattr(pd, "read_excel", fail_read)
    with pytest.raises(ValueError, match="Could not read Insight Raw"):
        read_insight_raw_sheet("bad.xlsx", "Raw")
