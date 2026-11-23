"""V1.8 debug launcher: stable Pass/Fail chart composition and import fixes."""
from __future__ import annotations

import sys

import pandas as pd
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHBoxLayout, QInputDialog, QMessageBox

import engineering_chart_analyzer_v16_compact as v16_compact
import engineering_chart_analyzer as app_module
import engineering_charts as chart_logic
from insight_raw_reader import read_insight_raw_sheet

VERSION = "1.8 DEBUG"

# Insight Raw has an independent raw-cell reader; PE continues through the
# established reader unchanged.
v16_compact._read_insight_raw_sheet = read_insight_raw_sheet

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
            f"{value:g}", xy=((lo + hi) / 2, value), xytext=(3, 0),
            textcoords="offset points", color="#20a45b", fontsize=8,
            ha="left", va="center",
        )


chart_logic._draw_specs = _draw_specs_numeric_target


def _remove_commonality_labels(window):
    """Clear only the two requested labels; preserve table, layout and data."""
    title = getattr(window, "vendor_summary_title", None)
    if title is not None:
        title.setText("")
    findings = getattr(window, "findings", None)
    if findings is not None and findings.text().strip() == "Load data to begin.":
        findings.setText("")


def _norm_sn(value):
    return chart_logic._norm_key(value)


def _failed_sn_keys(window, data, key_column, columns, specs):
    """Derive failing serials from the current chart data and existing specs."""
    return _failed_sn_keys_from_data(data, key_column, columns, specs)


def _failed_sn_keys_from_data(data, key_column, columns, specs):
    """Return normalized SNs that fail one or more selected measurement specs."""
    failures = chart_logic.fail_sn_list(data, columns, key_column, specs)
    if failures.empty:
        return set()
    return {_norm_sn(value) for value in failures["Fail SN"] if _norm_sn(value)}


def _compose_pass_fail_data(data, key_column, columns, specs, selected_fail_sns=None):
    """Keep all passing rows; optionally limit failing rows to selected SNs.

    ``None`` or an empty selection means the default view: all Pass and Fail
    Units. A non-empty selection retains the complete Pass baseline and adds
    only the selected failing serials.
    """
    if data is None or data.empty or not key_column or key_column not in data:
        return data.copy() if isinstance(data, pd.DataFrame) else pd.DataFrame()

    fail_keys = _failed_sn_keys_from_data(data, key_column, columns, specs)
    normalized = data[key_column].map(_norm_sn)
    failing_rows = normalized.isin(fail_keys)
    if not selected_fail_sns:
        return data.copy()

    selected_keys = {_norm_sn(value) for value in selected_fail_sns if _norm_sn(value)}
    keep = ~failing_rows | (failing_rows & normalized.isin(selected_keys))
    return data.loc[keep].copy()


