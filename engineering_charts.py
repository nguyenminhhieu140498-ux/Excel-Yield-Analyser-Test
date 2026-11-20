"""Engineering measurements, charts, spec handling, mapping, and reports."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage

CHART_TYPES = ["Multi-Line Trend Chart", "Vendor Comparison Chart", "Average Trend Chart", "Box Plot by Vendor", "Histogram", "Scatter Plot", "Control/SPC Chart"]
KEY_HINTS = ("serial number", "serial_number", "serialnumber", "unit id", "unit_id", "unitid", "serial", "sn")
GROUP_HINTS = ("vendor", "supplier", "manufacturer", "maker")
SPEC_COLUMNS = ["Start Point", "End Point", "USL", "Target", "LSL"]


def _norm_name(value): return re.sub(r"[^a-z0-9]", "", str(value).casefold())
def _norm_key(value):
    if pd.isna(value): return ""
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"\.0+$", "", str(value).strip().upper()))


def detect_key_column(data):
    if data is None or data.empty: return None
    names = {_norm_name(c): str(c) for c in data.columns}
    for hint in KEY_HINTS:
        if _norm_name(hint) in names: return names[_norm_name(hint)]
    return next((str(c) for c in data.columns if _norm_name(c) in {"sn", "serial", "serialno", "serialnumber", "unitid", "unitnumber"}), None)


def detect_group_column(data):
    if data is None: return None
    return next((str(c) for c in data.columns if any(h in _norm_name(c) for h in GROUP_HINTS)), None)


def numeric_columns(data):
    return [str(c) for c in data.columns if pd.to_numeric(data[c], errors="coerce").notna().any()]


def read_measurement_sheet(path, sheet_name):
    """Read standard headers unchanged; otherwise locate a raw-file header via column C (first 10 rows)."""
    standard = pd.read_excel(path, sheet_name=sheet_name, header=0)
    headers = [str(c).strip() for c in standard.columns]
    meaningful = [c for c in headers if not c.casefold().startswith("unnamed:") and c not in {"", "nan"}]
    if len(meaningful) >= 2:
        standard.columns = headers
        return standard
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
    if raw.shape[1] < 3:
        raise ValueError("Raw measurement sheet must have a header row with data in column C.")
    header_row = next((i for i in range(min(10, len(raw))) if pd.notna(raw.iat[i, 2]) and str(raw.iat[i, 2]).strip()), None)
    if header_row is None:
        raise ValueError("Could not find the raw measurement header in column C within the first 10 rows.")
    names = [str(v).strip() if pd.notna(v) and str(v).strip() else f"Unnamed: {i}" for i, v in enumerate(raw.iloc[header_row].tolist())]
    frame = raw.iloc[header_row + 1:].copy()
    frame.columns = names
    frame = frame.dropna(how="all").reset_index(drop=True)
    return frame


def auto_map_units(unit_data, mapping_data, unit_key=None, mapping_key=None, append_columns=None, fuzzy=False, fuzzy_threshold=90):
    if unit_data is None or mapping_data is None: raise ValueError("Load both measurement and mapping worksheets first.")
    unit_key = unit_key or detect_key_column(unit_data); mapping_key = mapping_key or detect_key_column(mapping_data)
    if not unit_key or unit_key not in unit_data: raise ValueError("Select a valid unit serial-number column.")
    if not mapping_key or mapping_key not in mapping_data: raise ValueError("Select a valid mapping serial-number column.")
    if not 0 <= int(fuzzy_threshold) <= 100: raise ValueError("Fuzzy threshold must be between 0 and 100.")
    append_columns = list(append_columns) if append_columns is not None else [c for c in mapping_data if c != mapping_key and c not in unit_data]
    append_columns = list(dict.fromkeys(c for c in append_columns if c in mapping_data and c != mapping_key and c not in unit_data))
    right = mapping_data[[mapping_key, *append_columns]].copy(); right["__key"] = right[mapping_key].map(_norm_key)
    right = right[right.__key.ne("")].drop_duplicates("__key", keep="first")
    lookup = right.set_index("__key")[append_columns]; keys = list(lookup.index)
    if fuzzy:
        try: from rapidfuzz import process, fuzz
        except ImportError as exc: raise ValueError("Install rapidfuzz to use fuzzy mapping.") from exc
    keys_out=[]; fuzzy_count=0
    for value in unit_data[unit_key]:
        key=_norm_key(value)
        if key in lookup.index: keys_out.append(key)
        elif fuzzy and key:
            found=process.extractOne(key, keys, scorer=fuzz.ratio, score_cutoff=int(fuzzy_threshold))
            keys_out.append(found[0] if found else None); fuzzy_count += bool(found)
        else: keys_out.append(None)
    result=unit_data.copy().reset_index(drop=True); meta=lookup.reindex(keys_out); meta.index=result.index
    for column in append_columns: result[column]=meta[column].to_numpy()
    matched=sum(key is not None for key in keys_out); total=len(result)
    return result, {"unit_rows":total,"matched_rows":matched,"unmatched_rows":total-matched,"match_rate_pct":matched/total*100 if total else 0.0,"unit_key":unit_key,"mapping_key":mapping_key,"mapped_columns":append_columns,"fuzzy_matches":int(fuzzy_count)}


def deduplicate_units(data, key_column, mode="Keep last + NG", fail_mask=None):
    if not key_column or key_column not in data: return data.copy()
    work=data.copy(); work["__order"] = np.arange(len(work)); work["__key"] = work[key_column].map(_norm_key)
    valid=work["__key"].ne("")
    if mode == "Keep first":
        chosen=work.loc[valid].drop_duplicates("__key", keep="first")
    else:
        chosen=work.loc[valid].drop_duplicates("__key", keep="last")
        if mode == "Keep last + NG" and fail_mask is not None:
            failed=work.loc[valid].loc[np.asarray(fail_mask, dtype=bool)]
            if not failed.empty:
                fail_last=failed.drop_duplicates("__key", keep="last").set_index("__key")
                chosen=chosen.set_index("__key")
                chosen.update(fail_last)
                chosen=chosen.reset_index()
    blanks=work.loc[~valid]
    return pd.concat([chosen,blanks],ignore_index=True).sort_values("__order",kind="stable").drop(columns=["__order","__key"],errors="ignore").reset_index(drop=True)


def validate_spec_ranges(spec_rows, categories):
    categories=list(categories); positions={str(v):i for i,v in enumerate(categories)}; spans=[]; valid=[]
    for row in spec_rows:
        start=str(row.get("Start Point", "")).strip(); end=str(row.get("End Point", "")).strip()
        if not start or not end: continue
        if start not in positions or end not in positions: raise ValueError(f"Spec range points must exist on the X-axis: {start} – {end}.")
        lo,hi=positions[start],positions[end]
        if lo>hi: raise ValueError(f"Start Point must not come after End Point: {start} – {end}.")
        usl=_optional_float(row.get("USL")); lsl=_optional_float(row.get("LSL")); target=_optional_float(row.get("Target"))
        if usl is not None and lsl is not None and usl<=lsl: raise ValueError(f"USL must be greater than LSL in range {start} – {end}.")
        if any(not (hi < a or lo > b) for a,b in spans): raise ValueError(f"Spec ranges cannot overlap: {start} – {end}.")
        spans.append((lo,hi)); valid.append({"Start Point":start,"End Point":end,"USL":usl,"Target":target,"LSL":lsl,"start_index":lo,"end_index":hi})
    return valid


def _optional_float(value):
    if value is None or (isinstance(value,str) and not value.strip()) or pd.isna(value): return None
    result=float(value)
    if not np.isfinite(result): raise ValueError("Spec values must be finite numbers.")
    return result


def spec_limits_for_columns(columns, mode="Single Spec", usl=None,target=None,lsl=None,spec_ranges=None):
    if mode != "Multi Spec": return [{"Start Point":columns[0],"End Point":columns[-1],"USL":usl,"Target":target,"LSL":lsl,"start_index":0,"end_index":len(columns)-1}] if columns else []
    return validate_spec_ranges(spec_ranges or [], columns)


def _values(data, columns):
    columns=list(columns)
    if not columns: raise ValueError("Select at least one measurement column.")
    missing=[c for c in columns if c not in data]
    if missing: raise ValueError("Measurement column(s) not found: "+", ".join(missing))
    return data[columns].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float)


def _stats(x,usl=None,lsl=None):
    x=np.asarray(x,dtype=float); x=x[np.isfinite(x)]; n=len(x); mean=float(np.mean(x)) if n else np.nan; sd=float(np.std(x,ddof=1)) if n>1 else np.nan
    above=int((x>usl).sum()) if usl is not None else 0; below=int((x<lsl).sum()) if lsl is not None else 0
    fail=int(((x>usl)|(x<lsl)).sum()) if usl is not None and lsl is not None else above if usl is not None else below
    within=float(np.std(np.diff(x),ddof=1)/np.sqrt(2)) if n>2 else np.nan
    cp=cpk=np.nan
    if usl is not None and lsl is not None and np.isfinite(within) and within>0: cp=(usl-lsl)/(6*within); cpk=min((usl-mean)/(3*within),(mean-lsl)/(3*within))
    return {"Count":n,"Mean":mean,"Median":float(np.median(x)) if n else np.nan,"Std Dev":sd,"Min":float(np.min(x)) if n else np.nan,"Max":float(np.max(x)) if n else np.nan,"Range":float(np.ptp(x)) if n else np.nan,"Cp":cp,"Cpk":cpk,"Above USL":above,"Below LSL":below,"Pass":n-fail,"Fail":fail,"Yield %":(n-fail)/n*100 if n and (usl is not None or lsl is not None) else np.nan}


def analyze_measurements(data,columns,usl=None,lsl=None):
    m=_values(data,columns); return pd.DataFrame([{"Measurement Point":c,**_stats(m[:,i],usl,lsl)} for i,c in enumerate(columns)]),_stats(m.ravel(),usl,lsl)


def _labels(series): return series.astype("object").where(series.notna(),"(blank)").astype(str)


def vendor_commonality_summary(data,columns,vendor_column,facet_column="",usl=None,lsl=None):
    cols=list(columns); vals=data[cols].apply(pd.to_numeric,errors="coerce"); valid=vals.notna().any(axis=1)
    fail=pd.Series(False,index=data.index)
    if usl is not None: fail |= vals.gt(usl).any(axis=1)
    if lsl is not None: fail |= vals.lt(lsl).any(axis=1)
    vendor=_labels(data[vendor_column]) if vendor_column in data else pd.Series("",index=data.index)
    facet=_labels(data[facet_column]) if facet_column and facet_column in data else pd.Series("All units",index=data.index)
    f=pd.DataFrame({"Vendor":vendor,"Breakdown":facet,"Fail":fail,"Valid":valid})
    f=f.loc[valid & f.Vendor.ne("(blank)") & f.Breakdown.ne("(blank)")]
    if f.empty:return pd.DataFrame(columns=[vendor_column or "Vendor",facet_column or "Breakdown","Fail N","Fail % of Total","Pass N","Pass % of Total","Total N"])
    g=f.groupby(["Vendor","Breakdown","Fail"],observed=True).size().unstack("Fail",fill_value=0).reindex(columns=[False,True],fill_value=0)
    total=int(g.to_numpy().sum()); out=g.reset_index(); out.columns=["Vendor","Breakdown","Pass N","Fail N"]
    out["Pass % of Total"]=out["Pass N"]/total*100; out["Fail % of Total"]=out["Fail N"]/total*100; out["Total N"]=out["Pass N"]+out["Fail N"]
    return out.rename(columns={"Vendor":vendor_column or "Vendor","Breakdown":facet_column or "Breakdown"})[[vendor_column or "Vendor",facet_column or "Breakdown","Fail N","Fail % of Total","Pass N","Pass % of Total","Total N"]]


def fail_sn_list(data,columns,key_column,specs):
    if not key_column or key_column not in data:return pd.DataFrame(columns=["Fail SN","Fail position","Fail value"])
    vals=data[list(columns)].apply(pd.to_numeric,errors="coerce"); records=[]
    for spec in specs:
        for col in columns[spec["start_index"]:spec["end_index"]+1]:
            series=vals[col]; mask=series.notna()
            if spec["USL"] is not None: mask &= series>spec["USL"]
            if spec["LSL"] is not None: mask |= series.notna() & (series<spec["LSL"])
            for idx in data.index[mask]: records.append({"Fail SN":data.at[idx,key_column],"Fail position":col,"Fail value":float(series.at[idx])})
    return pd.DataFrame(records,columns=["Fail SN","Fail position","Fail value"])


def dashboard_findings(data,columns,group_column="",usl=None,lsl=None):
    vals=data[list(columns)].apply(pd.to_numeric,errors="coerce"); bad=pd.DataFrame(False,index=data.index,columns=vals.columns)
    if usl is not None:bad|=vals.gt(usl)
    if lsl is not None:bad|=vals.lt(lsl)
    out=[{"Finding":"Top Fail Measurement Point","Category":c,"Count":int(bad[c].sum())} for c in bad if bad[c].any()]
    if bad.to_numpy().any() and group_column in data:
        counts=_labels(data[group_column]).loc[bad.any(axis=1)].value_counts(); counts=counts.drop("(blank)",errors="ignore")
        if len(counts):out.append({"Finding":"Top Fail Vendor","Category":counts.index[0],"Count":int(counts.iloc[0])})
    return pd.DataFrame(out,columns=["Finding","Category","Count"])


def _draw_specs(ax,columns,specs):
    for s in specs:
        lo,hi=s["start_index"],s["end_index"]
        for key,color,label in (("USL","#e53949","USL"),("Target","#20a45b","Target"),("LSL","#e53949","LSL")):
            value=s.get(key)
            if value is not None:
                ax.plot([lo,hi],[value,value],linestyle="--",linewidth=1.5,color=color,label=label if lo==0 else "_nolegend_")
                if key in {"USL","LSL"}: ax.text((lo+hi)/2,value,f"{label} {value:g}",color=color,fontsize=7,ha="center",va="bottom")
        if s.get("USL") is not None and s.get("LSL") is not None: ax.axhspan(s["LSL"],s["USL"],xmin=lo/max(1,len(columns)-1),xmax=hi/max(1,len(columns)-1),color="#68d8dc",alpha=.14,zorder=0)


def render_facet_chart(data,columns,*,vendor_column,facet_column="",usl=None,lsl=None,target=None,sample_limit=350,figure=None,vendor_values=None,facet_values=None,highlight_oos=True,spec_ranges=None,spec_mode="Single Spec"):
    columns=list(columns)
    if vendor_column not in data:raise ValueError("Choose a vendor/group column for the breakdown chart.")
    vals=data[columns].apply(pd.to_numeric,errors="coerce"); vl=_labels(data[vendor_column]); fl=_labels(data[facet_column]) if facet_column and facet_column in data else pd.Series("All units",index=data.index)
    vendors=list(vendor_values) if vendor_values is not None else [v for v in vl.unique() if v!="(blank)"]
    facets=list(facet_values) if facet_values is not None else [v for v in fl.unique() if v!="(blank)"]
    vendors=vendors[:8] or ["(no selected vendors)"]; facets=facets[:8] or ["(no selected breakdowns)"]
    specs=spec_limits_for_columns(columns,spec_mode,usl,target,lsl,spec_ranges)
    failed=pd.Series(False,index=data.index)
    for sp in specs:
        segment=vals.iloc[:,sp["start_index"]:sp["end_index"]+1]
        if sp["USL"] is not None:failed|=segment.gt(sp["USL"]).any(axis=1)
        if sp["LSL"] is not None:failed|=segment.lt(sp["LSL"]).any(axis=1)
    fig=figure or plt.figure(figsize=(14,8)); fig.clear(); axes=fig.subplots(len(facets),len(vendors),squeeze=False,sharex=True,sharey=True); x=np.arange(len(columns))
    for r,facet in enumerate(facets):
        for c,vendor in enumerate(vendors):
            ax=axes[r,c]; ids=np.flatnonzero((vl.eq(vendor)&fl.eq(facet)).to_numpy())
            if len(ids)>sample_limit:ids=ids[np.linspace(0,len(ids)-1,sample_limit,dtype=int)]
            for idx in ids: ax.plot(x,vals.iloc[idx].to_numpy(),color="#cf142b" if highlight_oos and failed.iloc[idx] else "#74a9ff",lw=1.6 if failed.iloc[idx] else .65,alpha=.95 if failed.iloc[idx] else .28)
            _draw_specs(ax,columns,specs); ax.set_title(str(vendor),fontsize=10,fontweight="bold"); ax.grid(alpha=.18)
            if c==0:ax.set_ylabel(f"{facet_column or 'Breakdown'}: {facet}\nMeasurement")
            if r==len(facets)-1:ax.set_xticks(x,columns,rotation=90,fontsize=7)
    fig.suptitle(f"Measurement offset by {vendor_column}"+(f" and {facet_column}" if facet_column else ""),fontweight="bold")
    fig.supxlabel(f"Measurement position ({', '.join(columns[:3])}{'…' if len(columns)>3 else ''})")
    handles,labels=axes[0,0].get_legend_handles_labels()
    if handles:fig.legend(handles,labels,loc="upper right")
    fig.tight_layout(rect=(.02,.04,.98,.93)); return fig


def render_chart(data,columns,chart_type,*,group_column="",id_column="",vendor_column="",bm_column="",usl=None,lsl=None,target=None,highlight_oos=True,selected_vendor="",sample_limit=500,figure=None,spec_ranges=None,spec_mode="Single Spec"):
    columns=list(columns); vals=data[columns].apply(pd.to_numeric,errors="coerce"); fig=figure or plt.figure(figsize=(11,6)); fig.clear(); ax=fig.add_subplot(111)
    specs=spec_limits_for_columns(columns,spec_mode,usl,target,lsl,spec_ranges); x=np.arange(len(columns)); failed=pd.Series(False,index=data.index)
    for sp in specs:
        seg=vals.iloc[:,sp["start_index"]:sp["end_index"]+1]
        if sp["USL"] is not None:failed|=seg.gt(sp["USL"]).any(axis=1)
        if sp["LSL"] is not None:failed|=seg.lt(sp["LSL"]).any(axis=1)
    if chart_type=="Multi-Line Trend Chart":
        ids=np.arange(len(data)); ids=ids[np.linspace(0,len(ids)-1,min(len(ids),sample_limit),dtype=int)] if len(ids)>sample_limit else ids
        for i in ids:ax.plot(x,vals.iloc[i].to_numpy(),color="#cf142b" if highlight_oos and failed.iloc[i] else "#74a9ff",alpha=.9 if failed.iloc[i] else .3,lw=1.5 if failed.iloc[i] else .65)
        ax.set_xticks(x,columns,rotation=45,ha="right");ax.set_ylabel("Measurement value");ax.set_xlabel("Measurement position")
    elif chart_type in ("Vendor Comparison Chart","Average Trend Chart"):
        labels=_labels(data[group_column]) if group_column in data else None
        if chart_type=="Vendor Comparison Chart" and labels is not None:
            for name in labels.unique():
                if name!="(blank)":ax.plot(columns,vals.loc[labels.eq(name)].mean(axis=0),marker="o",label=name)
            ax.legend(title=group_column)
        else:ax.plot(columns,vals.mean(axis=0),marker="o",label="Mean")
        ax.set_ylabel("Measurement value");ax.tick_params(axis="x",rotation=45)
    elif chart_type=="Box Plot by Vendor":
        if group_column not in data:raise ValueError("Choose a vendor field for box plots.")
        labels=_labels(data[group_column]); names=[n for n in labels.unique() if n!="(blank)"][:40]
        ax.boxplot([vals.loc[labels.eq(n)].to_numpy().ravel() for n in names],tick_labels=names,showfliers=False);ax.set_ylabel("Measurement value by vendor");ax.tick_params(axis="x",rotation=45)
    elif chart_type=="Histogram":ax.hist(vals.to_numpy().ravel(),bins="fd",color="#4472c4",alpha=.8);ax.set_xlabel("Measurement value")
    elif chart_type=="Scatter Plot":
        if len(columns)<2:raise ValueError("Select at least two measurements for scatter plot.")
        ax.scatter(vals.iloc[:,0],vals.iloc[:,1],c=np.where(failed,"#cf142b","#4472c4"),alpha=.6);ax.set_xlabel(columns[0]);ax.set_ylabel(columns[1])
    elif chart_type=="Control/SPC Chart":
        series=vals.iloc[:,0].to_numpy();mean=np.nanmean(series);sd=np.nanstd(series,ddof=1) if np.isfinite(series).sum()>1 else np.nan
        ax.plot(np.arange(len(series)),series,color="#4472c4",lw=.8);ax.axhline(mean,color="green",label="Center")
        if np.isfinite(sd):ax.axhline(mean+3*sd,color="#cf142b",ls="--",label="UCL");ax.axhline(mean-3*sd,color="#cf142b",ls="--",label="LCL")
        ax.set_ylabel(columns[0]);ax.set_xlabel(id_column or "Unit/row");ax.legend()
    else:raise ValueError(f"Unsupported chart type: {chart_type}")
    if chart_type not in ("Control/SPC Chart","Histogram","Scatter Plot"):_draw_specs(ax,columns,specs)
    ax.set_title(f"{chart_type} — vendor: {group_column or 'All'}");ax.grid(alpha=.2);return fig


def export_engineering_charts(output_path,figures,stats,overall,vendors,spec_analysis,spc_metrics=None,mapped_data=None,failures=None,include_charts=True,include_summary=True,include_stats=True,include_failures=True,include_data=True):
    path=Path(output_path).with_suffix(".xlsx");path.parent.mkdir(parents=True,exist_ok=True)
    from openpyxl import Workbook
    wb=load_workbook(path) if path.exists() else Workbook()
    if wb.sheetnames==["Sheet"] and wb["Sheet"].max_row==1 and wb["Sheet"].max_column==1 and wb["Sheet"]["A1"].value is None:wb.remove(wb.active)
    def add_table(name,frame):
        if name in wb.sheetnames:del wb[name]
        ws=wb.create_sheet(name)
        if frame is not None and not frame.empty:
            for j,c in enumerate(frame.columns,1):ws.cell(1,j,str(c))
            for i,row in enumerate(frame.itertuples(index=False,name=None),2):
                for j,val in enumerate(row,1):ws.cell(i,j,None if pd.isna(val) else val.item() if isinstance(val,np.generic) else val)
    if include_charts:
        if "Charts" in wb.sheetnames:del wb["Charts"]
        ws=wb.create_sheet("Charts")
        for i,(name,fig) in enumerate((figures.items() if isinstance(figures,dict) else [("Chart",figures)]),1):
            ws.cell(1+(i-1)*25,1,name);buf=BytesIO();fig.savefig(buf,format="png",dpi=130,bbox_inches="tight");buf.seek(0);img=XLImage(buf);img.width=900;img.height=480;img.anchor=f"A{2+(i-1)*25}";ws.add_image(img)
    if include_stats:add_table("EngineeringStats",stats)
    if include_summary:add_table("VendorCommonality",vendors)
    if include_failures:add_table("FailSNList",failures)
    add_table("SpecAnalysis",spec_analysis)
    if spc_metrics is not None:add_table("SPCMetrics",spc_metrics)
    if include_data and mapped_data is not None:add_table("MappedUnits",mapped_data)
    wb.save(path);return path


def export_pdf_report(output_path,figures,summary,overall,title="Engineering Chart Report",stats=None,failures=None,include_charts=True,include_summary=True,include_stats=True,include_failures=True):
    path=Path(output_path).with_suffix(".pdf");path.parent.mkdir(parents=True,exist_ok=True)
    chart_items=list(figures.items()) if isinstance(figures,dict) else [("Chart",figures)]
    with PdfPages(path) as pdf:
        if include_charts:
            for chart_name,fig in chart_items:
                fig.suptitle(f"{title}\n{chart_name}",fontweight="bold");pdf.savefig(fig,bbox_inches="tight")
        if include_summary or include_stats or (include_failures and failures is not None and not failures.empty):
            fig,ax=plt.subplots(figsize=(11.7,8.3));ax.axis("off");ax.set_title(title,fontsize=16,fontweight="bold")
            y=.94
            if include_stats:
                ax.text(.02,y,"Engineering statistics",fontweight="bold",transform=ax.transAxes);y-=.03
                table=pd.DataFrame([{"Metric":k,"Value":v} for k,v in overall.items()]);ax.table(cellText=table.fillna("").astype(str).values,colLabels=table.columns,loc="upper left",bbox=[.02,y-.25,.46,.24]);y-=.29
            if include_summary and summary is not None and not summary.empty:
                ax.text(.02,y,"Vendor Pass/Fail commonality",fontweight="bold",transform=ax.transAxes);y-=.03
                show=summary.head(22).fillna("").astype(str);ax.table(cellText=show.values,colLabels=show.columns,loc="upper left",bbox=[.02,y-.35,.96,.34]);y-=.39
            if include_failures and failures is not None and not failures.empty:
                ax.text(.02,y,"Fail SN list",fontweight="bold",transform=ax.transAxes);y-=.03
                show=failures.head(15).fillna("").astype(str);ax.table(cellText=show.values,colLabels=show.columns,loc="upper left",bbox=[.02,max(.02,y-.3),.96,.29])
            pdf.savefig(fig,bbox_inches="tight");plt.close(fig)
    return path
