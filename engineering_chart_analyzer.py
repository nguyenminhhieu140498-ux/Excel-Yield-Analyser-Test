"""Desktop Engineering Chart Analyzer."""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView,QApplication,QCheckBox,QComboBox,QDialog,QDialogButtonBox,QFileDialog,QFormLayout,QHBoxLayout,QLabel,QLineEdit,QListWidget,QListWidgetItem,QMessageBox,QPushButton,QRadioButton,QSpinBox,QSplitter,QTableWidget,QTableWidgetItem,QVBoxLayout,QWidget,QProgressBar)
from engineering_charts import (CHART_TYPES,analyze_measurements,auto_map_units,dashboard_findings,deduplicate_units,detect_group_column,detect_key_column,export_engineering_charts,export_pdf_report,fail_sn_list,numeric_columns,read_measurement_sheet,render_chart,render_facet_chart,spec_limits_for_columns,validate_spec_ranges,vendor_commonality_summary)

VERSION_TEXT="version 1.4 - designed and developed by Hiro Nguyen"

class MultiSheetDialog(QDialog):
    def __init__(self,sheets,parent=None):
        super().__init__(parent);self.setWindowTitle("Select measurement worksheets");layout=QVBoxLayout(self);layout.addWidget(QLabel("Select one or more sheets. Each selected sheet opens in its own window."));self.items=QListWidget();self.items.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection);self.items.addItems(sheets)
        for i in range(self.items.count()):self.items.item(i).setSelected(i==0)
        layout.addWidget(self.items);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def selected(self):return [i.text() for i in self.items.selectedItems()]

class ExportOptionsDialog(QDialog):
    def __init__(self,has_fail,parent=None):
        super().__init__(parent);self.setWindowTitle("Select report contents");layout=QVBoxLayout(self);self.options={}
        for key,label,checked in [("charts","Charts",True),("summary","Vendor commonality summary",True),("stats","Engineering statistics",True),("failures","Fail SN list",has_fail),("data","Mapped/filtered data (Excel only)",True)]:
            cb=QCheckBox(label);cb.setChecked(checked);self.options[key]=cb;layout.addWidget(cb)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def selected(self):return {k:v.isChecked() for k,v in self.options.items()}

