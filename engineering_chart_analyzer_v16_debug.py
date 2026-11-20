"""v1.6 DEBUG launcher: visualization, UI sizing, and report usability fixes."""
from __future__ import annotations

import sys
from pathlib import Path
from io import BytesIO

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSplitter, QTableWidget, QVBoxLayout,
)

# Import existing v1.4 DEBUG fixes first (CSV import, spec order, scroll panel,
# in-cell editing, and safe duplicate handling), then extend its application.
import engineering_chart_analyzer_v14_debug as v14
import engineering_chart_analyzer as app_module
import engineering_charts as chart_logic

VERSION = "1.6 DEBUG"
app_module.BytesIO = BytesIO  # Also fixes the previous BytesIO NameError.


def _get_specs(window, columns, usl, target, lsl):
    mode = "Multi Spec" if window.multi_mode.isChecked() else "Single Spec"
    return chart_logic.spec_limits_for_columns(columns, mode, usl, target, lsl, window._spec_rows())


def render_v16_chart(data, columns, chart_type, *, group_column="", id_column="", usl=None,
                     lsl=None, target=None, highlight_oos=True, sample_limit=500,
                     figure=None, spec_ranges=None, spec_mode="Single Spec", **kwargs):
    """Use measurement columns as X categories and numeric measurements as Y."""
    columns = list(columns)
    if not columns:
        raise ValueError("Select at least one numeric measurement column.")
    values = data[columns].apply(pd.to_numeric, errors="coerce")
    specs = chart_logic.spec_limits_for_columns(columns, spec_mode, usl, target, lsl, spec_ranges)
    failed = pd.Series(False, index=data.index, dtype=bool)
    for spec in specs:
        segment = values.iloc[:, spec["start_index"]:spec["end_index"] + 1]
        if spec["USL"] is not None:
            failed |= segment.gt(spec["USL"]).any(axis=1)
        if spec["LSL"] is not None:
            failed |= segment.lt(spec["LSL"]).any(axis=1)

    fig = figure or Figure(figsize=(13, 8), dpi=160)
    fig.clear()
    ax = fig.add_subplot(111)
    x = np.arange(len(columns))
    labels = data[group_column].astype("object").where(data[group_column].notna(), "(blank)").astype(str) if group_column in data else None

    if chart_type == "Multi-Line Trend Chart":
        indices = np.arange(len(data))
        if len(indices) > sample_limit:
            indices = indices[np.linspace(0, len(indices)-1, sample_limit, dtype=int)]
        for idx in indices:
            is_fail = bool(failed.iloc[idx])
            ax.plot(x, values.iloc[idx].to_numpy(dtype=float),
                    color="#d62728" if highlight_oos and is_fail else "#477de0",
                    alpha=.95 if is_fail else .35, linewidth=1.6 if is_fail else .7)
        ax.set_xticks(x, columns, rotation=70, ha="right")
        ax.set_xlabel("Measurement point")
        ax.set_ylabel("Measurement value")
    elif chart_type == "Box Plot by Vendor":
        # One numeric distribution per selected measurement point. This matches
        # the multi-line chart's measurement-point X axis and value Y axis.
        distributions = [values[column].dropna().to_numpy(dtype=float) for column in columns]
        ax.boxplot(distributions, positions=x, tick_labels=columns, showfliers=True)
        ax.set_xticks(x, columns, rotation=70, ha="right")
        ax.set_xlabel("Measurement point")
        ax.set_ylabel("Measurement value")
    elif chart_type in ("Vendor Comparison Chart", "Average Trend Chart"):
        if chart_type == "Vendor Comparison Chart" and labels is not None:
            for name in labels.unique():
                if name != "(blank)":
                    ax.plot(x, values.loc[labels.eq(name)].mean(axis=0), marker="o", label=str(name))
            ax.legend(title=group_column)
        else:
            ax.plot(x, values.mean(axis=0), marker="o", label="Mean")
        ax.set_xticks(x, columns, rotation=70, ha="right")
        ax.set_xlabel("Measurement point")
        ax.set_ylabel("Measurement value")
    elif chart_type == "Histogram":
        ax.hist(values.to_numpy().ravel(), bins="fd", color="#4472c4", alpha=.8)
        ax.set_xlabel("Measurement value")
        ax.set_ylabel("Frequency")
    elif chart_type == "Scatter Plot":
        if len(columns) < 2:
            raise ValueError("Select at least two measurements for scatter plot.")
        ax.scatter(values.iloc[:, 0], values.iloc[:, 1], c=np.where(failed, "#d62728", "#477de0"), alpha=.65)
        ax.set_xlabel(columns[0] + " value")
        ax.set_ylabel(columns[1] + " value")
    elif chart_type == "Control/SPC Chart":
        series = values.iloc[:, 0].to_numpy(dtype=float)
        mean = float(np.nanmean(series)) if np.isfinite(series).any() else np.nan
        sd = float(np.nanstd(series, ddof=1)) if np.isfinite(series).sum() > 1 else np.nan
        ax.plot(np.arange(len(series)), series, color="#477de0", linewidth=.8)
        ax.axhline(mean, color="green", label="Center")
        if np.isfinite(sd):
            ax.axhline(mean+3*sd, color="#d62728", linestyle="--", label="UCL")
            ax.axhline(mean-3*sd, color="#d62728", linestyle="--", label="LCL")
        ax.set_xlabel(id_column or "Unit/row")
        ax.set_ylabel(columns[0] + " value")
        ax.legend()
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")

    if chart_type not in ("Histogram", "Scatter Plot", "Control/SPC Chart"):
        chart_logic._draw_specs(ax, columns, specs)
    vendor_title = group_column or "All units"
    ax.set_title(f"{chart_type} — {vendor_title}")
    ax.grid(alpha=.2)
    fig.tight_layout()
    return fig


