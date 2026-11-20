"""Launch v1.4 with the three requested DEBUG UI/spec fixes and safe deduplication."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QFileDialog, QScrollArea, QSplitter, QTableWidget, QTableWidgetItem

import engineering_charts as chart_logic
from deduplication_fix import deduplicate_units


def validate_spec_ranges(spec_rows, categories):
    """Validate overlap by X-axis positions, not by CSV row order."""
    categories = list(categories)
    positions = {str(value): i for i, value in enumerate(categories)}
    populated = []
    for row in spec_rows:
        start = str(row.get("Start Point", "")).strip()
        end = str(row.get("End Point", "")).strip()
        if not start or not end:
            continue
        if start not in positions or end not in positions:
            raise ValueError(f"Spec range points must exist on the X-axis: {start} – {end}.")
        if positions[start] > positions[end]:
            raise ValueError(f"Start Point must not come after End Point on the selected X-axis: {start} – {end}.")
        populated.append(row)
    populated.sort(key=lambda row: positions[str(row["Start Point"]).strip()])
    return _original_validate_spec_ranges(populated, categories)


_original_validate_spec_ranges = chart_logic.validate_spec_ranges
chart_logic.validate_spec_ranges = validate_spec_ranges
# Patch before the application imports its function reference.
chart_logic.deduplicate_units = deduplicate_units

import engineering_chart_analyzer as application


def _read_specs_csv(self):
    path, _ = QFileDialog.getOpenFileName(self, "Import spec CSV", "", "CSV (*.csv)")
    if not path:
        return
    try:
        first_line = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()[0]
        separator = max((",", ";", "\t"), key=lambda candidate: first_line.count(candidate))
        frame = pd.read_csv(path, sep=separator, decimal="," if separator == ";" else ".", encoding="utf-8-sig")
        frame.columns = [str(column).strip() for column in frame.columns]
        required = ["Start Point", "End Point", "USL", "Target", "LSL"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError("CSV missing columns: " + ", ".join(missing))
        self.spec_table.setRowCount(len(frame))
        for row_index, (_, record) in enumerate(frame.iterrows()):
            for column_index, name in enumerate(required):
                value = record[name]
                self.spec_table.setItem(row_index, column_index, QTableWidgetItem("" if pd.isna(value) else str(value)))
        self._progress(100, f"Imported {len(frame)} spec ranges; row order will be matched to the selected X-axis.")
    except Exception as exc:
        self._error(str(exc))


_original_init = application.EngineeringChartWindow.__init__


def _init_with_debug_fixes(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    splitters = self.findChildren(QSplitter)
    if splitters:
        splitter = splitters[0]
        controls = splitter.widget(0)
        if controls is not None:
            scroll = QScrollArea(self)
            scroll.setObjectName("inputControlsScrollArea")
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setMinimumWidth(390)
            controls.setParent(None)
            scroll.setWidget(controls)
            splitter.insertWidget(0, scroll)
            self.input_scroll_area = scroll
    for table in self.findChildren(QTableWidget):
        if table.columnCount() == 5:
            table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed | QAbstractItemView.EditTrigger.AnyKeyPressed)
            table.setTabKeyNavigation(True)
            table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


application.EngineeringChartWindow.__init__ = _init_with_debug_fixes
application.EngineeringChartWindow.import_specs = _read_specs_csv


def main():
    app = QApplication(sys.argv)
    window = application.EngineeringChartWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
