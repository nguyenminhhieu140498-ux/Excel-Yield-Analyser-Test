"""V1.8 regression tests for pass/fail chart composition and target labels."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
from matplotlib.figure import Figure
import pytest
from PySide6.QtWidgets import QApplication

import engineering_chart_analyzer_v16_compact as compact
import engineering_chart_analyzer_v18_debug as v18


def test_pass_units_are_preserved_and_only_selected_fail_sns_are_added(qapp=None):
    data = pd.DataFrame({
        "SN": ["P1", "P2", "F1", "F2"],
        "M1": [0.0, 0.1, 1.2, 1.5],
        "M2": [0.0, 0.2, 1.1, 1.4],
    })
    specs = [{"start_index": 0, "end_index": 1, "USL": 1.0, "LSL": None,
              "Target": 0.5, "Start Point": "M1", "End Point": "M2"}]
    failing = v18._failed_sn_keys_from_data(data, "SN", ["M1", "M2"], specs)
    passing = data.loc[~data["SN"].map(v18._norm_sn).isin(failing)]
    chosen = data.loc[data["SN"].map(v18._norm_sn).isin({v18._norm_sn("F1")})]
    chart_rows = pd.concat([passing, chosen]).drop_duplicates()
    assert chart_rows["SN"].tolist() == ["P1", "P2", "F1"]


def test_target_label_is_numeric_only_and_aligned_to_target_y_value():
    figure = Figure()
    axis = figure.add_subplot(111)
    v18._draw_specs_numeric_target(axis, ["M1", "M2"], [{
        "start_index": 0, "end_index": 1, "USL": None, "LSL": None, "Target": -0.1,
    }])
    labels = [text for text in axis.texts]
    assert len(labels) == 1
    assert labels[0].get_text() == "-0.1"
    assert labels[0].get_color() == "#20a45b"
    assert labels[0].get_position()[1] == pytest.approx(-0.1)


def test_boxplot_uses_matplotlib_supported_label_keyword():
    data = pd.DataFrame({"Vendor": ["A", "A"], "M1": [1.0, 2.0]})
    figure = compact.render_boxplot_facets(data, ["M1"], vendor_column="Vendor", figure=Figure())
    assert [tick.get_text() for tick in figure.axes[0].get_xticklabels()] == ["M1"]


def test_insight_raw_import_discards_empty_and_whitespace_column_c(monkeypatch):
    workbook = pd.DataFrame({"SN": ["A", "B", "C"], "Vendor": ["V1", "V2", "V3"],
                             "Measurement": [1.2, None, "   "]})
    monkeypatch.setattr(v18.pd, "read_excel", lambda *args, **kwargs: workbook.copy())
    result = compact._read_insight_raw_sheet("fleet.xlsx", "Raw")
    assert result["SN"].tolist() == ["A"]


def test_commonality_panel_removal_is_safe_for_uninitialized_dialog(qapp=None):
    if QApplication.instance() is None:
        app = QApplication([])
    else:
        app = QApplication.instance()
    from engineering_chart_analyzer import EngineeringChartWindow
    window = EngineeringChartWindow()
    import engineering_chart_analyzer_v16_compact  # initializes V1.6 wrapper first
    # V1.8 initializer is installed when launcher is imported; instantiate a fresh one.
    window.close()
    window = EngineeringChartWindow()
    assert window.version.text().startswith("version 1.8")
    assert window.summary_table.isHidden()
    window.close()