def render_v16_facet(data, columns, *, vendor_column, facet_column="", usl=None, lsl=None,
                     target=None, sample_limit=350, figure=None, vendor_values=None,
                     facet_values=None, highlight_oos=True, spec_ranges=None,
                     spec_mode="Single Spec", **kwargs):
    columns = list(columns)
    vals = data[columns].apply(pd.to_numeric, errors="coerce")
    vendor_labels = data[vendor_column].astype("object").where(data[vendor_column].notna(), "(blank)").astype(str)
    facet_labels = (data[facet_column].astype("object").where(data[facet_column].notna(), "(blank)").astype(str)
                    if facet_column and facet_column in data else pd.Series("All units", index=data.index))
    vendors = list(vendor_values) if vendor_values is not None else [x for x in vendor_labels.unique() if x != "(blank)"]
    facets = list(facet_values) if facet_values is not None else [x for x in facet_labels.unique() if x != "(blank)"]
    vendors = vendors[:8] or ["(no selected vendors)"]
    facets = facets[:8] or ["(no selected breakdowns)"]
    specs = chart_logic.spec_limits_for_columns(columns, spec_mode, usl, target, lsl, spec_ranges)
    failed = pd.Series(False, index=data.index, dtype=bool)
    for spec in specs:
        segment = vals.iloc[:, spec["start_index"]:spec["end_index"]+1]
        if spec["USL"] is not None: failed |= segment.gt(spec["USL"]).any(axis=1)
        if spec["LSL"] is not None: failed |= segment.lt(spec["LSL"]).any(axis=1)
    fig = figure or Figure(figsize=(14, 8), dpi=160)
    fig.clear()
    axes = fig.subplots(len(facets), len(vendors), squeeze=False, sharex=True, sharey=True)
    x = np.arange(len(columns))
    for row, facet in enumerate(facets):
        for col, vendor in enumerate(vendors):
            ax = axes[row, col]
            mask = vendor_labels.eq(vendor) & facet_labels.eq(facet)
            ids = np.flatnonzero(mask.to_numpy())
            if len(ids) > sample_limit:
                ids = ids[np.linspace(0, len(ids)-1, sample_limit, dtype=int)]
            for idx in ids:
                is_fail = bool(failed.iloc[idx])
                ax.plot(x, vals.iloc[idx].to_numpy(dtype=float),
                        color="#d62728" if highlight_oos and is_fail else "#477de0",
                        linewidth=1.6 if is_fail else .7, alpha=.95 if is_fail else .35)
            chart_logic._draw_specs(ax, columns, specs)
            ax.set_title(f"{vendor_column}: {vendor}", fontsize=9, fontweight="bold")
            ax.grid(alpha=.2)
            if col == 0:
                ax.set_ylabel(f"{facet_column or 'Breakdown'}: {facet}\nMeasurement value")
            if row == len(facets)-1:
                ax.set_xticks(x, columns, rotation=70, ha="right", fontsize=7)
                ax.set_xlabel("Measurement point")
    fig.suptitle(f"Measurement by {vendor_column}" + (f" / {facet_column}" if facet_column else ""), fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, .95))
    return fig


# Patch core functions before the UI calls its imported references.
chart_logic.render_chart = render_v16_chart
chart_logic.render_facet_chart = render_v16_facet
app_module.render_chart = render_v16_chart
app_module.render_facet_chart = render_v16_facet


