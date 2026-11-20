"""Compact v1.6 launcher with parameter panel restoration and gesture zoom."""
from __future__ import annotations

import sys
from io import BytesIO

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QScrollArea, QSizePolicy, QSplitter

# Load the existing v1.6 charts/reports and prior CSV/spec/dedup fixes.
import engineering_chart_analyzer_v16_debug as v16
import engineering_chart_analyzer as app_module
import engineering_charts as chart_logic

VERSION = "1.6"
_BOX_CONTEXT = None


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
    # The buttons share the controls QWidget as parent (they are in a QHBoxLayout),
    # so hiding their parent would blank the entire parameter panel.
    for button in getattr(window, "_spec_buttons", []):
        button.setVisible(multi)


# Install before the v1.6 initializer calls the visibility method.
app_module.EngineeringChartWindow._apply_v16_spec_visibility = _apply_spec_visibility


def render_boxplot_facets(data, columns, *, vendor_column, facet_column="", figure=None,
                          vendor_values=None, facet_values=None, spec_ranges=None,
                          spec_mode="Single Spec", usl=None, lsl=None, target=None):
    """Render one box-plot panel per selected Vendor × Breakdown combination."""
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
                ax.boxplot([distributions[idx] for idx in nonempty], positions=nonempty,
                           tick_labels=[columns[idx] for idx in nonempty], showfliers=True)
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
    if len(args) >= 3 and args[2] == "Box Plot by Vendor" and _BOX_CONTEXT:
        return render_boxplot_facets(args[0], args[1], figure=kwargs.get("figure"), **_BOX_CONTEXT)
    return v16.render_v16_chart(*args, **kwargs)


# Patch the references used by the application and v1.6 wrapper.
chart_logic.render_chart = _render_chart_with_box_facets
app_module.render_chart = _render_chart_with_box_facets
v16.render_v16_chart = _render_chart_with_box_facets


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
    # The summary's first two fields are the group values, irrespective of the
    # source workbook's field names. Preserve these names for downstream exports.
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


_original_build = app_module.EngineeringChartWindow.build_charts


def _build_with_pair_facets(self, *args, **kwargs):
    global _BOX_CONTEXT
    # Match the selections passed to the Multi-Line facet renderer.
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
        return result
    finally:
        _BOX_CONTEXT = None


app_module.EngineeringChartWindow.build_charts = _build_with_pair_facets


_original_init = app_module.EngineeringChartWindow.__init__


def _compact_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.setWindowTitle(f"Engineering Chart Analyzer — v{VERSION}")
    if hasattr(self, "version"):
        self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")
    _restore_parameter_panel(self)

    # The earlier base handler changes only individual spec controls, not the
    # parent panel; the v1.6 handler is likewise safe after the class override.
    self._apply_v16_spec_visibility()

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
