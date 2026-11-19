"""Standalone Engineering Chart Analyzer with automatic unit-to-vendor mapping."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QInputDialog,
)

from engineering_charts import (
    CHART_TYPES, analyze_measurements, auto_map_units, dashboard_findings,
    detect_group_column, detect_key_column, export_engineering_charts,
    numeric_columns, render_chart, render_facet_chart, vendor_summary,
)


class EngineeringChartWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Engineering Chart Analyzer — Auto Mapping")
        self.resize(1500, 950)
        self.measurement_data = None
        self.mapping_data = None
        self.data = None
        self.mapping_info = None
        self.workbook_path = None
        self.mapping_path = None

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
        self.usl = QLineEdit(); self.target = QLineEdit(); self.lsl = QLineEdit()
        self.sample = QLineEdit("350")
        self.highlight = QCheckBox("Highlight failing units in red"); self.highlight.setChecked(True)
        form.addRow("Unit/serial key in data", self.unit_key)
        form.addRow("Unit/serial key in mapping", self.mapping_key)
        self.map_button = QPushButton("Auto-map units before charting")
        self.map_button.clicked.connect(self.run_mapping)
        form.addRow(self.map_button)
        form.addRow("Break down columns by vendor", self.vendor_column)
        form.addRow("Break down rows by (optional)", self.facet_column)
        form.addRow("Chart type", self.chart_type)
        form.addRow("Numeric measurement columns", self.columns)
        form.addRow("USL", self.usl); form.addRow("Target / nominal", self.target); form.addRow("LSL", self.lsl)
        form.addRow("Max lines per panel", self.sample); form.addRow(self.highlight)
        buttons = QHBoxLayout()
        refresh = QPushButton("Build chart"); refresh.clicked.connect(self.update_chart)
        png = QPushButton("Save PNG…"); png.clicked.connect(lambda: self.save_chart("png"))
        pdf = QPushButton("Save PDF…"); pdf.clicked.connect(lambda: self.save_chart("pdf"))
        export = QPushButton("Export Excel…"); export.clicked.connect(self.export_excel)
        for button in (refresh, png, pdf, export): buttons.addWidget(button)
        form.addRow(buttons)
        split.addWidget(controls)

        right = QWidget(); right_layout = QVBoxLayout(right)
        self.figure = Figure(figsize=(12, 7)); self.canvas = FigureCanvasQTAgg(self.figure)
        right_layout.addWidget(NavigationToolbar2QT(self.canvas, self)); right_layout.addWidget(self.canvas, 4)
        self.table = QTableWidget(); self.table.setMaximumHeight(190)
        right_layout.addWidget(QLabel("Vendor summary (ranked)")); right_layout.addWidget(self.table)
        self.findings = QLabel("Load data to begin."); self.findings.setWordWrap(True); right_layout.addWidget(self.findings)
        split.addWidget(right); split.setStretchFactor(1, 1); root.addWidget(split)
        self.status = QLabel("Choose measurement data. Optionally load a mapping workbook and auto-map SN/unit IDs to vendor metadata.")
        root.addWidget(self.status)
        for combo in (self.unit_key, self.mapping_key, self.vendor_column, self.facet_column, self.chart_type):
            combo.currentTextChanged.connect(self.update_chart)
        for field in (self.usl, self.target, self.lsl, self.sample): field.editingFinished.connect(self.update_chart)
        self.columns.itemSelectionChanged.connect(self.update_chart)

    @staticmethod
    def _read_workbook(parent, title):
        path, _ = QFileDialog.getOpenFileName(parent, title, "", "Excel workbooks (*.xlsx *.xlsm)")
        if not path: return None, None
        sheets = pd.ExcelFile(path).sheet_names
        sheet, ok = QInputDialog.getItem(parent, "Select worksheet", "Worksheet:", sheets, 0, False)
        if not ok: return None, None
        return Path(path), pd.read_excel(path, sheet_name=sheet)

    def open_measurements(self):
        path, frame = self._read_workbook(self, "Open measurement workbook")
        if frame is None: return
        self.workbook_path = path; self.measurement_data = frame; self.data = frame.copy()
        self.data_label.setText(path.name)
        self._refresh_controls()
        self.status.setText(f"Loaded {len(frame):,} measurement units. Add mapping workbook for vendor breakdown if needed.")
        self.update_chart()

    def open_mapping(self):
        path, frame = self._read_workbook(self, "Open unit/vendor mapping workbook")
        if frame is None: return
        self.mapping_path = path; self.mapping_data = frame
        self.mapping_label.setText(path.name)
        self._refresh_controls()
        self.run_mapping()

    def _fill_combo(self, combo, names, selected=""):
        combo.blockSignals(True); combo.clear(); combo.addItem(""); combo.addItems(names)
        if selected in names: combo.setCurrentText(selected)
        combo.blockSignals(False)

    def _refresh_controls(self):
        unit_names = [str(c) for c in self.measurement_data.columns] if self.measurement_data is not None else []
        map_names = [str(c) for c in self.mapping_data.columns] if self.mapping_data is not None else []
        old_unit, old_map = self.unit_key.currentText(), self.mapping_key.currentText()
        self._fill_combo(self.unit_key, unit_names, old_unit or (detect_key_column(self.measurement_data) if self.measurement_data is not None else ""))
        self._fill_combo(self.mapping_key, map_names, old_map or (detect_key_column(self.mapping_data) if self.mapping_data is not None else ""))
        frame = self.data if self.data is not None else self.measurement_data
        if frame is None: return
        names = [str(c) for c in frame.columns]
        old_vendor = self.vendor_column.currentText()
        guessed_vendor = detect_group_column(frame) or ""
        self._fill_combo(self.vendor_column, names, old_vendor if old_vendor in names else guessed_vendor)
        old_facet = self.facet_column.currentText()
        facet_candidates = [n for n in names if n.casefold() in {"product", "build matrix", "bm", "station", "test", "measurement group"}]
        self._fill_combo(self.facet_column, names, old_facet if old_facet in names else (facet_candidates[0] if facet_candidates else ""))
        self.columns.clear()
        for name in numeric_columns(frame): self.columns.addItem(name)

    def run_mapping(self):
        if self.measurement_data is None:
            self.status.setText("Load the measurement workbook first."); return
        if self.mapping_data is None:
            self.data = self.measurement_data.copy(); self.mapping_info = None
            self._refresh_controls(); self.update_chart()
            self.status.setText("No mapping workbook loaded; using columns already in measurement data.")
            return
        try:
            key = self.unit_key.currentText() or detect_key_column(self.measurement_data)
            map_key = self.mapping_key.currentText() or detect_key_column(self.mapping_data)
            if not key or not map_key:
                raise ValueError("Could not auto-detect a serial/unit key. Select both key columns from the dropdowns.")
            # Include all mapping metadata that is not already present, so Vendor/BM/Product can be grouped.
            self.data, self.mapping_info = auto_map_units(
                self.measurement_data, self.mapping_data, key, map_key
            )
            previous_vendor = self.vendor_column.currentText()
            self._refresh_controls()
            if previous_vendor in self.data.columns:
                self.vendor_column.setCurrentText(previous_vendor)
            else:
                guess = detect_group_column(self.data)
                if guess: self.vendor_column.setCurrentText(guess)
            self.status.setText(
                f"Auto-mapped {self.mapping_info['matched_rows']:,}/{self.mapping_info['unit_rows']:,} units "
                f"({self.mapping_info['match_rate_pct']:.1f}%). Mapped fields: "
                f"{', '.join(self.mapping_info['mapped_columns']) or 'none (already present)'}."
            )
            self.update_chart()
        except Exception as exc:
            QMessageBox.warning(self, "Auto mapping failed", str(exc))

    @staticmethod
    def _number(field):
        text = field.text().strip()
        if not text: return None
        value = float(text)
        if not np.isfinite(value): raise ValueError("Spec values must be finite numbers.")
        return value

    def selected_columns(self): return [item.text() for item in self.columns.selectedItems()]

    def update_chart(self, *_):
        if self.data is None: return
        columns = self.selected_columns()
        if not columns: return
        try:
            usl, target, lsl = self._number(self.usl), self._number(self.target), self._number(self.lsl)
            group = self.vendor_column.currentText()
            facet = self.facet_column.currentText()
            max_lines = max(25, int(self.sample.text() or 350))
            if group and self.chart_type.currentText() == "Multi-Line Trend Chart":
                render_facet_chart(self.data, columns, vendor_column=group, facet_column=facet,
                                   usl=usl, lsl=lsl, target=target, sample_limit=max_lines, figure=self.figure)
            else:
                render_chart(self.data, columns, self.chart_type.currentText(), group_column=group,
                             id_column=self.unit_key.currentText(), usl=usl, lsl=lsl, target=target,
                             sample_limit=max_lines, figure=self.figure)
            self.canvas.draw_idle()
            stats, overall = analyze_measurements(self.data, columns, usl, lsl)
            vendors = vendor_summary(self.data, columns, group, usl, lsl)
            self._show_table(vendors if not vendors.empty else stats)
            findings = dashboard_findings(self.data, columns, group, usl, lsl)
            messages = [f"{r.Finding}: {r.Category} ({r.Count:,})" for r in findings.itertuples()]
            self.findings.setText("\n".join(messages) if messages else "Enter USL/LSL to identify out-of-spec units.")
            self._last_stats, self._last_overall, self._last_vendors = stats, overall, vendors
            self.status.setText(f"{len(self.data):,} units · {len(columns)} measurement points · vendor panels: {group or 'none'} · facet rows: {facet or 'none'}")
        except Exception as exc:
            self.status.setText(str(exc))

    def _show_table(self, frame):
        self.table.clear(); self.table.setRowCount(min(100, len(frame))); self.table.setColumnCount(len(frame.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        for i, row in enumerate(frame.head(100).itertuples(index=False, name=None)):
            for j, value in enumerate(row):
                text = "" if pd.isna(value) else (f"{value:,.3f}" if isinstance(value, (float, np.floating)) else str(value))
                self.table.setItem(i, j, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

    def save_chart(self, fmt):
        path, _ = QFileDialog.getSaveFileName(self, f"Save {fmt.upper()}", f"EngineeringChart.{fmt}", f"{fmt.upper()} (*.{fmt})")
        if path:
            try: self.figure.savefig(path, format=fmt, dpi=160, bbox_inches="tight")
            except Exception as exc: QMessageBox.warning(self, "Save failed", str(exc))

    def export_excel(self):
        if self.data is None or not hasattr(self, "_last_stats"):
            QMessageBox.information(self, "Export", "Load data and select measurement columns first."); return
        path, _ = QFileDialog.getSaveFileName(self, "Export workbook", "Engineering_Charts.xlsx", "Excel workbook (*.xlsx)")
        if not path: return
        try:
            specs = pd.DataFrame([{"Metric": k, "Value": v} for k, v in self._last_overall.items() if k in ("Above USL", "Below LSL", "Pass", "Fail", "Yield %")])
            output = export_engineering_charts(path, self.figure, self._last_stats, self._last_overall,
                                               self._last_vendors, specs, mapped_data=self.data)
            QMessageBox.information(self, "Export complete", f"Saved mapped data and chart to:\n{output}")
        except Exception as exc: QMessageBox.warning(self, "Export failed", str(exc))


def main():
    app = QApplication(sys.argv)
    window = EngineeringChartWindow(); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
