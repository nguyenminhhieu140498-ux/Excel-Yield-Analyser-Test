"""V1.8 debug launcher: stable Pass/Fail chart composition and import fixes."""
from __future__ import annotations

import sys

import pandas as pd
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout

import engineering_chart_analyzer_v16_compact as v16_compact
import engineering_chart_analyzer as app_module
import engineering_charts as chart_logic
from insight_raw_reader import read_insight_raw_sheet

VERSION = "1.8 DEBUG"

# Insight Raw has an independent, raw-cell reader. PE continues to use its
# established reader unchanged through the existing template-selection path.
v16_compact._read_insight_raw_sheet = read_insight_raw_sheet

# Keep the already-tested renderers; this layer changes only the requested
# V1.8 behavior and leaves the existing UI widgets in place.
_ORIGINAL_INIT = app_module.EngineeringChartWindow.__init__
_ORIGINAL_BUILD = app_module.EngineeringChartWindow.build_charts
_ORIGINAL_DRAW_SPECS = v16_compact._ORIGINAL_DRAW_SPECS


def _draw_specs_numeric_target(ax, columns, specs):
    """Keep the green target line; show only its numeric value on that Y level."""
    _ORIGINAL_DRAW_SPECS(ax, columns, specs)
    for spec in specs:
        value = spec.get("Target")
        if value is None:
            continue
        lo, hi = spec["start_index"], spec["end_index"]
        ax.annotate(
            f"{value:g}",
            xy=((lo + hi) / 2, value),
            xytext=(3, 0),
            textcoords="offset points",
            color="#20a45b",
            fontsize=8,
            ha="left",
            va="center",
        )


chart_logic._draw_specs = _draw_specs_numeric_target


def _detach_layout_widgets(layout):
    """Remove a layout's visible widgets while preserving their Python references."""
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
        elif child_layout is not None:
            _detach_layout_widgets(child_layout)


def _remove_commonality_panel(window):
    """Remove only the commonality display and give its existing space to Fail SN."""
    preview = getattr(window, "preview_splitter", None)
    if preview is None or preview.count() < 2:
        return
    table_box = preview.widget(1)
    layout = table_box.layout()
    if not isinstance(layout, QHBoxLayout):
        return
    if layout.count() > 1:
        summary_item = layout.takeAt(0)
        summary_layout = summary_item.layout()
        if summary_layout is not None:
            _detach_layout_widgets(summary_layout)
        else:
            summary_widget = summary_item.widget()
            if summary_widget is not None:
                summary_widget.hide()
                summary_widget.setParent(None)
    if layout.count() > 0:
        layout.setStretch(0, 1)
    preview.setStretchFactor(1, 1)
    window.summary_table.hide()
    title = getattr(window, "vendor_summary_title", None)
    if title is not None:
        title.hide()


def _norm_sn(value):
    return chart_logic._norm_key(value)


def _failed_sn_keys(window, data, key_column, columns, specs):
    failures = getattr(window, "_last_failures", None)
    if failures is None or failures.empty:
        failures = chart_logic.fail_sn_list(data, columns, key_column, specs)
    if failures.empty or "Fail SN" not in failures:
        return set()
    return {_norm_sn(value) for value in failures["Fail SN"] if _norm_sn(value)}


