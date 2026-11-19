import numpy as np
import pandas as pd
import pytest

from engineering_charts import (
    analyze_measurements, auto_map_units, dashboard_findings, detect_group_column,
    detect_key_column, numeric_columns, render_facet_chart, vendor_summary,
)


def test_auto_map_units_maps_serials_and_vendor_in_input_order():
    units = pd.DataFrame({"SN": ["ab-001", "AB002", "no-match"], "31AA": [0.0, 0.1, -0.2]})
    mapping = pd.DataFrame({"Serial Number": ["AB001", "ab-001", "ab 002"], "Vendor": ["EVW", "wrong duplicate", "FX"], "Family": ["BYD CD", "wrong", "LYT"]})
    result, info = auto_map_units(units, mapping)
    assert result["Vendor"].tolist() == ["EVW", "FX", np.nan] or result["Vendor"].iloc[:2].tolist() == ["EVW", "FX"]
    assert info["matched_rows"] == 2
    assert info["unmatched_rows"] == 1
    assert info["match_rate_pct"] == pytest.approx(200 / 3 * 100)


def test_detect_mapping_columns_and_stats():
    data = pd.DataFrame({"Serial_Number": ["a", "b"], "Vendor": ["EVW", "FX"], "A": [0.0, 0.2]})
    assert detect_key_column(data) == "Serial_Number"
    assert detect_group_column(data) == "Vendor"
    assert numeric_columns(data) == ["A"]
    _, overall = analyze_measurements(data, ["A"], usl=0.1, lsl=-0.2)
    assert overall["Fail"] == 1
    summary = vendor_summary(data, ["A"], "Vendor", usl=0.1, lsl=-0.2)
    assert summary.iloc[0]["Vendor"] == "EVW"
    findings = dashboard_findings(data, ["A"], "Vendor", usl=0.1, lsl=-0.2)
    assert "Top Fail Vendor" in findings["Finding"].tolist()


def test_facet_chart_builds_vendor_columns_and_family_rows():
    data = pd.DataFrame({"Vendor": ["EVW", "FX", "EVW", "FX"], "Family": ["BYD CD", "BYD CD", "LYT", "LYT"], "A": [0.0, .2, -.1, -.4], "B": [.01, .1, -.2, -.5]})
    fig = render_facet_chart(data, ["A", "B"], vendor_column="Vendor", facet_column="Family", usl=.15, lsl=-.3)
    assert len(fig.axes) == 4
