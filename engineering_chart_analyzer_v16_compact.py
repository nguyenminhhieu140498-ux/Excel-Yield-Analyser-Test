"""Compact v1.6 launcher with parameter panel restoration and gesture zoom."""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QScrollArea, QSizePolicy, QSplitter
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

# Load the existing v1.6 charts/reports and prior CSV/spec/dedup fixes.
import engineering_chart_analyzer_v16_debug  # noqa: F401
import engineering_chart_analyzer as app_module

VERSION = "1.6"


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
    # The v1.4 wrapper created this scroll area around the original controls.
    scroll = getattr(window, "input_scroll_area", None)
    if not isinstance(scroll, QScrollArea):
        scroll = next((item for item in window.findChildren(QScrollArea)
                       if item.objectName() == "inputControlsScrollArea"), None)

    # Recover the exact original controls widget from its existing controls.
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

    # Attach the original selection panel to the top-level horizontal splitter;
    # never replace or rebuild its widgets/layout, so existing actions remain wired.
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

    # Guard against a panel that exists but lost the original key controls.
    required_controls = ("unit_key", "vendor_column", "facet_column", "chart_checks", "columns",
                         "single_mode", "multi_mode", "spec_table", "build_button")
    missing = [name for name in required_controls if not hasattr(window, name)]
    if missing:
        raise RuntimeError("Parameter panel is missing controls: " + ", ".join(missing))


_original_init = app_module.EngineeringChartWindow.__init__


def _compact_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.setWindowTitle(f"Engineering Chart Analyzer — v{VERSION}")
    if hasattr(self, "version"):
        self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")

    _restore_parameter_panel(self)

    # No oversized zoom buttons in the preview; add compact magnifiers to chart toolbar.
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
    # FigureCanvasQTAgg is a QWidget, not a QAbstractScrollArea; do not call viewport().
    self.canvas.installEventFilter(self._zoom_gesture_filter)
    for target in self._zoom_table_targets:
        target.installEventFilter(self._zoom_gesture_filter)


app_module.EngineeringChartWindow.__init__ = _compact_init


def main():
    app = QApplication(sys.argv)
    window = app_module.EngineeringChartWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