def _render_composed_chart_data(window, selected_fail_sns=()):
    """Render all passing units plus only explicitly selected failing SNs."""
    source = getattr(window, "_v18_source_chart_data", None)
    if source is None or source.empty:
        return
    context = window._v18_chart_context
    fail_keys = _failed_sn_keys(
        window, source, context["key"], context["columns"], context["specs"]
    )
    normalized = source[context["key"]].map(_norm_sn)
    pass_data = source.loc[~normalized.isin(fail_keys)]
    selected_keys = {_norm_sn(value) for value in selected_fail_sns if _norm_sn(value)}
    selected_fail_data = source.loc[normalized.isin(selected_keys & fail_keys)]
    chart_data = pd.concat([pass_data, selected_fail_data]).drop_duplicates().reset_index(drop=True)

    figures = {}
    for chart_name in context["chart_names"]:
        figure = Figure(figsize=(12, 7))
        common = dict(
            usl=context["usl"], lsl=context["lsl"], target=context["target"],
            spec_ranges=context["specs"], spec_mode=context["spec_mode"], figure=figure,
        )
        if chart_name == "Multi-Line Trend Chart" and context["vendor"]:
            v16_compact._ORIGINAL_RENDER_V16_FACET(
                chart_data, context["columns"], vendor_column=context["vendor"],
                facet_column=context["facet"], sample_limit=context["sample_limit"],
                vendor_values=context["vendor_values"], facet_values=context["facet_values"],
                highlight_oos=context["highlight_oos"], **common,
            )
        elif chart_name == "Box Plot by Vendor":
            v16_compact.render_boxplot_facets(
                chart_data, context["columns"], vendor_column=context["vendor"],
                facet_column=context["facet"], vendor_values=context["vendor_values"],
                facet_values=context["facet_values"], **common,
            )
        else:
            v16_compact._ORIGINAL_RENDER_V16_CHART(
                chart_data, context["columns"], chart_name, group_column=context["vendor"],
                sample_limit=context["sample_limit"], highlight_oos=context["highlight_oos"], **common,
            )
        figures[chart_name] = figure

    window._chart_figures = figures
    window._chart_data = chart_data
    window._render_page()


def _selected_sns_from_table(window):
    selected = []
    for index in window.fail_table.selectionModel().selectedRows():
        item = window.fail_table.item(index.row(), 0)
        if item is not None:
            selected.append(item.text())
    return selected


def _fail_selection_changed(window):
    if not getattr(window, "_v18_ready", False):
        return
    if window.fail_toggle.isChecked():
        _render_composed_chart_data(window, _selected_sns_from_table(window))


def _build_charts_v18(self, *args, **kwargs):
    result = _ORIGINAL_BUILD(self, *args, **kwargs)
    source = getattr(self, "_chart_data", None)
    if source is None or source.empty or not getattr(self, "_chart_names", None):
        return result

    self._v18_source_chart_data = source.copy()
    self._v18_chart_context = {
        "key": self.unit_key.currentText(),
        "columns": self.selected_columns(),
        "vendor": self.vendor_column.currentText(),
        "facet": self.facet_column.currentText(),
        "vendor_values": self.checked(self.vendor_values),
        "facet_values": self.checked(self.facet_values),
        "usl": None if self.multi_mode.isChecked() else self._number(self.usl),
        "lsl": None if self.multi_mode.isChecked() else self._number(self.lsl),
        "target": None if self.multi_mode.isChecked() else self._number(self.target),
        "specs": list(getattr(self, "_last_specs", [])),
        "spec_mode": "Multi Spec" if self.multi_mode.isChecked() else "Single Spec",
        "sample_limit": max(25, int(self.sample.text() or 350)),
        "highlight_oos": self.fail_toggle.isChecked(),
        "chart_names": list(self._chart_names),
    }

    # Start with Pass Units and add a failing SN only when explicitly selected.
    self._v18_ready = False
    self.fail_table.clearSelection()
    self._v18_ready = True
    _render_composed_chart_data(self, _selected_sns_from_table(self))
    return result


def _init_window_v18(self, *args, **kwargs):
    _ORIGINAL_INIT(self, *args, **kwargs)
    self.setWindowTitle(f"Engineering Chart Analyzer — {VERSION}")
    if hasattr(self, "version"):
        self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")
    _remove_commonality_panel(self)
    self._v18_ready = False
    self.fail_table.itemSelectionChanged.connect(lambda: _fail_selection_changed(self))


app_module.EngineeringChartWindow.__init__ = _init_window_v18
app_module.EngineeringChartWindow.build_charts = _build_charts_v18


def main():
    app = QApplication(sys.argv)
    window = app_module.EngineeringChartWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
