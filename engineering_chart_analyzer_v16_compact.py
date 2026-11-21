"""Compact v1.6 launcher with parameter panel restoration and gesture zoom."""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QInputDialog, QScrollArea, QSizePolicy,
    QSplitter, QTableWidgetSelectionRange,
)

# Load the existing v1.6 charts/reports and prior CSV/spec/dedup fixes.
import engineering_chart_analyzer_v16_debug as v16
import engineering_chart_analyzer as app_module
import engineering_charts as chart_logic

VERSION = "1.6"
_BOX_CONTEXT = None

# Keep immutable references to the original renderers before installing wrappers.
_ORIGINAL_RENDER_V16_CHART = v16.render_v16_chart
_ORIGINAL_RENDER_V16_FACET = v16.render_v16_facet
_ORIGINAL_DRAW_SPECS = chart_logic._draw_specs


def _zoom_icon(sign: str) -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(Qt.GlobalColor.black, 1.6))
    painter.drawEllipse(1, 1, 12, 12)
    painter.drawLine(12, 12, 17, 17)
    painter.drawLine(4, 7, 10, 7)
    if sign == "+":
        painter.drawLine(7, 4, 7, 10)
    painter.end()
    return QIcon(pixmap)


class _GestureZoomFilter(QObject):
    """Compact gesture zoom; leaves ordinary table scrolling untouched."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            value = float(event.value())
            if value:
                factor = max(.2, min(5.0, 1.0 / (1.0 + value)))
                if watched is self.window.canvas:
                    self.window._v16_zoom(1.0 / factor)
                else:
                    table = self.window._zoom_table_lookup.get(watched)
                    if table is not None:
                        self._zoom_table(table, factor)
                return True
        if event.type() == QEvent.Type.Wheel and watched in self.window._zoom_table_targets:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                steps = event.angleDelta().y() / 120.0
                table = self.window._zoom_table_lookup.get(watched)
                if steps and table is not None:
                    self._zoom_table(table, 1.12 ** steps)
                    return True
        return super().eventFilter(watched, event)

    @staticmethod
    def _zoom_table(table, factor):
        font = table.font()
        size = font.pointSizeF() or 10.0
        font.setPointSizeF(max(6.0, min(30.0, size * factor)))
        table.setFont(font)
        table.horizontalHeader().setFont(font)
        table.verticalHeader().setFont(font)
        table.resizeRowsToContents()


def _restore_parameter_panel(window):
    """Ensure the original parameter-selection widget is actually visible in pane 1."""
    scroll = getattr(window, "input_scroll_area", None)
    if not isinstance(scroll, QScrollArea):
        scroll = next((item for item in window.findChildren(QScrollArea)
                       if item.objectName() == "inputControlsScrollArea"), None)
    controls = scroll.widget() if scroll is not None else None
    if controls is None and hasattr(window, "unit_key"):
        controls = window.unit_key.parentWidget()
        while controls is not None and controls.layout() is None:
            controls = controls.parentWidget()
    if controls is None:
        raise RuntimeError("Could not locate the original parameter-selection controls.")

    if scroll is None:
        scroll = QScrollArea(window)
        scroll.setObjectName("inputControlsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(controls)
        window.input_scroll_area = scroll
    elif scroll.widget() is None:
        scroll.setWidget(controls)

    scroll.setWidgetResizable(True)
    scroll.setMinimumWidth(400)
    scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    controls.setMinimumWidth(380)
    controls.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    controls.show()
    scroll.show()

    splitter = next((item for item in window.findChildren(QSplitter)
                     if item.orientation() == Qt.Orientation.Horizontal and item.count() >= 2), None)
    if splitter is None:
        raise RuntimeError("Could not locate the input/chart splitter.")
    if splitter.widget(0) is not scroll:
        splitter.insertWidget(0, scroll)
    splitter.setCollapsible(0, False)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    width = max(window.width(), 1200)
    splitter.setSizes([max(400, min(520, int(width * .28))), max(700, int(width * .72))])
    window.input_scroll_area = scroll

    required_controls = ("unit_key", "vendor_column", "facet_column", "chart_checks", "columns",
                         "single_mode", "multi_mode", "spec_table", "build_button")
    missing = [name for name in required_controls if not hasattr(window, name)]
    if missing:
        raise RuntimeError("Parameter panel is missing controls: " + ", ".join(missing))


def _apply_spec_visibility(window):
    """Toggle only spec-specific rows; never hide the controls parent widget."""
    multi = window.multi_mode.isChecked()
    for control, label in getattr(window, "_multi_spec_labels", []):
        control.setVisible(not multi)
        if label is not None:
            label.setVisible(not multi)
    table_label = getattr(window, "_spec_table_label", None)
    window.spec_table.setVisible(multi)
    if table_label is not None:
        table_label.setVisible(multi)
    # Spec buttons share the controls QWidget as parent; hide buttons individually.
    for button in getattr(window, "_spec_buttons", []):
        button.setVisible(multi)


# Install before the v1.6 initializer calls the visibility method.
app_module.EngineeringChartWindow._apply_v16_spec_visibility = _apply_spec_visibility


def _draw_specs_with_target_label(ax, columns, specs):
    """Draw spec lines and their numeric Target/Nominal labels on the source figure."""
    _ORIGINAL_DRAW_SPECS(ax, columns, specs)
    for spec in specs:
        value = spec.get("Target")
        if value is None:
            continue
        lo, hi = spec["start_index"], spec["end_index"]
        ax.annotate(
            f"Target/Nominal: {value:g}",
            xy=((lo + hi) / 2, value),
            xytext=(0, 5),
            textcoords="offset points",
            color="#168447",
            fontsize=7,
            ha="center",
            va="bottom",
        )


chart_logic._draw_specs = _draw_specs_with_target_label


def render_boxplot_facets(data, columns, *, vendor_column, facet_column="", figure=None,
                          vendor_values=None, facet_values=None, spec_ranges=None,
                          spec_mode="Single Spec", usl=None, lsl=None, target=None):
    """Render the existing Box Plot as one panel per Vendor × Breakdown pair."""
    columns = list(columns)
    if not columns:
        raise ValueError("Select at least one numeric measurement column.")
    if not vendor_column or vendor_column not in data:
        raise ValueError("Choose a vendor field for box plots.")

    values = data[columns].apply(pd.to_numeric, errors="coerce")
    vendors_all = chart_logic._group_labels(data, vendor_column)
    facets_all = (chart_logic._group_labels(data, facet_column)
                  if facet_column and facet_column in data
                  else pd.Series("All units", index=data.index))
    vendors = list(vendor_values) if vendor_values is not None else [x for x in vendors_all.unique() if x != "(blank)"]
    facets = list(facet_values) if facet_values is not None else [x for x in facets_all.unique() if x != "(blank)"]
    vendors = vendors[:8] or ["(no selected vendors)"]
    facets = facets[:8] or ["(no selected breakdowns)"]
    specs = chart_logic.spec_limits_for_columns(columns, spec_mode, usl, target, lsl, spec_ranges)

    fig = figure or Figure(figsize=(14, 8), dpi=160)
    fig.clear()
    axes = fig.subplots(len(facets), len(vendors), squeeze=False, sharey=True)
    for row, facet in enumerate(facets):
        for col, vendor in enumerate(vendors):
            ax = axes[row, col]
            mask = vendors_all.eq(vendor) & facets_all.eq(facet)
            distributions = [values.loc[mask, name].dropna().to_numpy(dtype=float) for name in columns]
            nonempty = [idx for idx, array in enumerate(distributions) if len(array)]
            if nonempty:
                # Use the long-supported labels argument for Matplotlib 3.8 compatibility.
                ax.boxplot([distributions[idx] for idx in nonempty], positions=nonempty,
                           labels=[columns[idx] for idx in nonempty], showfliers=True,
                           flierprops={"markersize": 3})
            else:
                ax.text(.5, .5, "No measurements", ha="center", va="center", transform=ax.transAxes)
            chart_logic._draw_specs(ax, columns, specs)
            ax.set_title(f"{vendor_column}: {vendor}\n{facet_column or 'Breakdown'}: {facet}",
                         fontsize=9, fontweight="bold")
            ax.set_ylabel("Measurement value")
            ax.tick_params(axis="x", rotation=60, labelsize=7)
            ax.grid(axis="y", alpha=.2)
    fig.suptitle(f"Box Plot by {vendor_column}" + (f" × {facet_column}" if facet_column else ""),
                 fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, .95))
    return fig


def _render_chart_with_box_facets(*args, **kwargs):
    """Route Box Plot to facets and all other charts to the captured v1.6 renderer."""
    if len(args) >= 3 and args[2] == "Box Plot by Vendor" and _BOX_CONTEXT:
        return render_boxplot_facets(args[0], args[1], figure=kwargs.get("figure"), **_BOX_CONTEXT)
    # Do not call v16.render_v16_chart here: that public name is patched below.
    return _ORIGINAL_RENDER_V16_CHART(*args, **kwargs)


# Patch only the application-facing generic renderer. Keep v16's public function intact.
app_module.render_chart = _render_chart_with_box_facets
chart_logic.render_chart = _render_chart_with_box_facets


def _read_insight_raw_sheet(path, sheet_name):
    """Read Insight Raw with Excel row 2 as headers and discard blank column-C rows."""
    raw = pd.read_excel(path, sheet_name=sheet_name, header=1)
    if raw.shape[1] < 3:
        raise ValueError("Insight Raw data must contain at least three columns.")
    column_c = raw.iloc[:, 2]
    keep = column_c.notna() & column_c.astype(str).str.strip().ne("")
    return raw.loc[keep].reset_index(drop=True)


def _open_measurements_with_template(self):
    """Choose an import template while leaving the established PE reader untouched."""
    try:
        path, _ = app_module.QFileDialog.getOpenFileName(
            self, "Open measurement workbook", "", "Excel (*.xlsx *.xlsm)"
        )
        if not path:
            return
        template, ok = QInputDialog.getItem(
            self,
            "Select measurement data template",
            "Data template:",
            ["Fleet Data - PE Format", "Fleet Data - Insight Raw"],
            0,
            False,
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
        if len(chosen) > 1 and app_module.QMessageBox.question(
            self,
            "Open selected sheets?",
            f"Open {len(chosen)} sheets in separate windows?",
            app_module.QMessageBox.StandardButton.Yes | app_module.QMessageBox.StandardButton.Cancel,
        ) == app_module.QMessageBox.StandardButton.Cancel:
            return

        for sheet in chosen:
            if template == "Fleet Data - PE Format":
                # Preserve the project's existing PE detection algorithm verbatim.
                frame = self._read_measurement(path, sheet)
            else:
                frame = _read_insight_raw_sheet(path, sheet)
            if len(chosen) == 1:
                self._set_measurements(Path(path), frame, sheet)
            else:
                window = app_module.EngineeringChartWindow()
                window._set_measurements(Path(path), frame, sheet)
                window.show()
                self._child_windows.append(window)
        self._progress(100, f"Loaded {len(chosen)} sheet(s); each sheet has its own window.")
    except Exception as exc:
        self._error(str(exc))


app_module.EngineeringChartWindow.open_measurements = _open_measurements_with_template


def _render_large_preview(self):
    if not getattr(self, "_chart_names", []):
        return
    name = self._chart_names[self._page]
    self.figure.clear()
    source = self._chart_figures[name]
    buffer = BytesIO()
    source.savefig(buffer, format="png", dpi=240, bbox_inches="tight")
    buffer.seek(0)
    import matplotlib.image as mpimg
    axis = self.figure.add_axes((0, 0, 1, 1))
    axis.imshow(mpimg.imread(buffer), interpolation="lanczos", aspect="auto")
    axis.axis("off")
    self._v16_image_axis = axis
    self.canvas.draw_idle()
    self.page_label.setText(f"Chart {self._page + 1} / {len(self._chart_names)} — {name}")


def _set_commonality_headers(window):
    """Keep the summary/export data schema stable and customize only UI headers."""
    frame = getattr(window, "_last_summary", None)
    if frame is None or len(frame.columns) < 2:
        return
    columns = list(frame.columns)
    columns[0] = "Vendor"
    columns[1] = "Breakdown"
    frame.columns = columns
    headers = [str(column) for column in frame.columns]
    vendor_field = window.vendor_column.currentText() or "Vendor"
    breakdown_field = window.facet_column.currentText() or "All units"
    headers[0] = f"Vendor value: {vendor_field}"
    headers[1] = f"Breakdown value: {breakdown_field}"
    if window.summary_table.columnCount() == len(headers):
        window.summary_table.setHorizontalHeaderLabels(headers)


def _filter_by_selected_fail_sn(data, key_column, selected_sns):
    """Filter all measurement rows by SN only, never by Fail Position."""
    if not key_column or key_column not in data:
        return data.iloc[0:0].copy()
    selected = {str(value) for value in selected_sns}
    if not selected:
        return data.iloc[0:0].copy()
    return data.loc[data[key_column].astype("object").astype(str).isin(selected)].copy()


def _selected_fail_sns(window):
    selected_rows = window.fail_table.selectionModel().selectedRows()
    result = []
    for model_index in selected_rows:
        item = window.fail_table.item(model_index.row(), 0)
        if item is not None:
            result.append(item.text())
    return result


def _rerender_selected_fail_sns(window):
    if not getattr(window, "_fail_filter_ready", False):
        return
    if not window.fail_toggle.isChecked() or not getattr(window, "_failure_chart_data", None) is not None:
        return
    selected = _selected_fail_sns(window)
    data = _filter_by_selected_fail_sn(
        window._failure_chart_data, window._failure_key_column, selected
    )
    figures = {}
    if data.empty:
        for chart_name in window._failure_chart_names:
            figure = Figure(figsize=(12, 7))
            axis = figure.add_subplot(111)
            axis.text(.5, .5, "No Fail SN selected", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
            figures[chart_name] = figure
    else:
        context = window._failure_render_context
        for chart_name in window._failure_chart_names:
            figure = Figure(figsize=(12, 7))
            common = dict(
                usl=context["usl"], lsl=context["lsl"], target=context["target"],
                spec_ranges=context["specs"], spec_mode=context["spec_mode"],
                figure=figure,
            )
            if chart_name == "Multi-Line Trend Chart" and context["vendor"]:
                _ORIGINAL_RENDER_V16_FACET(
                    data, context["columns"], vendor_column=context["vendor"],
                    facet_column=context["facet"], sample_limit=context["sample_limit"],
                    vendor_values=context["vendor_values"], facet_values=context["facet_values"],
                    highlight_oos=context["highlight_oos"], **common,
                )
            elif chart_name == "Box Plot by Vendor":
                render_boxplot_facets(
                    data, context["columns"], vendor_column=context["vendor"],
                    facet_column=context["facet"], vendor_values=context["vendor_values"],
                    facet_values=context["facet_values"], **common,
                )
            else:
                _ORIGINAL_RENDER_V16_CHART(
                    data, context["columns"], chart_name, group_column=context["vendor"],
                    sample_limit=context["sample_limit"], highlight_oos=context["highlight_oos"], **common,
                )
            figures[chart_name] = figure
    window._chart_figures = figures
    window._chart_data = data
    window._render_page()


_original_build = app_module.EngineeringChartWindow.build_charts


def _build_with_pair_facets_and_fail_filter(self, *args, **kwargs):
    global _BOX_CONTEXT
    self._fail_filter_ready = False
    _BOX_CONTEXT = {
        "vendor_column": self.vendor_column.currentText(),
        "facet_column": self.facet_column.currentText(),
        "vendor_values": self.checked(self.vendor_values),
        "facet_values": self.checked(self.facet_values),
        "usl": None if self.multi_mode.isChecked() else self._number(self.usl),
        "lsl": None if self.multi_mode.isChecked() else self._number(self.lsl),
        "target": None if self.multi_mode.isChecked() else self._number(self.target),
        "spec_ranges": self._spec_rows(),
        "spec_mode": "Multi Spec" if self.multi_mode.isChecked() else "Single Spec",
    }
    try:
        result = _original_build(self, *args, **kwargs)
        _set_commonality_headers(self)
        if getattr(self, "_chart_data", None) is not None:
            self._failure_chart_data = self._chart_data.copy()
            self._failure_key_column = self.unit_key.currentText()
            self._failure_chart_names = list(getattr(self, "_chart_names", []))
            self._failure_render_context = {
                "columns": self.selected_columns(),
                "vendor": self.vendor_column.currentText(),
                "facet": self.facet_column.currentText(),
                "vendor_values": self.checked(self.vendor_values),
                "facet_values": self.checked(self.facet_values),
                "usl": _BOX_CONTEXT["usl"], "lsl": _BOX_CONTEXT["lsl"],
                "target": _BOX_CONTEXT["target"], "specs": list(getattr(self, "_last_specs", [])),
                "spec_mode": _BOX_CONTEXT["spec_mode"],
                "sample_limit": max(25, int(self.sample.text() or 350)),
                "highlight_oos": self.fail_toggle.isChecked(),
            }
            self._fail_filter_ready = True
            if self.fail_toggle.isChecked() and self.fail_table.rowCount():
                self.fail_table.selectAll()
                _rerender_selected_fail_sns(self)
        return result
    finally:
        _BOX_CONTEXT = None


app_module.EngineeringChartWindow.build_charts = _build_with_pair_facets_and_fail_filter


_original_init = app_module.EngineeringChartWindow.__init__


def _compact_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.setWindowTitle(f"Engineering Chart Analyzer — v{VERSION}")
    if hasattr(self, "version"):
        self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")
    _restore_parameter_panel(self)
    self._apply_v16_spec_visibility()

    self._fail_filter_ready = False
    self.fail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    self.fail_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    self.fail_table.itemSelectionChanged.connect(lambda: _rerender_selected_fail_sns(self))

    for name in ("zoom_in_button", "zoom_out_button", "zoom_reset_button"):
        widget = getattr(self, name, None)
        if widget is not None:
            widget.hide()
    toolbars = self.findChildren(NavigationToolbar2QT)
    if toolbars:
        toolbar = toolbars[0]
        zoom_in = QAction(_zoom_icon("+"), "Zoom in", toolbar)
        zoom_out = QAction(_zoom_icon("−"), "Zoom out", toolbar)
        zoom_in.triggered.connect(lambda: self._v16_zoom(.8))
        zoom_out.triggered.connect(lambda: self._v16_zoom(1.25))
        toolbar.addSeparator()
        toolbar.addAction(zoom_in)
        toolbar.addAction(zoom_out)
        self._compact_zoom_actions = (zoom_in, zoom_out)

    self._zoom_table_targets = set()
    self._zoom_table_lookup = {}
    for name in ("summary_table", "fail_table"):
        table = getattr(self, name, None)
        if table is None:
            continue
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for target in (table, table.viewport()):
            self._zoom_table_targets.add(target)
            self._zoom_table_lookup[target] = table
    self._zoom_gesture_filter = _GestureZoomFilter(self)
    self.canvas.installEventFilter(self._zoom_gesture_filter)
    for target in self._zoom_table_targets:
        target.installEventFilter(self._zoom_gesture_filter)


app_module.EngineeringChartWindow.__init__ = _compact_init
app_module.EngineeringChartWindow._v16_render_page = _render_large_preview
app_module.EngineeringChartWindow._render_page = _render_large_preview


def main():
    app = QApplication(sys.argv)
    window = app_module.EngineeringChartWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
