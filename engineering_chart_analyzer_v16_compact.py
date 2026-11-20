"""Compact v1.6 launcher with chart toolbar and gesture zoom.

The chart uses the existing Matplotlib navigation toolbar plus mouse-wheel /
trackpad zoom. Tables support Ctrl+wheel or pinch-to-zoom; normal scrolling is
unchanged. No large preview zoom buttons are created.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

# Import v1.6 first so its chart, report, and UI compatibility patches load.
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
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.NativeGesture:
            if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                value = float(event.value())
                if value:
                    self._zoom_target(watched, 1.0 / (1.0 + value))
                    return True
        if event.type() == QEvent.Type.Wheel and watched in self.window._zoom_table_targets:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                steps = event.angleDelta().y() / 120.0
                if steps:
                    table = self.window._table_for_target(watched)
                    self._zoom_table(table, 1.12 ** steps)
                    return True
        return super().eventFilter(watched, event)

    def _zoom_target(self, watched, factor):
        if watched is self.window.canvas:
            # Matplotlib's scroll handler in v1.6 zooms around the pointer.
            self.window._v16_zoom(max(.2, min(5.0, 1.0 / factor)))
            return
        table = self.window._table_for_target(watched)
        if table is not None:
            self._zoom_table(table, factor)

    @staticmethod
    def _zoom_table(table, factor):
        if table is None:
            return
        font = table.font()
        size = font.pointSizeF()
        if size <= 0:
            size = 10.0
        font.setPointSizeF(max(6.0, min(30.0, size * factor)))
        table.setFont(font)
        table.horizontalHeader().setFont(font)
        table.verticalHeader().setFont(font)
        table.resizeRowsToContents()


_original_init = app_module.EngineeringChartWindow.__init__


def _compact_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.setWindowTitle(f"Engineering Chart Analyzer — v{VERSION}")
    if hasattr(self, "version"):
        self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")

    # Hide the large buttons from the preceding preview iteration if present.
    for name in ("zoom_in_button", "zoom_out_button", "zoom_reset_button"):
        widget = getattr(self, name, None)
        if widget is not None:
            widget.hide()

    toolbars = self.findChildren(NavigationToolbar2QT)
    if toolbars:
        toolbar = toolbars[0]
        toolbar.setIconSize(toolbar.iconSize())
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
        target_objects = [table, table.viewport()]
        for target in target_objects:
            self._zoom_table_targets.add(target)
            self._zoom_table_lookup[target] = table
            target.installEventFilter(self._zoom_gesture_filter if hasattr(self, "_zoom_gesture_filter") else QObject())

    self._zoom_gesture_filter = _GestureZoomFilter(self)
    # FigureCanvasQTAgg is a QWidget and has no QAbstractScrollArea.viewport().
    # Install only on the canvas itself to avoid the reported AttributeError.
    self.canvas.installEventFilter(self._zoom_gesture_filter)
    for target in self._zoom_table_targets:
        target.installEventFilter(self._zoom_gesture_filter)


def _table_for_target(self, target):
    return self._zoom_table_lookup.get(target)


app_module.EngineeringChartWindow.__init__ = _compact_init
app_module.EngineeringChartWindow._table_for_target = _table_for_target


def main():
    app = QApplication(sys.argv)
    window = app_module.EngineeringChartWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
