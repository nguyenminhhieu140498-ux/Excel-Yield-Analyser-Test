"""Compact v1.6 launcher with safe toolbar and gesture zoom."""
from __future__ import annotations
import sys
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
import engineering_chart_analyzer_v16_debug  # Apply v1.6 application patches.
import engineering_chart_analyzer as app_module

VERSION = "1.6"

def _zoom_icon(sign):
    pixmap=QPixmap(18,18); pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setPen(QPen(Qt.GlobalColor.black,1.6))
    painter.drawEllipse(1,1,12,12); painter.drawLine(12,12,17,17); painter.drawLine(4,7,10,7)
    if sign=="+": painter.drawLine(7,4,7,10)
    painter.end(); return QIcon(pixmap)

class _GestureZoomFilter(QObject):
    def __init__(self,window): super().__init__(window); self.window=window
    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.NativeGesture and event.gestureType()==Qt.NativeGestureType.ZoomNativeGesture:
            value=float(event.value())
            if value:
                factor=max(.2,min(5.,1./(1.+value)))
                if watched is self.window.canvas: self.window._v16_zoom(1./factor)
                else:
                    table=self.window._zoom_table_lookup.get(watched)
                    if table is not None:self._zoom_table(table,factor)
                return True
        if event.type()==QEvent.Type.Wheel and watched in self.window._zoom_table_targets and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps=event.angleDelta().y()/120.
            if steps:
                self._zoom_table(self.window._zoom_table_lookup[watched],1.12**steps)
                return True
        return super().eventFilter(watched,event)
    @staticmethod
    def _zoom_table(table,factor):
        font=table.font(); size=font.pointSizeF() or 10.
        font.setPointSizeF(max(6.,min(30.,size*factor))); table.setFont(font)
        table.horizontalHeader().setFont(font); table.verticalHeader().setFont(font); table.resizeRowsToContents()

_original_init=app_module.EngineeringChartWindow.__init__
def _compact_init(self,*args,**kwargs):
    _original_init(self,*args,**kwargs)
    self.setWindowTitle(f"Engineering Chart Analyzer — v{VERSION}")
    if hasattr(self,"version"):self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")
    for name in ("zoom_in_button","zoom_out_button","zoom_reset_button"):
        widget=getattr(self,name,None)
        if widget is not None:widget.hide()
    toolbars=self.findChildren(NavigationToolbar2QT)
    if toolbars:
        toolbar=toolbars[0]
        zoom_in=QAction(_zoom_icon("+"),"Zoom in",toolbar); zoom_out=QAction(_zoom_icon("−"),"Zoom out",toolbar)
        zoom_in.triggered.connect(lambda:self._v16_zoom(.8)); zoom_out.triggered.connect(lambda:self._v16_zoom(1.25))
        toolbar.addSeparator(); toolbar.addAction(zoom_in); toolbar.addAction(zoom_out)
        self._compact_zoom_actions=(zoom_in,zoom_out)
    self._zoom_table_targets=set(); self._zoom_table_lookup={}
    for name in ("summary_table","fail_table"):
        table=getattr(self,name,None)
        if table is None:continue
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        for target in (table,table.viewport()):
            self._zoom_table_targets.add(target); self._zoom_table_lookup[target]=table
    self._zoom_gesture_filter=_GestureZoomFilter(self)
    # FigureCanvasQTAgg is a QWidget, not a QAbstractScrollArea; no viewport().
    self.canvas.installEventFilter(self._zoom_gesture_filter)
    for target in self._zoom_table_targets:target.installEventFilter(self._zoom_gesture_filter)
app_module.EngineeringChartWindow.__init__=_compact_init

def main():
    app=QApplication(sys.argv); window=app_module.EngineeringChartWindow(); window.show(); return app.exec()
if __name__=="__main__":raise SystemExit(main())
