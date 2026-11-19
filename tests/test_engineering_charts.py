import numpy as np
import pandas as pd
import pytest

from engineering_charts import (
    analyze_measurements, auto_map_units, dashboard_findings, detect_group_column,
    detect_key_column, numeric_columns, render_facet_chart, vendor_commonality_summary,
)


def test_fuzzy_mapping_and_metadata():
    units = pd.DataFrame({"SN": ["AB-001", "AB00Z", "NOPE"], "M1": [0.0, 0.2, -0.1]})
    mapping = pd.DataFrame({"Serial Number": ["AB001", "AB002"], "Vendor": ["EVW", "FX"], "Family": ["BYD CD", "LYT"]})
    result, info = auto_map_units(units, mapping, fuzzy=True, fuzzy_threshold=80)
    assert result["Vendor"].iloc[0] == "EVW"
    assert info["matched_rows"] >= 2
    assert info["fuzzy_matches"] >= 1


def test_commonality_summary_excludes_blank_groups_and_handles_categoricals():
    data = pd.DataFrame({
        "Vendor": pd.Categorical(["EVW", "EVW", "FX", None]),
        "Family": pd.Categorical(["BYD", "LYT", "BYD", "LYT"]),
        "A": [0.0, .2, -.4, .01],
    })
    summary = vendor_commonality_summary(data, ["A"], "Vendor", "Family", usl=.1, lsl=-.3)
    assert "(blank)" not in summary["Vendor"].tolist()
    assert set(summary.columns) >= {"Vendor", "Breakdown", "Fail N", "Pass N", "Fail % of Total", "Pass % of Total"}
    evw_byd = summary[(summary.Vendor == "EVW") & (summary.Breakdown == "BYD")].iloc[0]
    assert evw_byd["Pass N"] == 1
    assert evw_byd["Fail N"] == 0


def test_vendor_and_facet_filter_chart_handles_blank_categorical_values():
    data = pd.DataFrame({"Vendor": pd.Categorical(["EVW", "FX", None, "FX"]),
                         "Family": pd.Categorical(["BYD", "BYD", "LYT", None]),
                         "A": [0.0, .2, -.1, -.4], "B": [.01, .1, -.2, -.5]})
    fig = render_facet_chart(data, ["A", "B"], vendor_column="Vendor", facet_column="Family",
                             usl=.15, lsl=-.3, vendor_values=["EVW", "FX", "(blank)"],
                             facet_values=["BYD", "LYT", "(blank)"])
    assert len(fig.axes) == 9


def test_basic_detection_and_stats():
    data = pd.DataFrame({"Serial_Number": ["a", "b"], "Vendor": ["EVW", "FX"], "A": [0.0, 0.2]})
    assert detect_key_column(data) == "Serial_Number"
    assert detect_group_column(data) == "Vendor"
    assert numeric_columns(data) == ["A"]
    _, overall = analyze_measurements(data, ["A"], usl=.1, lsl=-.2)
    assert overall["Fail"] == 1
    assert overall["Yield %"] == pytest.approx(50)
    assert "Top Fail Vendor" in dashboard_findings(data, ["A"], "Vendor", usl=.1, lsl=-.2)["Finding"].tolist()
