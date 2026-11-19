"""Engineering Chart Analyzer with unit mapping and vendor breakdown."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QInputDialog, QProgressBar,
)

from engineering_charts import (
    CHART_TYPES, analyze_measurements, auto_map_units, dashboard_findings,
    detect_group_column, detect_key_column, export_engineering_charts,
    export_pdf_report, numeric_columns, render_chart, render_facet_chart,
    vendor_commonality_summary,
)

VERSION_TEXT = "version 1.3 - designed and developed by Hiro Nguyen"


class EngineeringChartWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Engineering Chart Analyzer")
        self.resize(1500, 950)
        self.measurement_data = None
        self.mapping_data = None
        self.data = None
        self.mapping_info = None
        self.workbook_path = None
        self.mapping_path = None
        self._last_stats = None
        self._last_overall = None
        self._last_summary = pd.DataFrame()

        root = QVBoxLayout(self)
        files = QHBoxLayout()
        self.data_label = QLabel("Measurement workbook: not loaded")
        self.mapping_label = QLabel("Mapping workbook: optional")
        open_data = QPushButton("Open measurements…")
        open_data.clicked.connect(self.open_measurements)
        open_mapping = QPushButton("Open unit mapping…")
        open_mapping.clicked.connect(self.open_mapping)
        files.addWidget(open_data); files.addWidget(self.data_label, 1)
        files.addWidget(open_mapping); files.addWidget(self.mapping_label, 1)
        root.addLayout(files)

        split = QSplitter(Qt.Orientation.Horizontal)
        controls = QWidget(); form = QFormLayout(controls)
        self.unit_key = QComboBox(); self.mapping_key = QComboBox()
        self.vendor_column = QComboBox(); self.facet_column = QComboBox()
        self.chart_type = QComboBox(); self.chart_type.addItems(CHART_TYPES)
        self.columns = QListWidget(); self.columns.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.numeric_search = QLineEdit(); self.numeric_search.setPlaceholderText("Filter measurement columns…")
        self.numeric_search.textChanged.connect(self.filter_numeric_columns)
        self.vendor_values = QListWidget(); self.vendor_values.setMaximumHeight(95)
        self.facet_values = QListWidget(); self.facet_values.setMaximumHeight(95)
        self.usl = QLineEdit(); self.target = QLineEdit(); self.lsl = QLineEdit()
        self.sample = QLineEdit("350")
        self.fuzzy_enabled = QCheckBox("Allow similar (fuzzy) unit-key matches")
        self.fuzzy_threshold = QComboBox(); self.fuzzy_threshold.addItems(["80", "85", "90", "95", "98"]); self.fuzzy_threshold.setCurrentText("90")

        form.addRow("Unit/serial key in data", self.unit_key)
        form.addRow("Unit/serial key in mapping", self.mapping_key)
        form.addRow(self.fuzzy_enabled)
        form.addRow("Fuzzy match threshold (%)", self.fuzzy_threshold)
        self.map_button = QPushButton("Auto-map units before charting")
        self.map_button.clicked.connect(self.run_mapping)
        form.addRow(self.map_button)
        form.addRow("Break down columns by vendor", self.vendor_column)
        form.addRow("Select vendor values (blank included)", self.vendor_values)
        form.addRow("Break down rows by (optional)", self.facet_column)
        form.addRow("Select breakdown values (blank included)", self.facet_values)
        form.addRow("Chart type", self.chart_type)
        form.addRow("Filter numeric columns", self.numeric_search)
        form.addRow("Numeric measurement columns", self.columns)
        form.addRow("USL", self.usl); form.addRow("Target / nominal", self.target); form.addRow("LSL", self.lsl)
        form.addRow("Max lines per panel", self.sample)
        buttons = QHBoxLayout()
        self.build_button = QPushButton("Build chart"); self.build_button.clicked.connect(self.build_chart)
        png = QPushButton("Save PNG…"); png.clicked.connect(self.save_png)
        pdf = QPushButton("Save PDF…"); pdf.clicked.connect(self.save_pdf)
        excel = QPushButton("Export Excel…"); excel.clicked.connect(self.export_excel)
        reset = QPushButton("Start over"); reset.clicked.connect(self.start_over)
        for button in (self.build_button, png, pdf, excel, reset): buttons.addWidget(button)
        form.addRow(buttons)
        split.addWidget(controls)

        right = QWidget(); right_layout = QVBoxLayout(right)
        self.figure = Figure(figsize=(12, 7)); self.canvas = FigureCanvasQTAgg(self.figure)
        right_layout.addWidget(NavigationToolbar2QT(self.canvas, self)); right_layout.addWidget(self.canvas, 4)
        self.table = QTableWidget(); self.table.setMaximumHeight(210)
        right_layout.addWidget(QLabel("Vendor Pass/Fail commonality summary")); right_layout.addWidget(self.table)
        self.findings = QLabel("Load data to begin."); self.findings.setWordWrap(True); right_layout.addWidget(self.findings)
        split.addWidget(right); split.setStretchFactor(1, 1); root.addWidget(split)

        status_row = QHBoxLayout()
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        self.status = QLabel("Choose measurement data.")
        self.version = QLabel(VERSION_TEXT); self.version.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self.progress); status_row.addWidget(self.status, 3); status_row.addWidget(self.version, 2)
        root.addLayout(status_row)

        self.vendor_column.currentTextChanged.connect(self._refresh_value_filters)
        self.facet_column.currentTextChanged.connect(self._refresh_value_filters)
        for combo in (self.unit_key, self.mapping_key, self.chart_type):
            combo.currentTextChanged.connect(self._mark_ready)
        for field in (self.usl, self.target, self.lsl, self.sample): field.editingFinished.connect(self._mark_ready)
        self.columns.itemSelectionChanged.connect(self._mark_ready)

    @staticmethod
    def _read_workbook(parent, title):
        path, _ = QFileDialog.getOpenFileName(parent, title, "", "Excel workbooks (*.xlsx *.xlsm)")
        if not path: return None, None
        sheets = pd.ExcelFile(path).sheet_names
        sheet, ok = QInputDialog.getItem(parent, "Select worksheet", "Worksheet:", sheets, 0, False)
        if not ok: return None, None
        return Path(path), pd.read_excel(path, sheet_name=sheet)

    def _progress(self, value: int, text: str):
        self.progress.setValue(value); self.status.setText(text); QApplication.processEvents()

    def _error(self, text: str):
        self.progress.setValue(0); self.status.setText(f"ERROR — {text}")
        QMessageBox.critical(self, "Engineering Chart Analyzer error", text)

    def open_measurements(self):
        try:
            self._progress(5, "Loading measurement workbook…")
            path, frame = self._read_workbook(self, "Open measurement workbook")
            if frame is None: self._progress(0, "Measurement loading cancelled."); return
            self.workbook_path = path; self.measurement_data = frame; self.data = frame.copy()
            self.data_label.setText(path.name); self._refresh_controls()
            self._progress(100, f"Loaded {len(frame):,} measurement rows successfully.")
        except Exception as exc: self._error(str(exc))

    def open_mapping(self):
        try:
            self._progress(5, "Loading unit mapping workbook…")
            path, frame = self._read_workbook(self, "Open unit/vendor mapping workbook")
            if frame is None: self._progress(0, "Mapping loading cancelled."); return
            self.mapping_path = path; self.mapping_data = frame; self.mapping_label.setText(path.name)
            self._refresh_controls(); self._progress(100, f"Loaded mapping workbook ({len(frame):,} rows).")
        except Exception as exc: self._error(str(exc))

    @staticmethod
    def _fill_combo(combo, names, selected=""):
        combo.blockSignals(True); combo.clear(); combo.addItem(""); combo.addItems(names)
        if selected in names: combo.setCurrentText(selected)
        combo.blockSignals(False)

    def _refresh_controls(self):
        unit_names = [str(c) for c in self.measurement_data.columns] if self.measurement_data is not None else []
        map_names = [str(c) for c in self.mapping_data.columns] if self.mapping_data is not None else []
        self._fill_combo(self.unit_key, unit_names, detect_key_column(self.measurement_data) or "")
        self._fill_combo(self.mapping_key, map_names, detect_key_column(self.mapping_data) or "")
        frame = self.data if self.data is not None else self.measurement_data
        if frame is None: return
        names = [str(c) for c in frame.columns]
        vendor_guess = detect_group_column(frame) or ""
        self._fill_combo(self.vendor_column, names, vendor_guess)
        facet_options = [n for n in names if _facet_candidate(n)]
        self._fill_combo(self.facet_column, names, facet_options[0] if facet_options else "")
        self._populate_numeric_columns()
        self._refresh_value_filters()

    def _populate_numeric_columns(self):
        if self.data is None: return
        selected = set(self.selected_columns()) if hasattr(self, "columns") else set()
        query = self.numeric_search.text().casefold().strip()
        self.columns.blockSignals(True); self.columns.clear()
        for name in numeric_columns(self.data):
            if query and query not in name.casefold(): continue
            item = QListWidgetItem(name); self.columns.addItem(item)
            if name in selected: item.setSelected(True)
        self.columns.blockSignals(False)

    def filter_numeric_columns(self, _text): self._populate_numeric_columns()

    def selected_columns(self): return [item.text() for item in self.columns.selectedItems()]

    def _fill_checklist(self, widget, values):
        previous = {widget.item(i).text(): widget.item(i).checkState() for i in range(widget.count())}
        widget.blockSignals(True); widget.clear()
        for value in values:
            item = QListWidgetItem(value); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(previous.get(value, Qt.CheckState.Checked)); widget.addItem(item)
        widget.blockSignals(False)

    def _refresh_value_filters(self, *_):
        if self.data is None: return
        vendor_col = self.vendor_column.currentText(); facet_col = self.facet_column.currentText()
        if vendor_col and vendor_col in self.data:
            vals = sorted(_safe_labels(self.data[vendor_col]).unique().tolist())
            self._fill_checklist(self.vendor_values, vals)
        else: self._fill_checklist(self.vendor_values, [])
        if facet_col and facet_col in self.data:
            vals = sorted(_safe_labels(self.data[facet_col]).unique().tolist())
            self._fill_checklist(self.facet_values, vals)
        else: self._fill_checklist(self.facet_values, [])

    @staticmethod
    def _checked(widget):
        return [widget.item(i).text() for i in range(widget.count()) if widget.item(i).checkState() == Qt.CheckState.Checked]

    def run_mapping(self):
        if self.measurement_data is None: self._error("Load the measurement workbook first."); return
        if self.mapping_data is None: self._error("Load the unit mapping workbook first."); return
        try:
            self._progress(10, "Matching unit/serial keys…")
            key = self.unit_key.currentText() or detect_key_column(self.measurement_data)
            map_key = self.mapping_key.currentText() or detect_key_column(self.mapping_data)
            if not key or not map_key: raise ValueError("Choose the unit serial key in both worksheets.")
            self.data, self.mapping_info = auto_map_units(
                self.measurement_data, self.mapping_data, key, map_key,
                fuzzy=self.fuzzy_enabled.isChecked(), fuzzy_threshold=int(self.fuzzy_threshold.currentText()))
            self._progress(75, "Preparing vendor and breakdown filters…")
            self._refresh_controls()
            self._progress(100, f"Mapping complete: {self.mapping_info['matched_rows']:,}/{self.mapping_info['unit_rows']:,} units matched ({self.mapping_info['match_rate_pct']:.1f}%; fuzzy matches {self.mapping_info['fuzzy_matches']:,}).")
        except Exception as exc: self._error(str(exc))

    @staticmethod
    def _number(field):
        text = field.text().strip()
        if not text: return None
        value = float(text)
        if not np.isfinite(value): raise ValueError("Spec values must be finite numbers.")
        return value

    def build_chart(self):
        if self.data is None: self._error("Load measurement data before building a chart."); return
        columns = self.selected_columns()
        if not columns: self._error("Select one or more numeric measurement columns."); return
        try:
            self._progress(5, "Validating selections…")
            usl, target, lsl = self._number(self.usl), self._number(self.target), self._number(self.lsl)
            group = self.vendor_column.currentText(); facet = self.facet_column.currentText()
            vendor_selection = self._checked(self.vendor_values)
            facet_selection = self._checked(self.facet_values)
            filtered = self.data.copy()
            if group and group in filtered:
                labels = _safe_labels(filtered[group]); filtered = filtered.loc[labels.isin(vendor_selection)]
            if facet and facet in filtered and facet_selection:
                labels = _safe_labels(filtered[facet]); filtered = filtered.loc[labels.isin(facet_selection)]
            if filtered.empty: raise ValueError("The selected vendor/facet filters leave no rows to chart.")
            self._progress(30, "Generating chart…")
            limit = max(25, int(self.sample.text() or 350))
            if group and self.chart_type.currentText() == "Multi-Line Trend Chart":
                render_facet_chart(filtered, columns, vendor_column=group, facet_column=facet,
                    usl=usl, lsl=lsl, target=target, sample_limit=limit, figure=self.figure,
                    vendor_values=vendor_selection, facet_values=facet_selection, highlight_oos=True)
            else:
                render_chart(filtered, columns, self.chart_type.currentText(), group_column=group,
                    id_column=self.unit_key.currentText(), usl=usl, lsl=lsl, target=target,
                    sample_limit=limit, figure=self.figure)
            self.canvas.draw(); self._progress(65, "Calculating unit-level Pass/Fail vendor commonality…")
            stats, overall = analyze_measurements(filtered, columns, usl, lsl)
            summary = vendor_commonality_summary(filtered, columns, group, facet, usl, lsl)
            self._show_table(summary)
            findings = dashboard_findings(filtered, columns, group, usl, lsl)
            self.findings.setText("\n".join(f"{r.Finding}: {r.Category} ({r.Count:,})" for r in findings.itertuples()) or "No out-of-spec units detected (or no spec limits entered).")
            self._last_stats, self._last_overall, self._last_summary, self._chart_data = stats, overall, summary, filtered
            self._last_specs = (usl, target, lsl)
            self._progress(100, f"Chart ready — {len(filtered):,} units, {len(columns)} measurements, {len(summary)} vendor/facet rows.")
        except Exception as exc: self._error(str(exc))

    def _mark_ready(self, *_):
        if self.data is not None: self.status.setText("Selections changed. Click Build chart to apply them.")

    def _show_table(self, frame):
        self.table.clear(); self.table.setRowCount(min(200, len(frame))); self.table.setColumnCount(len(frame.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        for i, row in enumerate(frame.head(200).itertuples(index=False, name=None)):
            for j, value in enumerate(row):
                if pd.isna(value): text = ""
                elif isinstance(value, (float, np.floating)): text = f"{value:,.2f}%" if "%" in str(frame.columns[j]) else f"{value:,.3f}"
                else: text = str(value)
                self.table.setItem(i, j, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

    def _confirm_export(self, kind):
        answer = QMessageBox.question(self, "Confirm report export",
            f"Export the current chart and vendor summary as {kind}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Yes

    def save_png(self):
        if self._last_stats is None: self._error("Build a chart before saving PNG."); return
        path, _ = QFileDialog.getSaveFileName(self, "Save chart image", "EngineeringChart.png", "PNG image (*.png)")
        if not path: self.status.setText("PNG export cancelled."); return
        try:
            self._progress(20, "Saving chart image…"); self.figure.savefig(path, format="png", dpi=160, bbox_inches="tight")
            self._progress(100, f"Chart image saved: {path}")
        except Exception as exc: self._error(str(exc))

    def save_pdf(self):
        if self._last_stats is None: self._error("Build a chart before creating a PDF report."); return
        if not self._confirm_export("PDF report"): self.status.setText("PDF report export cancelled."); return
        path, _ = QFileDialog.getSaveFileName(self, "Save complete PDF report", "EngineeringReport.pdf", "PDF report (*.pdf)")
        if not path: self.status.setText("PDF report export cancelled."); return
        try:
            self._progress(20, "Building PDF report…")
            title = f"Engineering Chart Report — {self.vendor_column.currentText()}"
            output = export_pdf_report(path, self.figure, self._last_summary, self._last_overall, title)
            self._progress(100, f"Complete PDF report saved: {output}")
        except Exception as exc: self._error(str(exc))

    def export_excel(self):
        if self._last_stats is None: self._error("Build a chart before exporting Excel."); return
        if not self._confirm_export("Excel workbook"): self.status.setText("Excel export cancelled."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export chart, data and vendor summary", "EngineeringReport.xlsx", "Excel workbook (*.xlsx)")
        if not path: self.status.setText("Excel export cancelled."); return
        try:
            self._progress(15, "Writing chart, data, and vendor summary…")
            spec = pd.DataFrame([{"Metric": k, "Value": v} for k, v in self._last_overall.items() if k in ("Above USL", "Below LSL", "Pass", "Fail", "Yield %")])
            output = export_engineering_charts(path, self.figure, self._last_stats, self._last_overall,
                self._last_summary, spec, mapped_data=self._chart_data)
            self._progress(100, f"Excel report with chart, mapped data, and vendor commonality saved: {output}")
        except Exception as exc: self._error(str(exc))

    def start_over(self):
        self.measurement_data = self.mapping_data = self.data = self.mapping_info = None
        self.workbook_path = self.mapping_path = None
        self._last_stats = self._last_overall = None; self._last_summary = pd.DataFrame()
        self.data_label.setText("Measurement workbook: not loaded"); self.mapping_label.setText("Mapping workbook: optional")
        self.unit_key.clear(); self.mapping_key.clear(); self.vendor_column.clear(); self.facet_column.clear()
        self.columns.clear(); self.vendor_values.clear(); self.facet_values.clear(); self.numeric_search.clear()
        self.table.clear(); self.table.setRowCount(0); self.table.setColumnCount(0); self.findings.setText("Load data to begin.")
        self.figure.clear(); self.canvas.draw(); self.progress.setValue(0); self.status.setText("Reset complete. Load a measurement workbook to start over.")


def _safe_labels(series):
    return series.astype("object").where(series.notna(), "(blank)").astype(str)


def _facet_candidate(name: str) -> bool:
    folded = name.casefold().replace("_", " ")
    return folded in {"product", "build matrix", "bm", "station", "test", "measurement group", "trackpad"}


def main():
    app = QApplication(sys.argv)
    window = EngineeringChartWindow(); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
