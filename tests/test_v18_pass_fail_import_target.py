"""Regression tests for V1.8 full filtered Pass/Fail composition."""
import pandas as pd
from matplotlib.figure import Figure

import engineering_chart_analyzer_v18_debug as v18


def _sample_data(pass_count=2, fail_count=2):
    sns = [f"P{i + 1}" for i in range(pass_count)] + [f"F{i + 1}" for i in range(fail_count)]
    values = [0.1 + i * 0.01 for i in range(pass_count)] + [1.2 + i * 0.1 for i in range(fail_count)]
    return pd.DataFrame({"SN": sns, "M1": values, "M2": values})


def _sample_specs():
    return [{"start_index": 0, "end_index": 1, "USL": 1.0, "LSL": None,
             "Target": None, "Start Point": "M1", "End Point": "M2"}]


def test_default_view_contains_every_pass_and_fail_unit():
    data = _sample_data()
    result = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], _sample_specs())
    assert len(result) == 4
    assert result["SN"].tolist() == ["P1", "P2", "F1", "F2"]


def test_one_selected_fail_keeps_all_pass_rows_and_hides_other_fails():
    data = _sample_data()
    result = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], _sample_specs(), ["F1"])
    assert result["SN"].tolist() == ["P1", "P2", "F1"]


def test_multiple_selected_fails_keep_all_pass_rows():
    data = _sample_data(fail_count=3)
    result = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], _sample_specs(), ["F1", "F3"])
    assert result["SN"].tolist() == ["P1", "P2", "F1", "F3"]


def test_cleared_selection_restores_default_all_units_view():
    data = _sample_data()
    result = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], _sample_specs(), [])
    assert result["SN"].tolist() == ["P1", "P2", "F1", "F2"]


def test_pass_159_fail_1_composition_matches_commonality_counts():
    data = _sample_data(pass_count=159, fail_count=1)
    specs = _sample_specs()
    failing = v18._failed_sn_keys_from_data(data, "SN", ["M1", "M2"], specs)
    pass_data = data.loc[~data["SN"].map(v18._norm_sn).isin(failing)]
    fail_data = data.loc[data["SN"].map(v18._norm_sn).isin(failing)]
    assert len(pass_data) == 159
    assert len(fail_data) == 1
    selected = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], specs, [fail_data["SN"].iloc[0]])
    assert len(selected) == 160
    assert len(selected.loc[selected["SN"].str.startswith("P")]) == 159


def test_multiline_renderer_plots_both_baseline_and_fail_rows():
    data = _sample_data()
    figure = Figure()
    v18.v16_compact._ORIGINAL_RENDER_V16_CHART(
        data, ["M1", "M2"], "Multi-Line Trend Chart", usl=1.0,
        highlight_oos=True, figure=figure,
    )
    lines = figure.axes[0].lines
    assert len(lines) == len(data)
    assert sum(line.get_color() == "#477de0" for line in lines) == 2
    assert sum(line.get_color() == "#d62728" for line in lines) == 2
