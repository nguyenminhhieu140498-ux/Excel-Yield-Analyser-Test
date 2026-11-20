"""Regression tests for the requested v1.6 UI and chart fixes."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pandas as pd
import pytest
from matplotlib.figure import Figure
from PySide6.QtWidgets import QApplication, QSplitter


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_single_multi_spec_switch_keeps_controls_and_switches_rows(qapp):
    import engineering_chart_analyzer_v16_compact  # noqa: F401
    from engineering_chart_analyzer import EngineeringChartWindow

    window = EngineeringChartWindow()
    controls = window.input_scroll_area.widget()
    assert controls is not None
    assert window.single_mode.isChecked()
    assert not controls.isHidden()
    assert all(not widget.isHidden() for widget in (window.usl, window.target, window.lsl))

    window.multi_mode.setChecked(True)
    assert window.input_scroll_area.widget() is controls
    assert not controls.isHidden()
    assert not window.spec_table.isHidden()
    assert all(not button.isHidden() for button in window._spec_buttons)
    assert all(widget.isHidden() for widget in (window.usl, window.target, window.lsl))

    window.single_mode.setChecked(True)
    assert not controls.isHidden()
    assert window.spec_table.isHidden()
    assert all(button.isHidden() for button in window._spec_buttons)
    assert all(not widget.isHidden() for widget in (window.usl, window.target, window.lsl))

    splitters = [widget for widget in window.findChildren(QSplitter)
                 if widget.orientation().name == "Horizontal" and widget.count() >= 2]
    assert splitters and splitters[0].widget(0) is window.input_scroll_area
    window.close()


def test_preview_uses_full_canvas_area_and_keeps_zoom_axis(qapp):
    import engineering_chart_analyzer_v16_compact  # noqa: F401
    from engineering_chart_analyzer import EngineeringChartWindow

    window = EngineeringChartWindow()
    source = Figure(figsize=(4, 3))
    source.subplots().plot([0, 1], [1, 2])
    window._chart_figures = {"sample": source}
    window._chart_names = ["sample"]
    window._page = 0
    window._render_page()
    axis = window._v16_image_axis
    assert axis.get_aspect() == "auto"
    assert axis.get_position().bounds == pytest.approx((0, 0, 1, 1))
    assert len(axis.images) == 1
    window.close()


def test_box_plot_has_panel_for_each_vendor_breakdown_pair():
    import engineering_chart_analyzer_v16_compact as compact

    data = pd.DataFrame({
        "Vendor": ["A", "A", "A", "B", "B"],
        "Breakdown": ["X", "Y", "X", "X", "Y"],
        "M1": [1, 2, 3, 4, 5],
        "M2": [2, 3, 4, 5, 6],
    })
    fig = compact.render_boxplot_facets(
        data, ["M1", "M2"], vendor_column="Vendor", facet_column="Breakdown",
        vendor_values=["A", "B"], facet_values=["X", "Y"], figure=Figure(),
    )
    assert len(fig.axes) == 4
    assert [axis.get_title() for axis in fig.axes] == [
        "Vendor: A\nBreakdown: X", "Vendor: B\nBreakdown: X",
        "Vendor: A\nBreakdown: Y", "Vendor: B\nBreakdown: Y",
    ]
    assert all([tick.get_text() for tick in axis.get_xticklabels()] == ["M1", "M2"] for axis in fig.axes)


def test_commonality_export_schema_and_ui_headers_are_distinct(qapp):
    import engineering_chart_analyzer_v16_compact as compact
    from engineering_chart_analyzer import EngineeringChartWindow
    from engineering_charts import vendor_commonality_summary

    window = EngineeringChartWindow()
    window.vendor_column.addItem("Top Case Vendor")
    window.vendor_column.setCurrentText("Top Case Vendor")
    window.facet_column.addItem("Housing Vendor")
    window.facet_column.setCurrentText("Housing Vendor")
    window._last_summary = vendor_commonality_summary(
        pd.DataFrame({"Top Case Vendor": ["EVW"], "Housing Vendor": ["FX"], "M": [1.0]}),
        ["M"], "Top Case Vendor", "Housing Vendor",
    )
    window.summary_table.setColumnCount(len(window._last_summary.columns))

    compact._set_commonality_headers(window)
    assert list(window._last_summary.columns[:2]) == ["Vendor", "Breakdown"]
    assert window.summary_table.horizontalHeaderItem(0).text() == "Vendor value: Top Case Vendor"
    assert window.summary_table.horizontalHeaderItem(1).text() == "Breakdown value: Housing Vendor"
    window.close()