def _render_composed_chart_data(window, selected_fail_sns=None):
    """Render the Pass baseline and the default or selected Fail SN overlay."""
    source = getattr(window, "_v18_source_chart_data", None)
    if source is None or source.empty:
        return
    context = window._v18_chart_context
    chart_data = _compose_pass_fail_data(
        source, context["key"], context["columns"], context["specs"], selected_fail_sns
    )

    figures = {}
    for chart_name in context["chart_names"]:
        figure = Figure(figsize=(12, 7))
        common = dict(usl=context["usl"], lsl=context["lsl"], target=context["target"],
                      spec_ranges=context["specs"], spec_mode=context["spec_mode"], figure=figure)
        if chart_name == "Multi-Line Trend Chart" and context["vendor"]:
            v16_compact._ORIGINAL_RENDER_V16_FACET(
                chart_data, context["columns"], vendor_column=context["vendor"],
                facet_column=context["facet"], sample_limit=context["sample_limit"],
                vendor_values=context["vendor_values"], facet_values=context["facet_values"],
                # Always distinguish failing rows from the Pass baseline.
                highlight_oos=True, **common,
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
    if getattr(window, "_v18_ready", False) and window.fail_toggle.isChecked():
        selected = _selected_sns_from_table(window)
        # Clearing selection restores the default view with every Fail Unit.
        _render_composed_chart_data(window, selected or None)


def _build_charts_v18(self, *args, **kwargs):
    result = _ORIGINAL_BUILD(self, *args, **kwargs)
    source = getattr(self, "_chart_data", None)
    if source is None or source.empty or not getattr(self, "_chart_names", None):
        return result
    self._v18_source_chart_data = source.copy()
    self._v18_chart_context = {
        "key": self.unit_key.currentText(), "columns": self.selected_columns(),
        "vendor": self.vendor_column.currentText(), "facet": self.facet_column.currentText(),
        "vendor_values": self.checked(self.vendor_values), "facet_values": self.checked(self.facet_values),
        "usl": None if self.multi_mode.isChecked() else self._number(self.usl),
        "lsl": None if self.multi_mode.isChecked() else self._number(self.lsl),
        "target": None if self.multi_mode.isChecked() else self._number(self.target),
        "specs": list(getattr(self, "_last_specs", [])),
        "spec_mode": "Multi Spec" if self.multi_mode.isChecked() else "Single Spec",
        "sample_limit": max(25, int(self.sample.text() or 350)),
        "highlight_oos": self.fail_toggle.isChecked(), "chart_names": list(self._chart_names),
    }
    self._v18_ready = False
    self.fail_table.clearSelection()
    self._v18_ready = True
    # Build completes in the default state: all Pass and all Fail Units visible.
    _render_composed_chart_data(self, None)
    return result


def _open_measurements_v18(self):
    """Keep PE import unchanged; ask for the actual Insight Raw header row."""
    try:
        path, _ = app_module.QFileDialog.getOpenFileName(
            self, "Open measurement workbook", "", "Excel (*.xlsx *.xlsm)"
        )
        if not path:
            return
        template, ok = QInputDialog.getItem(
            self, "Select measurement data template", "Data template:",
            ["Fleet Data - PE Format", "Fleet Data - Insight Raw"], 0, False,
        )
        if not ok:
            return
        sheets = pd.ExcelFile(path).sheet_names
        dialog = app_module.MultiSheetDialog(sheets, self)
        if dialog.exec() != app_module.QDialog.DialogCode.Accepted:
            return
        chosen = dialog.selected()
        if not chosen:
            return
        header_row = None
        if template == "Fleet Data - Insight Raw":
            header_row, ok = QInputDialog.getInt(
                self, "Insight Raw header row", "Excel row containing column headers:",
                3, 1, 1000000, 1,
            )
            if not ok:
                return
        if len(chosen) > 1 and app_module.QMessageBox.question(
            self, "Open selected sheets?", f"Open {len(chosen)} sheets in separate windows?",
            app_module.QMessageBox.StandardButton.Yes | app_module.QMessageBox.StandardButton.Cancel,
        ) == app_module.QMessageBox.StandardButton.Cancel:
            return

        from pathlib import Path
        for sheet in chosen:
            frame = (self._read_measurement(path, sheet) if template == "Fleet Data - PE Format"
                     else read_insight_raw_sheet(path, sheet, header_row))
            if len(chosen) == 1:
                self._set_measurements(Path(path), frame, sheet)
            else:
                child = app_module.EngineeringChartWindow()
                child._set_measurements(Path(path), frame, sheet)
                child.show()
                self._child_windows.append(child)
        self._progress(100, f"Loaded {len(chosen)} sheet(s); each sheet has its own window.")
    except Exception as exc:
        self._error(str(exc))


def _init_window_v18(self, *args, **kwargs):
    _ORIGINAL_INIT(self, *args, **kwargs)
    self.setWindowTitle(f"Engineering Chart Analyzer — {VERSION}")
    if hasattr(self, "version"):
        self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")
    _remove_commonality_labels(self)
    self._v18_ready = False
    self.fail_table.itemSelectionChanged.connect(lambda: _fail_selection_changed(self))


app_module.EngineeringChartWindow.open_measurements = _open_measurements_v18
app_module.EngineeringChartWindow.__init__ = _init_window_v18
app_module.EngineeringChartWindow.build_charts = _build_charts_v18


def main():
    app = QApplication(sys.argv)
    window = app_module.EngineeringChartWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