class EngineeringChartWindow(QDialog):
    def __init__(self):
        super().__init__();self.setWindowTitle("Engineering Chart Analyzer");self.resize(1500,950)
        self.measurement_data=self.mapping_data=self.data=None;self.mapping_info=None;self._last_stats=self._last_overall=None;self._last_summary=pd.DataFrame();self._last_failures=pd.DataFrame();self._chart_figures={};self._chart_data=None;self._child_windows=[]
        root=QVBoxLayout(self);top=QHBoxLayout();self.data_label=QLabel("Measurement workbook: not loaded");self.mapping_label=QLabel("Mapping workbook: optional")
        b=QPushButton("Open measurements…");b.clicked.connect(self.open_measurements);top.addWidget(b);top.addWidget(self.data_label,1)
        b=QPushButton("Open unit mapping…");b.clicked.connect(self.open_mapping);top.addWidget(b);top.addWidget(self.mapping_label,1)
        self.figure=Figure(figsize=(12,7));self.canvas=FigureCanvasQTAgg(self.figure);self.toolbar=NavigationToolbar2QT(self.canvas,self);self.toolbar.setIconSize(self.toolbar.iconSize().scaled(18,18,Qt.AspectRatioMode.KeepAspectRatio));self.toolbar.setMaximumHeight(32);top.addWidget(self.toolbar);root.addLayout(top)
        split=QSplitter(Qt.Orientation.Horizontal);controls=QWidget();form=QFormLayout(controls)
        self.unit_key=QComboBox();self.mapping_key=QComboBox();self.vendor_column=QComboBox();self.facet_column=QComboBox()
        form.addRow("Unit/serial key in data",self.unit_key);form.addRow("Unit/serial key in mapping",self.mapping_key)
        self.fuzzy_enabled=QCheckBox("Allow similar (fuzzy) unit-key matches");self.fuzzy_threshold=QSpinBox();self.fuzzy_threshold.setRange(50,100);self.fuzzy_threshold.setValue(90)
        form.addRow(self.fuzzy_enabled);form.addRow("Fuzzy threshold (%)",self.fuzzy_threshold)
        self.duplicate_mode=QComboBox();self.duplicate_mode.addItems(["Keep last + NG","Keep last","Keep first"]);form.addRow("Duplicate SN handling",self.duplicate_mode)
        mapb=QPushButton("Auto-map units before charting");mapb.clicked.connect(self.run_mapping);form.addRow(mapb)
        form.addRow("Vendor field (chart columns / X)",self.vendor_column);self.vendor_values=QListWidget();self.vendor_values.setMaximumHeight(75);form.addRow("Vendor values",self.vendor_values)
        form.addRow("Breakdown field (chart rows / Y)",self.facet_column);self.facet_values=QListWidget();self.facet_values.setMaximumHeight(75);form.addRow("Breakdown values",self.facet_values)
        self.chart_checks=QListWidget();self.chart_checks.setMaximumHeight(100)
        for name in CHART_TYPES:
            item=QListWidgetItem(name);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked);self.chart_checks.addItem(item)
        self.chart_checks.itemChanged.connect(self._mark_ready);form.addRow("Chart types (select multiple)",self.chart_checks)
        self.numeric_search=QLineEdit();self.numeric_search.setPlaceholderText("Filter measurement columns…");form.addRow("Find measurements",self.numeric_search);self.numeric_search.textChanged.connect(self._populate_columns)
        self.columns=QListWidget();self.columns.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection);form.addRow("Numeric measurement columns",self.columns)
        self.single_mode=QRadioButton("Single Spec");self.multi_mode=QRadioButton("Multi Spec");self.single_mode.setChecked(True);modes=QHBoxLayout();modes.addWidget(self.single_mode);modes.addWidget(self.multi_mode);form.addRow("Spec mode",modes)
        self.usl=QLineEdit();self.target=QLineEdit();self.lsl=QLineEdit();form.addRow("USL",self.usl);form.addRow("Target / nominal",self.target);form.addRow("LSL",self.lsl)
        self.spec_table=QTableWidget(0,5);self.spec_table.setHorizontalHeaderLabels(["Start Point","End Point","USL","Target","LSL"]);form.addRow("Spec Configuration Table",self.spec_table)
        spec_buttons=QHBoxLayout();add=QPushButton("Add Spec Row");add.clicked.connect(self.add_spec_row);delete=QPushButton("Delete Spec Row");delete.clicked.connect(self.delete_spec_row);imp=QPushButton("Import CSV");imp.clicked.connect(self.import_specs);exp=QPushButton("Export CSV");exp.clicked.connect(self.export_specs)
        for w in (add,delete,imp,exp):spec_buttons.addWidget(w)
        form.addRow(spec_buttons);self.spec_table.setVisible(False);self._spec_buttons=[add,delete,imp,exp]
        self.sample=QLineEdit("350");form.addRow("Max lines per panel",self.sample)
        actions=QHBoxLayout();self.build_button=QPushButton("Build chart");self.build_button.clicked.connect(self.build_charts);self.fail_toggle=QCheckBox("Show Fail / out-of-spec units");self.fail_toggle.setChecked(True);self.fail_toggle.stateChanged.connect(self._mark_ready);actions.addWidget(self.build_button);actions.addWidget(self.fail_toggle);form.addRow(actions)
        actions=QHBoxLayout();png=QPushButton("Save PNG…");png.clicked.connect(self.save_png);pdf=QPushButton("Save PDF…");pdf.clicked.connect(self.save_pdf);excel=QPushButton("Export Excel…");excel.clicked.connect(self.export_excel);reset=QPushButton("Start over");reset.clicked.connect(self.start_over)
        for w in (png,pdf,excel,reset):actions.addWidget(w)
        form.addRow(actions);split.addWidget(controls)
        right=QWidget();rv=QVBoxLayout(right);nav=QHBoxLayout();self.prev=QPushButton("◀");self.next=QPushButton("▶");self.page_label=QLabel("Chart 0 / 0");self.prev.clicked.connect(lambda:self.show_page(-1));self.next.clicked.connect(lambda:self.show_page(1));nav.addWidget(self.prev);nav.addWidget(self.page_label);nav.addWidget(self.next);rv.addLayout(nav);rv.addWidget(self.canvas,4)
        tables=QHBoxLayout();left=QVBoxLayout();left.addWidget(QLabel("Vendor Pass/Fail commonality"));self.summary_table=QTableWidget();left.addWidget(self.summary_table);righttable=QVBoxLayout();self.fail_title=QLabel("Fail SN list");righttable.addWidget(self.fail_title);self.fail_table=QTableWidget();righttable.addWidget(self.fail_table);tables.addLayout(left,2);tables.addLayout(righttable,1);rv.addLayout(tables,1)
        self.findings=QLabel("Load data to begin.");self.findings.setWordWrap(True);rv.addWidget(self.findings);split.addWidget(right);split.setStretchFactor(1,1);root.addWidget(split)
        status=QHBoxLayout();self.progress=QProgressBar();self.progress.setRange(0,100);self.status=QLabel("Choose measurement data.");self.version=QLabel(VERSION_TEXT);status.addWidget(self.progress);status.addWidget(self.status,3);status.addWidget(self.version,2);root.addLayout(status)
        self.vendor_column.currentTextChanged.connect(self._refresh_filters);self.facet_column.currentTextChanged.connect(self._refresh_filters);self.single_mode.toggled.connect(self._spec_mode_changed);self.multi_mode.toggled.connect(self._spec_mode_changed)
        self._spec_mode_changed()

    def _progress(self,n,msg):self.progress.setValue(n);self.status.setText(msg);QApplication.processEvents()
    def _error(self,msg):self.progress.setValue(0);self.status.setText("ERROR — "+msg);QMessageBox.critical(self,"Analyzer error",msg)
    def _read_measurement(self,path,sheet):return read_measurement_sheet(path,sheet)
    def open_measurements(self):
        try:
            path,_=QFileDialog.getOpenFileName(self,"Open measurement workbook","","Excel (*.xlsx *.xlsm)")
            if not path:return
            sheets=pd.ExcelFile(path).sheet_names
            dialog=MultiSheetDialog(sheets,self)
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            chosen=dialog.selected()
            if not chosen:return
            if len(chosen)>1 and QMessageBox.question(self,"Open selected sheets?",f"Open {len(chosen)} sheets in separate windows?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel)==QMessageBox.StandardButton.Cancel:return
            for i,sheet in enumerate(chosen):
                frame=self._read_measurement(path,sheet)
                if len(chosen)==1:self._set_measurements(Path(path),frame,sheet)
                else:
                    window=EngineeringChartWindow();window._set_measurements(Path(path),frame,sheet);window.show();self._child_windows.append(window)
            self._progress(100,f"Loaded {len(chosen)} sheet(s); each sheet has its own window.")
        except Exception as exc:self._error(str(exc))
    def _set_measurements(self,path,frame,sheet):
        self.workbook_path=path;self.measurement_data=frame;self.data=frame.copy();self.data_label.setText(f"{path.name} — {sheet}");self._refresh_controls();self._progress(100,f"Loaded {len(frame):,} rows from {sheet}.")
    def open_mapping(self):
        try:
            path,_=QFileDialog.getOpenFileName(self,"Open mapping workbook","","Excel (*.xlsx *.xlsm)")
            if not path:return
            sheets=pd.ExcelFile(path).sheet_names;sheet,ok=QFileDialog.getOpenFileName(self,"Select mapping sheet",str(path),"") if False else (sheets[0],True)
            if len(sheets)>1:
                from PySide6.QtWidgets import QInputDialog
                sheet,ok=QInputDialog.getItem(self,"Mapping worksheet","Select sheet:",sheets,0,False)
            if not ok:return
            self.mapping_data=pd.read_excel(path,sheet_name=sheet);self.mapping_label.setText(f"{Path(path).name} — {sheet}");self._refresh_controls();self._progress(100,"Mapping workbook loaded.")
        except Exception as exc:self._error(str(exc))
    @staticmethod
    def _combo(combo,names,selected=""):
        combo.blockSignals(True);combo.clear();combo.addItem("");combo.addItems(names)
        if selected in names:combo.setCurrentText(selected)
        combo.blockSignals(False)
    def _refresh_controls(self):
        if self.measurement_data is None:return
        self._combo(self.unit_key,[str(c) for c in self.measurement_data],detect_key_column(self.measurement_data) or "")
        if self.mapping_data is not None:self._combo(self.mapping_key,[str(c) for c in self.mapping_data],detect_key_column(self.mapping_data) or "")
        names=[str(c) for c in self.data.columns];self._combo(self.vendor_column,names,detect_group_column(self.data) or "")
        facet=next((c for c in names if c.casefold().replace("_"," ") in {"trackpad vendor","trackpad","build matrix","bm","product","station"}),"");self._combo(self.facet_column,names,facet)
        self._populate_columns();self._refresh_filters()
    def _populate_columns(self,*_):
        if self.data is None:return
        old=set(self.selected_columns());q=self.numeric_search.text().casefold();self.columns.blockSignals(True);self.columns.clear()
        for name in numeric_columns(self.data):
            if q and q not in name.casefold():continue
            item=QListWidgetItem(name);self.columns.addItem(item);item.setSelected(name in old)
        self.columns.blockSignals(False)
    def selected_columns(self):return [i.text() for i in self.columns.selectedItems()]
    def _refresh_filters(self,*_):
        if self.data is None:return
        for widget,col in ((self.vendor_values,self.vendor_column.currentText()),(self.facet_values,self.facet_column.currentText())):
            widget.clear()
            if col in self.data:
                vals=sorted(self.data[col].astype("object").where(self.data[col].notna(),"(blank)").astype(str).unique())
                for v in vals:
                    it=QListWidgetItem(v);it.setFlags(it.flags()|Qt.ItemFlag.ItemIsUserCheckable);it.setCheckState(Qt.CheckState.Checked);widget.addItem(it)
    @staticmethod
    def checked(widget):return [widget.item(i).text() for i in range(widget.count()) if widget.item(i).checkState()==Qt.CheckState.Checked]
    def run_mapping(self):
        if self.measurement_data is None or self.mapping_data is None:self._error("Load measurement and mapping workbooks first.");return
        try:
            self.data,self.mapping_info=auto_map_units(self.measurement_data,self.mapping_data,self.unit_key.currentText(),self.mapping_key.currentText(),fuzzy=self.fuzzy_enabled.isChecked(),fuzzy_threshold=self.fuzzy_threshold.value());self._refresh_controls();self._progress(100,f"Mapped {self.mapping_info['matched_rows']}/{self.mapping_info['unit_rows']} units ({self.mapping_info['match_rate_pct']:.1f}%; fuzzy {self.mapping_info['fuzzy_matches']}).")
        except Exception as exc:self._error(str(exc))
    def _spec_mode_changed(self,*_):
        multi=self.multi_mode.isChecked()
        for widget in (self.usl,self.target,self.lsl):widget.setVisible(not multi)
        self.spec_table.setVisible(multi)
        for widget in self._spec_buttons:widget.setVisible(multi)
    def add_spec_row(self):
        row=self.spec_table.rowCount();self.spec_table.insertRow(row)
        for c in range(5):self.spec_table.setItem(row,c,QTableWidgetItem(""))
    def delete_spec_row(self):
        row=self.spec_table.currentRow()
        if row>=0:self.spec_table.removeRow(row)
    def _spec_rows(self):
        rows=[]
        for r in range(self.spec_table.rowCount()):
            rows.append({name:(self.spec_table.item(r,c).text() if self.spec_table.item(r,c) else "") for c,name in enumerate(["Start Point","End Point","USL","Target","LSL"])})
        return rows
    def import_specs(self):
        path,_=QFileDialog.getOpenFileName(self,"Import spec CSV","","CSV (*.csv)")
        if not path:return
        try:
            df=pd.read_csv(path);missing=[c for c in ["Start Point","End Point","USL","Target","LSL"] if c not in df]
            if missing:raise ValueError("CSV missing columns: "+", ".join(missing))
            self.spec_table.setRowCount(len(df))
            for r,(_,vals) in enumerate(df.iterrows()):
                for c,name in enumerate(["Start Point","End Point","USL","Target","LSL"]):self.spec_table.setItem(r,c,QTableWidgetItem("" if pd.isna(vals[name]) else str(vals[name])))
            self._progress(100,f"Imported {len(df)} spec ranges.")
        except Exception as exc:self._error(str(exc))
    def export_specs(self):
        path,_=QFileDialog.getSaveFileName(self,"Export spec CSV","specs.csv","CSV (*.csv)")
        if path:pd.DataFrame(self._spec_rows(),columns=["Start Point","End Point","USL","Target","LSL"]).to_csv(path,index=False);self._progress(100,f"Spec ranges exported: {path}")
    def _mark_ready(self,*_):
        if self.data is not None:self.status.setText("Selections changed. Click Build chart to apply.")
    def _checked_charts(self):return [self.chart_checks.item(i).text() for i in range(self.chart_checks.count()) if self.chart_checks.item(i).checkState()==Qt.CheckState.Checked]
    def build_charts(self):
        if self.data is None:self._error("Load measurement data first.");return
        columns=self.selected_columns();charts=self._checked_charts()
        if not columns:self._error("Select numeric measurement columns.");return
        if not charts:self._error("Select at least one chart type.");return
        try:
            usl=None if self.multi_mode.isChecked() else self._number(self.usl);target=None if self.multi_mode.isChecked() else self._number(self.target);lsl=None if self.multi_mode.isChecked() else self._number(self.lsl)
            specs=spec_limits_for_columns(columns,"Multi Spec" if self.multi_mode.isChecked() else "Single Spec",usl,target,lsl,self._spec_rows())
            mask=pd.Series(False,index=self.data.index);vals=self.data[columns].apply(pd.to_numeric,errors="coerce")
            for sp in specs:
                seg=vals.iloc[:,sp["start_index"]:sp["end_index"]+1]
                if sp["USL"] is not None:mask|=seg.gt(sp["USL"]).any(axis=1)
                if sp["LSL"] is not None:mask|=seg.lt(sp["LSL"]).any(axis=1)
            key=self.unit_key.currentText()
            dedup=deduplicate_units(self.data,key,self.duplicate_mode.currentText(),mask.to_numpy())
            cols=[c for c in columns if c in dedup]
            vendor=self.vendor_column.currentText();facet=self.facet_column.currentText()
            filtered=dedup.copy()
            if vendor in filtered:filtered=filtered.loc[filtered[vendor].astype("object").where(filtered[vendor].notna(),"(blank)").astype(str).isin(self.checked(self.vendor_values))]
            if facet in filtered:filtered=filtered.loc[filtered[facet].astype("object").where(filtered[facet].notna(),"(blank)").astype(str).isin(self.checked(self.facet_values))]
            if filtered.empty:raise ValueError("Current filters leave no rows.")
            self._chart_figures={};limit=max(25,int(self.sample.text() or 350));vsel=self.checked(self.vendor_values);fsel=self.checked(self.facet_values)
            for i,chart in enumerate(charts):
                fig=Figure(figsize=(12,7))
                if chart=="Multi-Line Trend Chart" and vendor:
                    render_facet_chart(filtered,cols,vendor_column=vendor,facet_column=facet,usl=usl,lsl=lsl,target=target,spec_ranges=specs,spec_mode="Multi Spec" if self.multi_mode.isChecked() else "Single Spec",sample_limit=limit,figure=fig,vendor_values=vsel,facet_values=fsel,highlight_oos=self.fail_toggle.isChecked())
                else:render_chart(filtered,cols,chart,group_column=vendor,usl=usl,lsl=lsl,target=target,spec_ranges=specs,spec_mode="Multi Spec" if self.multi_mode.isChecked() else "Single Spec",sample_limit=limit,figure=fig)
                self._chart_figures[chart]=fig
            self._chart_names=charts;self._page=0;self._render_page()
            self._last_stats,self._last_overall=analyze_measurements(filtered,cols,usl,lsl)
            self._last_summary=vendor_commonality_summary(filtered,cols,vendor,facet,usl,lsl)
            if vendor in self._last_summary:self._last_summary=self._last_summary.rename(columns={vendor:"Vendor Value",facet:"Breakdown Value"} if facet in self._last_summary else {vendor:"Vendor Value"})
            self._last_failures=fail_sn_list(filtered,cols,key,specs) if self.fail_toggle.isChecked() else pd.DataFrame(columns=["Fail SN","Fail position","Fail value"])
            self._show_table(self.summary_table,self._last_summary);self._show_table(self.fail_table,self._last_failures);self.fail_table.setVisible(not self._last_failures.empty);self.fail_title.setVisible(not self._last_failures.empty)
            self._chart_data=filtered;self._last_stats_by_chart=self._last_stats;self._last_specs=specs
            self._progress(100,f"Charts ready ({len(charts)} pages) — {len(filtered):,} units; vendor title: {vendor or 'not selected'}; breakdown title: {facet or 'All units'}.")
        except Exception as exc:self._error(str(exc))
    def _render_page(self):
        if not getattr(self,"_chart_names",[]):return
        name=self._chart_names[self._page];self.figure.clear();source=self._chart_figures[name]
        source.savefig(sys.stdout if False else BytesIO(),format="png") if False else None
        self.figure.clear();self.figure.set_size_inches(source.get_size_inches());self.figure.subplots_adjust(0,0,1,1)
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        buf=BytesIO();source.savefig(buf,format="png",dpi=110,bbox_inches="tight");buf.seek(0)
        import matplotlib.image as mpimg
        self.figure.add_subplot(111).imshow(mpimg.imread(buf));self.figure.axes[0].axis("off");self.canvas.draw_idle();self.page_label.setText(f"Chart {self._page+1} / {len(self._chart_names)} — {name}")
    def show_page(self,delta):
        if not getattr(self,"_chart_names",[]):return
        self._page=(self._page+delta)%len(self._chart_names);self._render_page()
    @staticmethod
    def _number(w):
        t=w.text().strip()
        if not t:return None
        v=float(t)
        if not np.isfinite(v):raise ValueError("Spec values must be finite.")
        return v
    def _show_table(self,table,frame):
        table.clear();table.setRowCount(min(300,len(frame)));table.setColumnCount(len(frame.columns));table.setHorizontalHeaderLabels([str(c) for c in frame.columns])
        for r,row in enumerate(frame.head(300).itertuples(index=False,name=None)):
            for c,v in enumerate(row):
                text="" if pd.isna(v) else f"{v:,.2f}%" if isinstance(v,(float,np.floating)) and "%" in str(frame.columns[c]) else f"{v:,.4g}" if isinstance(v,(float,np.floating)) else str(v)
                table.setItem(r,c,QTableWidgetItem(text))
        table.resizeColumnsToContents()
    def _export_options(self):
        d=ExportOptionsDialog(not self._last_failures.empty,self)
        return d.selected() if d.exec()==QDialog.DialogCode.Accepted else None
    def save_png(self):
        if not self._chart_figures:self._error("Build charts first.");return
        path,_=QFileDialog.getSaveFileName(self,"Save current chart","EngineeringChart.png","PNG (*.png)")
        if path:self._chart_figures[self._chart_names[self._page]].savefig(path,dpi=160,bbox_inches="tight");self._progress(100,f"Chart PNG saved: {path}")
    def save_pdf(self):self._save_report("pdf")
    def export_excel(self):self._save_report("xlsx")
    def _save_report(self,kind):
        if not self._chart_figures:self._error("Build charts before exporting.");return
        opts=self._export_options()
        if opts is None:self.status.setText("Report export cancelled.");return
        path,_=QFileDialog.getSaveFileName(self,"Save report",f"EngineeringReport.{kind}",f"{kind.upper()} (*.{kind})")
        if not path:return
        try:
            figs=self._chart_figures if opts["charts"] else {}
            summary=self._last_summary if opts["summary"] else pd.DataFrame();stats=self._last_stats if opts["stats"] else pd.DataFrame();fails=self._last_failures if opts["failures"] else pd.DataFrame()
            if kind=="pdf":out=export_pdf_report(path,figs,summary,self._last_overall,"Engineering Chart Report",stats=stats,failures=fails,include_charts=opts["charts"],include_summary=opts["summary"],include_stats=opts["stats"],include_failures=opts["failures"])
            else:out=export_engineering_charts(path,figs,stats,self._last_overall,summary,pd.DataFrame(self._last_specs),mapped_data=self._chart_data,failures=fails,include_charts=opts["charts"],include_summary=opts["summary"],include_stats=opts["stats"],include_failures=opts["failures"],include_data=opts["data"])
            self._progress(100,f"Report exported: {out}")
        except Exception as exc:self._error(str(exc))
    def start_over(self):
        self.measurement_data=self.mapping_data=self.data=None;self._last_stats=self._last_overall=None;self._last_summary=self._last_failures=pd.DataFrame();self._chart_figures={};self.data_label.setText("Measurement workbook: not loaded");self.mapping_label.setText("Mapping workbook: optional");self.summary_table.clear();self.fail_table.clear();self.figure.clear();self.canvas.draw();self._progress(0,"Reset complete.")

def main():
    app=QApplication(sys.argv);window=EngineeringChartWindow();window.show();return app.exec()
if __name__=="__main__":raise SystemExit(main())
