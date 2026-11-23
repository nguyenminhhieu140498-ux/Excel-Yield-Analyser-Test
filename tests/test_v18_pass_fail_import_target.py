"""V1.8 regression tests for pass/fail composition and restored commonality table."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from matplotlib.figure import Figure
import pytest
from PySide6.QtWidgets import QApplication

import engineering_chart_analyzer_v16_compact as compact
import engineering_chart_analyzer_v18_debug as v18


def test_selected_fail_sn_composition_retains_all_pass_rows():
    data = pd.DataFrame({"SN": ["P1", "P2", "F1", "F2"],
                         "M1": [0.0, 0.1, 1.2, 1.5], "M2": [0.0, 0.2, 1.1, 1.4]})
    specs = [{"start_index": 0, "end_index": 1, "USL": 1.0, "LSL": None,
              "Target": 0.5, "Start Point": "M1", "End Point": "M2"}]
    fail_keys = v18._failed_sn_keys_from_data(data, "SN", ["M1", "M2"], specs)
    passing = data.loc[~data["SN"].map(v18._norm_sn).isin(fail_keys)]
    selected_fail = data.loc[data["SN"].map(v18._norm_sn).eq(v18._norm_sn("F1"))]
    composed = pd.concat([passing, selected_fail]).drop_duplicates()
    assert composed["SN"].tolist() == ["P1", "P2", "F1"]


def test_target_label_is_numeric_only_and_aligned_to_target_y_value():
    axis = Figure().add_subplot(111)
    v18._draw_specs_numeric_target(axis, ["M1", "M2"], [{
        "start_index": 0, "end_index": 1, "USL": None, "LSL": None, "Target": -0.1,
    }])
    labels = axis.texts
    assert len(labels) == 1
    assert labels[0].get_text() == "-0.1"
    assert labels[0].get_color() == "#20a45b"
    assert labels[0].get_position()[1] == pytest.approx(-0.1)


def test_boxplot_uses_matplotlib_supported_label_keyword():
    data = pd.DataFrame({"Vendor": ["A", "A"], "M1": [1.0, 2.0]})
    figure = compact.render_boxplot_facets(data, ["M1"], vendor_column="Vendor", figure=Figure())
    assert [tick.get_text() for tick in figure.axes[0].get_xticklabels()] == ["M1"]


def test_imported_v18_window_retains_commonality_table_and_clears_only_labels():
    if QApplication.instance() is None:
        app = QApplication([])
    window = app.engineering_window if hasattr(app, "engineering_window") else None
    from engineering_chart_analyzer import EngineeringChartWindow
    if window is not None:
        window.close()
    window = EngineeringChartWindow()
    assert window.summary_table is not None
    assert not window.summary_table.isHidden()
    assert window.vendor_summary_title.text() == ""
    assert window.findings.text() == ""
    window.close()
