import pytest
from engineering_charts import validate_spec_ranges


def test_spec_ranges_accept_csv_rows_in_any_order_and_return_axis_order():
    axis = ["11AA", "11AB", "11AC", "11BA", "11BB", "11BC"]
    rows = [
        {"Start Point": "11BA", "End Point": "11BC", "USL": ".13", "Target": "0", "LSL": "-.18"},
        {"Start Point": "11AA", "End Point": "11AC", "USL": ".09", "Target": "0", "LSL": "-.14"},
    ]
    result = validate_spec_ranges(rows, axis)
    assert [item["Start Point"] for item in result] == ["11AA", "11BA"]
    assert [(item["start_index"], item["end_index"]) for item in result] == [(0, 2), (3, 5)]


def test_spec_ranges_still_reject_actual_axis_overlap_independent_of_row_order():
    axis = ["11AA", "11AB", "11AC", "11AD"]
    rows = [
        {"Start Point": "11AC", "End Point": "11AD", "USL": 1, "LSL": 0},
        {"Start Point": "11AA", "End Point": "11AC", "USL": 2, "LSL": 0},
    ]
    with pytest.raises(ValueError, match="cannot overlap"):
        validate_spec_ranges(rows, axis)
