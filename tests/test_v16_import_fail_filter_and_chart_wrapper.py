"""Regression tests for import templates, chart rendering and Fail SN filtering."""
import pandas as pd
from matplotlib.figure import Figure

import engineering_chart_analyzer_v16_compact as compact


def test_original_renderer_fallback_does_not_recurse():
    data = pd.DataFrame({"M1": [1.0, 2.0], "M2": [2.0, 3.0], "Vendor": ["A", "B"]})
    for chart_type in (
        "Vendor Comparison Chart", "Average Trend Chart", "Histogram",
        "Scatter Plot", "Control/SPC Chart",
    ):
        columns = ["M1"] if chart_type in {"Histogram", "Control/SPC Chart"} else ["M1", "M2"]
        figure = Figure()
        result = compact._render_chart_with_box_facets(
            data, columns, chart_type, group_column="Vendor", figure=figure
        )
        assert result is figure
        assert figure.axes


def test_insight_raw_reader_uses_second_excel_row_and_drops_blank_column_c(monkeypatch):
    observed = {}
    frame = pd.DataFrame({"SN": ["A", "B", "C"], "Vendor": ["V1", "V2", "V3"],
                          "Measurement": [1.2, None, "   "]})
    monkeypatch.setattr(compact.pd, "read_excel",
                        lambda *args, **kwargs: (observed.update(kwargs) or frame.copy()))
    cleaned = compact._read_insight_raw_sheet("fleet.xlsx", "Raw")
    assert observed["header"] == 1
    assert cleaned["SN"].tolist() == ["A"]


def test_fail_sn_filter_keeps_all_measurements_for_selected_sn_only():
    data = pd.DataFrame({"SN": ["A", "A", "B"], "Position": ["M1", "M2", "M1"],
                         "M1": [1.0, 2.0, 3.0], "M2": [4.0, 5.0, 6.0]})
    filtered = compact._filter_by_selected_fail_sn(data, "SN", ["A"])
    assert filtered["Position"].tolist() == ["M1", "M2"]
    assert compact._filter_by_selected_fail_sn(data, "SN", []).empty


def test_target_nominal_is_annotated_in_source_figure():
    figure = Figure()
    axis = figure.add_subplot(111)
    compact.chart_logic._draw_specs(axis, ["M1", "M2"], [{
        "start_index": 0, "end_index": 1, "USL": None, "LSL": None, "Target": 1.5,
    }])
    assert any("Target/Nominal: 1.5" in text.get_text() for text in axis.texts)


def test_box_plot_facets_retain_vendor_breakdown_and_target_label():
    data = pd.DataFrame({"Vendor": ["A", "A", "B", "B"], "Breakdown": ["X", "Y", "X", "Y"],
                         "M1": [1.0, 2.0, 3.0, 4.0], "M2": [1.5, 2.5, 3.5, 4.5]})
    fig = compact.render_boxplot_facets(
        data, ["M1", "M2"], vendor_column="Vendor", facet_column="Breakdown",
        vendor_values=["A", "B"], facet_values=["X", "Y"], target=2.0, figure=Figure(),
    )
    assert len(fig.axes) == 4
    assert all([tick.get_text() for tick in axis.get_xticklabels()] == ["M1"] or
               [tick.get_text() for tick in axis.get_xticklabels()] == ["M1", "M2"]
               for axis in fig.axes)
    assert all(any("Target/Nominal: 2" in text.get_text() for text in axis.texts) for axis in fig.axes)


def test_boxplot_label_keyword_matches_installed_matplotlib():
    import inspect

    parameters = inspect.signature(Figure().add_subplot(111).boxplot).parameters
    keyword = "tick_labels" if "tick_labels" in parameters else "labels"
    assert keyword in {"labels", "tick_labels"}
    fig = compact.render_boxplot_facets(
        pd.DataFrame({"Vendor": ["V", "V"], "M": [1.0, 2.0]}),
        ["M"], vendor_column="Vendor", vendor_values=["V"], figure=Figure(),
    )
    assert fig.axes
    assert [tick.get_text() for tick in fig.axes[0].get_xticklabels()] == ["M"]