_original_init = app_module.EngineeringChartWindow.__init__


def _v16_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.setWindowTitle(f"Engineering Chart Analyzer — {VERSION}")
    self.version.setText(f"version {VERSION} - designed and developed by Hiro Nguyen")
    # Keep fail-list pane visible even when there are no failing units.
    self.fail_table.setVisible(True)
    self.fail_title.setVisible(True)
    self.fail_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    self.summary_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    self.fail_table.setMinimumHeight(90)
    self.summary_table.setMinimumHeight(90)
    self.columns.setMinimumHeight(170)
    self.columns.setMinimumWidth(390)
    self.vendor_values.setMinimumHeight(95)
    self.facet_values.setMinimumHeight(95)

    # Replace the chart/table area with a vertical splitter for adjustable space.
    horizontal = self.findChildren(QSplitter)[0]
    right = horizontal.widget(1)
    layout = right.layout()
    chart_index = layout.indexOf(self.canvas)
    if chart_index >= 0:
        layout.removeWidget(self.canvas)
        table_box = QFrame()
        table_layout = QHBoxLayout(table_box)
        for widget in (self.summary_table, self.fail_table):
            widget.setParent(None)
        summary_box = QVBoxLayout()
        self.vendor_summary_title = QLabel("Vendor commonality")
        summary_box.addWidget(self.vendor_summary_title)
        summary_box.addWidget(self.summary_table)
        fail_box = QVBoxLayout()
        fail_box.addWidget(self.fail_title)
        fail_box.addWidget(self.fail_table)
        table_layout.addLayout(summary_box, 2)
        table_layout.addLayout(fail_box, 1)
        self.preview_splitter = QSplitter(Qt.Orientation.Vertical)
        self.preview_splitter.addWidget(self.canvas)
        self.preview_splitter.addWidget(table_box)
        self.preview_splitter.setStretchFactor(0, 4)
        self.preview_splitter.setStretchFactor(1, 2)
        layout.insertWidget(chart_index, self.preview_splitter, 4)

    # Hide unused Single Spec fields in Multi Spec and hide table in Single Spec.
    form = self.spec_table.parentWidget().layout()
    self._multi_spec_labels = []
    for control in (self.usl, self.target, self.lsl):
        label = form.labelForField(control) if form else None
        self._multi_spec_labels.append((control, label))
    self._spec_table_label = form.labelForField(self.spec_table) if form else None
    self._spec_buttons_widget = self._spec_buttons[0].parentWidget()
    self._apply_v16_spec_visibility()
    self.single_mode.toggled.connect(lambda *_: self._apply_v16_spec_visibility())
    self.multi_mode.toggled.connect(lambda *_: self._apply_v16_spec_visibility())

    self.zoom_in_button = QPushButton("Zoom +")
    self.zoom_out_button = QPushButton("Zoom −")
    self.zoom_reset_button = QPushButton("Reset zoom")
    self.zoom_in_button.clicked.connect(lambda: self._v16_zoom(0.8))
    self.zoom_out_button.clicked.connect(lambda: self._v16_zoom(1.25))
    self.zoom_reset_button.clicked.connect(self._v16_zoom_reset)
    self.prev.parentWidget().layout().addWidget(self.zoom_in_button)
    self.prev.parentWidget().layout().addWidget(self.zoom_out_button)
    self.prev.parentWidget().layout().addWidget(self.zoom_reset_button)
    self.canvas.mpl_connect("scroll_event", self._v16_scroll_zoom)
    self._v16_image_axis = None


def _apply_v16_spec_visibility(self):
    multi = self.multi_mode.isChecked()
    for control, label in getattr(self, "_multi_spec_labels", []):
        control.setVisible(not multi)
        if label: label.setVisible(not multi)
    self.spec_table.setVisible(multi)
    if getattr(self, "_spec_table_label", None): self._spec_table_label.setVisible(multi)
    if getattr(self, "_spec_buttons_widget", None): self._spec_buttons_widget.setVisible(multi)


def _v16_render_page(self):
    if not getattr(self, "_chart_names", []): return
    name = self._chart_names[self._page]
    self.figure.clear()
    source = self._chart_figures[name]
    # Rasterize at high resolution for a crisp, scalable preview.
    buf = BytesIO()
    source.savefig(buf, format="png", dpi=240, bbox_inches="tight")
    buf.seek(0)
    import matplotlib.image as mpimg
    ax = self.figure.add_subplot(111)
    ax.imshow(mpimg.imread(buf), interpolation="lanczos")
    ax.axis("off")
    self._v16_image_axis = ax
    self.canvas.draw_idle()
    self.page_label.setText(f"Chart {self._page+1} / {len(self._chart_names)} — {name}")


