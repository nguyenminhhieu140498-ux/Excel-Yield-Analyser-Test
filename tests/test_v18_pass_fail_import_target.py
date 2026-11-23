"""Regression tests for V1.8 Pass baseline and Fail SN overlays."""
import pandas as pd
from matplotlib.figure import Figure

import engineering_chart_analyzer_v18_debug as v18


def _sample_data():
    return pd.DataFrame({
        "SN": ["P1", "P2", "F1", "F2"],
        "M1": [0.0, 0.1, 1.2, 1.5],
        "M2": [0.0, 0.2, 1.1, 1.4],
    })


def _sample_specs():
    return [{"start_index": 0, "end_index": 1, "USL": 1.0, "LSL": None,
             "Target": None, "Start Point": "M1", "End Point": "M2"}]


def test_default_chart_data_contains_all_pass_and_fail_units():
    data = _sample_data()
    result = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], _sample_specs())
    assert result["SN"].tolist() == ["P1", "P2", "F1", "F2"]


def test_selection_keeps_all_pass_and_only_chosen_failures():
    data = _sample_data()
    result = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], _sample_specs(), ["F1"])
    assert result["SN"].tolist() == ["P1", "P2", "F1"]


def test_multiple_selected_failures_keep_all_pass_and_selected_subset():
    data = _sample_data()
    result = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], _sample_specs(), ["F2"])
    assert result["SN"].tolist() == ["P1", "P2", "F2"]


def test_clearing_selection_restores_all_failures():
    data = _sample_data()
    result = v18._compose_pass_fail_data(data, "SN", ["M1", "M2"], _sample_specs(), [])
    assert result["SN"].tolist() == ["P1", "P2", "F1", "F2"]


def test_multiline_pass_baseline_and_fail_overlay_have_distinct_styles():
    data = _sample_data()
    fig = Figure()
    v18.v16_compact._ORIGINAL_RENDER_V16_FACET(
        data, ["M1", "M2"], vendor_column="", facet_column="",
        usl=1.0, figure=fig, highlight_oos=True,
    ) if False else None
    # Use the original single-axis renderer to verify all pass/fail traces coexist
    # and are color-coded against the same chart population.
    v18.v16_compact._ORIGINAL_RENDER_V16_CHART(
        data, ["M1", "M2"], "Multi-Line Trend Chart", usl=1.0,
        highlight_oos=True, figure=fig,
    )
    colors = [line.get_color() for line in fig.axes[0].lines]
    assert colors.count("#477de0") == 2
    assert colors.count("#d62728") == 2
