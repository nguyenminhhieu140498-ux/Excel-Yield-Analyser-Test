"""Compact v1.6 launcher with zoom integrated into the chart toolbar.

Chart: toolbar magnifier icons and mouse-wheel/trackpad zoom.
Tables: Ctrl+wheel or trackpad pinch zooms table text; ordinary wheel scrolls.
No extra zoom buttons are added to the preview area.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QStyle
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

import engineering_chart_analyzer_v16_debug as v16
import engineering_chart_analyzer as app_module

VERSION = "1.6"


def _zoom_icon(sign: str) -> QIcon:
    """Draw a compact magnifier icon for the existing chart toolbar."""
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(Qt.GlobalColor.black, 1.7)
    painter.setPen(pen)
    painter.drawEllipse(2, 2, 12, 12)
    painter.drawLine(13, 13, 18, 18)
    painter.drawLine(5, 8, 11, 8)
    if sign == "+":
        painter.drawLine(8, 5, 8, 11)
    painter.end()
    return QIcon(pixmap)


class _GestureZoomFilter(QObject):
    """Handle pinch zoom on chart and tables without adding screen controls."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.NativeGesture and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            factor = float(event.value())
            if factor:
                scale = 1.0 / (1.0 + factor)
                self._apply_zoom(watched, scale)
                return True
        if event.type() == QEvent.Type.Wheel and watched in self.window._v16_zoom_tables:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                steps = event.angleDelta().y() / 120.0
                if steps:
                    self._zoom_table(watched, 0.12 * steps)
                    return True
        return super().eventFilter(watched, event)

    def _apply_zoom(self, watched, scale):
        if watched is self.window.canvas or watched is self.window.canvas.viewport():
            self.window._v16_zoom(max(.2, min(5.0, scale)))
        elif watched in self.window._v16_zoom_tables:
            self._zoom_table(watched, (1.0 / scale - 1.0) * 0.75)

    @staticmethod
    def _zoom_table(table, delta):
        font = table.font()
        size = font.pointSizeF()
        if size <= 0:
            size = 10.0
        font.setPointSizeF(max(6.0, min(30.0, size * (1.0 + delta))))
        table.setFont(font)
        table.horizontalHeader().setFont(font)
        table.verticalHeader().setFont(font)
        table.resizeRowsToContents()


_original_init = app_module.EngineeringChartWindow.__init__


def _compact_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)

    # Do not let the DEBUG label leak into the user-facing app title/version.
    self.setWindowTitle(f"Engineering Chart Analyzer — v{VERSION}")
    if hasattr(self, "version"):
        self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")

    # The preceding launcher created large Zoom+/Zoom−/Reset buttons below the
    # chart. Hide those controls; use small magnifier actions in the chart toolbar.
    for attr in ("zoom_in_button", "zoom_out_button", "zoom_reset_button"):
        widget = getattr(self, attr, None)
        if widget is not None:
            widget.hide()

    toolbars = self.findChildren(NavigationToolbar2QT)
    if toolbars:
        toolbar = toolbars[0]
        toolbar.setIconSize(toolbar.iconSize().boundedTo(toolbar.iconSize()))
        plus = QAction(_zoom_icon("+"), "Zoom in", toolbar)
        minus = QAction(_zoom_icon("−"), "Zoom out", toolbar)
        plus.triggered.connect(lambda: self._v16_zoom(.8))
        minus.triggered.connect(lambda: self._v16_zoom(1.25))
        toolbar.addSeparator()
        toolbar.addAction(plus)
        toolbar.addAction(minus)
        self._compact_zoom_actions = (plus, minus)

    self._v16_zoom_tables = []
    for name in ("summary_table", "fail_table"):
        table = getattr(self, name, None)
        if table is not None:
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            table.setMinimumHeight(70)
            self._v16_zoom_tables.extend((table, table.viewport()))

    self._zoom_gesture_filter = _GestureZoomFilter(self)
    self.canvas.installEventFilter(self._zoom_gesture_filter)
    self.canvas.viewport().installEventFilter(self._zoom_gesture_filter)
    for table in (getattr(self, "summary_table", None), getattr(self, "fail_table", None)):
        if table is not None:
            table.installEventFilter(self._zoom_gesture_filter)
            table.viewport().installEventFilter(self._zoom_gesture_filter)


app_module.EngineeringChartWindow.__init__ = _compact_init


def main():
    app = QApplication(sys.argv)
    window = app_module.EngineeringChartWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