def _v16_zoom(self, scale):
    ax = getattr(self, "_v16_image_axis", None)
    if ax is None: return
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    cx, cy = sum(xlim)/2, sum(ylim)/2
    half_x=(xlim[1]-xlim[0])*scale/2; half_y=(ylim[1]-ylim[0])*scale/2
    ax.set_xlim(cx-half_x,cx+half_x); ax.set_ylim(cy-half_y,cy+half_y)
    self.canvas.draw_idle()


def _v16_zoom_reset(self):
    if getattr(self,"_v16_image_axis",None) is not None:
        self._v16_image_axis.set_xlim(-.5, self._v16_image_axis.images[0].get_array().shape[1]-.5)
        self._v16_image_axis.set_ylim(self._v16_image_axis.images[0].get_array().shape[0]-.5, -.5)
        self.canvas.draw_idle()


def _v16_scroll_zoom(self,event):
    if event.inaxes is None or event.inaxes is not getattr(self,"_v16_image_axis",None): return
    scale=.8 if event.button=="up" else 1.25
    ax=event.inaxes; xlim=ax.get_xlim();ylim=ax.get_ylim();cx=event.xdata;cy=event.ydata
    ax.set_xlim(cx+(xlim[0]-cx)*scale,cx+(xlim[1]-cx)*scale)
    ax.set_ylim(cy+(ylim[0]-cy)*scale,cy+(ylim[1]-cy)*scale)
    self.canvas.draw_idle()


def _v16_build_charts(self):
    _original_build(self)
    # Keep the separate pane visible whether or not any rows currently fail.
    self.fail_table.setVisible(True)
    self.fail_title.setVisible(True)
    vendor = self.vendor_column.currentText() or "(not selected)"
    facet = self.facet_column.currentText() or "All units"
    self.vendor_summary_title.setText(f"Vendor value: {vendor}    |    Breakdown value: {facet}")


_original_build = app_module.EngineeringChartWindow.build_charts
app_module.EngineeringChartWindow.__init__ = _v16_init
app_module.EngineeringChartWindow._apply_v16_spec_visibility = _apply_v16_spec_visibility
app_module.EngineeringChartWindow._v16_render_page = _v16_render_page
app_module.EngineeringChartWindow._render_page = _v16_render_page
app_module.EngineeringChartWindow._v16_zoom = _v16_zoom
app_module.EngineeringChartWindow._v16_zoom_reset = _v16_zoom_reset
app_module.EngineeringChartWindow._v16_scroll_zoom = _v16_scroll_zoom
app_module.EngineeringChartWindow.build_charts = _v16_build_charts


def _round_frame(frame):
    if frame is None or not isinstance(frame, pd.DataFrame): return frame
    result=frame.copy()
    for col in result.select_dtypes(include="number").columns:
        result[col]=result[col].round(2)
    return result


_original_pdf=app_module.export_pdf_report
_original_excel=app_module.export_engineering_charts

def _pdf_rounded(*args,**kwargs):
    args=list(args)
    if len(args)>2: args[2]=_round_frame(args[2])
    if len(args)>5: args[5]=_round_frame(args[5])
    for key in ("summary","stats","failures"):
        if key in kwargs:kwargs[key]=_round_frame(kwargs[key])
    return _original_pdf(*args,**kwargs)

def _excel_rounded(*args,**kwargs):
    args=list(args)
    for index in (2,4,5):
        if len(args)>index:args[index]=_round_frame(args[index])
    for key in ("failures","mapped_data","spec_analysis","stats","vendors"):
        if key in kwargs:kwargs[key]=_round_frame(kwargs[key])
    return _original_excel(*args,**kwargs)

app_module.export_pdf_report=_pdf_rounded
app_module.export_engineering_charts=_excel_rounded

_original_save_report=app_module.EngineeringChartWindow._save_report

def _save_report_with_open_prompt(self,kind):
    _original_save_report(self,kind)
    message=self.status.text()
    prefix="Report exported: "
    if message.startswith(prefix):
        path=message[len(prefix):].strip()
        answer=QMessageBox.question(self,"Open exported report?",f"Open the report now?\n{path}",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

app_module.EngineeringChartWindow._save_report=_save_report_with_open_prompt


def main():
    app=QApplication(sys.argv)
    window=app_module.EngineeringChartWindow()
    window.show()
    return app.exec()

if __name__=="__main__":
    raise SystemExit(main())
