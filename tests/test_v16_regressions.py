import pandas as pd
import pytest
from engineering_charts import validate_spec_ranges, vendor_commonality_summary


def test_spec_ranges_return_axis_order_independent_of_csv_row_order():
    axis = ["11AA", "11AB", "11AC", "11BA", "11BB", "11BC"]
    rows = [
        {"Start Point": "11BA", "End Point": "11BC", "USL": ".13", "Target": "0", "LSL": "-.18"},
        {"Start Point": "11AA", "End Point": "11AC", "USL": ".09", "Target": "0", "LSL": "-.14"},
    ]
    result = validate_spec_ranges(rows, axis)
    assert [row["Start Point"] for row in result] == ["11AA", "11BA"]


def test_commonality_retains_generic_legacy_column_names():
    data = pd.DataFrame({"Vendor": ["EVW", "EVW"], "Family": ["BYD", "LYT"], "A": [0, .2]})
    summary = vendor_commonality_summary(data, ["A"], "Vendor", "Family", usl=.1, lsl=-.3)
    assert set(summary.columns) >= {"Vendor", "Breakdown", "Fail N", "Pass N", "Fail % of Total", "Pass % of Total"}
