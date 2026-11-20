"""Engineering measurements, spec validation, charts, summaries and reports."""
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


def _norm_name(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _norm_key(value):
    if pd.isna(value):
        return ""
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"\.0+$", "", str(value).strip().upper()))


def detect_key_column(data):
    if data is None or data.empty:
        return None
    normalized = {_norm_name(c): str(c) for c in data.columns}
    for hint in KEY_HINTS:
        if _norm_name(hint) in normalized:
            return normalized[_norm_name(hint)]
    for col in data.columns:
        name = _norm_name(col)
        if name in {"sn", "serial", "serialno", "serialnumber", "unitid", "unitnumber"} or "serialnumber" in name:
            return str(col)
    return None


def detect_group_column(data):
    if data is None:
        return None
    return next((str(c) for c in data.columns if any(h in _norm_name(c) for h in GROUP_HINTS)), None)


def numeric_columns(data):
    return [str(c) for c in data.columns if pd.to_numeric(data[c], errors="coerce").notna().any()]


def read_measurement_sheet(path, sheet_name):
    """Keep normal row-1 headers; otherwise locate the raw header using column C in rows 1–10."""
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
    return frame.dropna(how="all").reset_index(drop=True)


def auto_map_units(unit_data, mapping_data, unit_key=None, mapping_key=None, append_columns=None, fuzzy=False, fuzzy_threshold=90):
    if unit_data is None or mapping_data is None:
        raise ValueError("Load both measurement and mapping worksheets first.")
    unit_key = unit_key or detect_key_column(unit_data)
    mapping_key = mapping_key or detect_key_column(mapping_data)
    if not unit_key or unit_key not in unit_data:
        raise ValueError("Select a valid unit serial-number column.")
    if not mapping_key or mapping_key not in mapping_data:
        raise ValueError("Select a valid mapping serial-number column.")
    if not 0 <= int(fuzzy_threshold) <= 100:
        raise ValueError("Fuzzy threshold must be between 0 and 100.")
    if append_columns is None:
        append_columns = [c for c in mapping_data.columns if c != mapping_key and c not in unit_data.columns]
    append_columns = list(dict.fromkeys(c for c in append_columns if c in mapping_data.columns and c != mapping_key and c not in unit_data.columns))
    right = mapping_data[[mapping_key, *append_columns]].copy()
    right["__key"] = right[mapping_key].map(_norm_key)
    right = right[right["__key"].ne("")].drop_duplicates("__key", keep="first")
    lookup = right.set_index("__key")[append_columns]
    keys = list(lookup.index)
    if fuzzy:
        try:
            from rapidfuzz import process, fuzz
        except ImportError as exc:
            raise ValueError("Install rapidfuzz to use fuzzy mapping.") from exc
    keys_out, fuzzy_count = [], 0
    for value in unit_data[unit_key]:
        key = _norm_key(value)
        if key in lookup.index:
            keys_out.append(key)
        elif fuzzy and key:
            found = process.extractOne(key, keys, scorer=fuzz.ratio, score_cutoff=int(fuzzy_threshold))
            keys_out.append(found[0] if found else None)
            fuzzy_count += int(bool(found))
        else:
            keys_out.append(None)
    result = unit_data.copy().reset_index(drop=True)
    metadata = lookup.reindex(keys_out)
    metadata.index = result.index
    for column in append_columns:
        result[column] = metadata[column].to_numpy()
    matched, total = sum(k is not None for k in keys_out), len(result)
    return result, {"unit_rows": total, "matched_rows": matched, "unmatched_rows": total-matched,
                    "match_rate_pct": matched/total*100 if total else 0.0, "unit_key": unit_key,
                    "mapping_key": mapping_key, "mapped_columns": append_columns, "fuzzy_matches": fuzzy_count}


def deduplicate_units(data, key_column, mode="Keep last + NG", fail_mask=None):
    if not key_column or key_column not in data:
        return data.copy()
    n = len(data)
    failures = np.zeros(n, dtype=bool) if fail_mask is None else np.asarray(fail_mask, dtype=bool)
    if failures.ndim != 1 or len(failures) != n:
        raise ValueError(f"Fail mask must contain exactly {n} values; got {len(failures)}.")
    if mode not in {"Keep first", "Keep last", "Keep last + NG"}:
        raise ValueError(f"Unsupported duplicate handling mode: {mode}")
    groups, blanks = {}, []
    for i, value in enumerate(data[key_column]):
        key = _norm_key(value)
        if key:
            groups.setdefault(key, []).append(i)
        else:
            blanks.append(i)
    keep = list(blanks)
    for indexes in groups.values():
        if mode == "Keep first":
            keep.append(indexes[0])
        elif mode == "Keep last":
            keep.append(indexes[-1])
        else:
            bad = [i for i in indexes if failures[i]]
            keep.append(bad[-1] if bad else indexes[-1])
    return data.iloc[sorted(keep)].copy().reset_index(drop=True)


def _optional_float(value):
    if value is None or (isinstance(value, str) and not value.strip()) or pd.isna(value):
        return None
    result = float(value)
    if not np.isfinite(result):
        raise ValueError("Spec values must be finite numbers.")
    return result


def validate_spec_ranges(spec_rows, categories):
    """Validate spec intervals against X-axis positions; CSV order is irrelevant."""
    categories = list(categories)
    positions = {str(value): i for i, value in enumerate(categories)}
    ranges = []
    for row in spec_rows:
        start, end = str(row.get("Start Point", "")).strip(), str(row.get("End Point", "")).strip()
        if not start or not end:
            continue
        if start not in positions or end not in positions:
            raise ValueError(f"Spec range points must exist on the X-axis: {start} – {end}.")
        lo, hi = positions[start], positions[end]
        if lo > hi:
            raise ValueError(f"Start Point must not come after End Point on the selected X-axis: {start} – {end}.")
        usl, target, lsl = (_optional_float(row.get(k)) for k in ("USL", "Target", "LSL"))
        if usl is not None and lsl is not None and usl <= lsl:
            raise ValueError(f"USL must be greater than LSL in range {start} – {end}.")
        ranges.append({"Start Point": start, "End Point": end, "USL": usl, "Target": target, "LSL": lsl,
                       "start_index": lo, "end_index": hi})
    ranges.sort(key=lambda item: (item["start_index"], item["end_index"]))
    previous_end = -1
    for item in ranges:
        if item["start_index"] <= previous_end:
            raise ValueError(f"Spec ranges cannot overlap: {item['Start Point']} – {item['End Point']}.")
        previous_end = item["end_index"]
    return ranges


def spec_limits_for_columns(columns, mode="Single Spec", usl=None, target=None, lsl=None, spec_ranges=None):
    columns = list(columns)
    if not columns:
        return []
    if mode != "Multi Spec":
        return [{"Start Point": columns[0], "End Point": columns[-1], "USL": usl, "Target": target, "LSL": lsl,
                 "start_index": 0, "end_index": len(columns)-1}]
    return validate_spec_ranges(spec_ranges or [], columns)


def _values(data, columns):
    columns = list(columns)
    if not columns:
        raise ValueError("Select at least one measurement column.")
    missing = [c for c in columns if c not in data]
    if missing:
        raise ValueError("Measurement column(s) not found: " + ", ".join(missing))
    return data[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)


def _stats(array, usl=None, lsl=None):
    x = np.asarray(array, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    mean = float(np.mean(x)) if n else np.nan
    sd = float(np.std(x, ddof=1)) if n > 1 else np.nan
    above = int((x > usl).sum()) if usl is not None else 0
    below = int((x < lsl).sum()) if lsl is not None else 0
    failed = int(((x > usl) | (x < lsl)).sum()) if usl is not None and lsl is not None else (above if usl is not None else below)
    within = float(np.std(np.diff(x), ddof=1) / np.sqrt(2)) if n > 2 else np.nan
    cp = cpk = np.nan
    if usl is not None and lsl is not None and np.isfinite(within) and within > 0:
        cp = (usl-lsl)/(6*within)
        cpk = min((usl-mean)/(3*within), (mean-lsl)/(3*within))
    q1, q3 = np.percentile(x, [25, 75]) if n else (np.nan, np.nan)
    iqr = q3-q1
    return {"Count": n, "Mean": mean, "Median": float(np.median(x)) if n else np.nan,
            "Std Dev": sd, "Min": float(np.min(x)) if n else np.nan, "Max": float(np.max(x)) if n else np.nan,
            "Range": float(np.ptp(x)) if n else np.nan, "Cp": cp, "Cpk": cpk,
            "Pp": (usl-lsl)/(6*sd) if usl is not None and lsl is not None and np.isfinite(sd) and sd > 0 else np.nan,
            "Ppk": min((usl-mean)/(3*sd), (mean-lsl)/(3*sd)) if usl is not None and lsl is not None and np.isfinite(sd) and sd > 0 else np.nan,
            "Above USL": above, "Below LSL": below, "Pass": n-failed, "Fail": failed,
            "Yield %": (n-failed)/n*100 if n and (usl is not None or lsl is not None) else np.nan,
            "Outlier Count": int(((x < q1-1.5*iqr) | (x > q3+1.5*iqr)).sum()) if n else 0}


def analyze_measurements(data, columns, usl=None, lsl=None):
    columns = list(columns)
    matrix = _values(data, columns)
    stats = pd.DataFrame([{"Measurement Point": c, **_stats(matrix[:, i], usl, lsl)} for i, c in enumerate(columns)])
    return stats, _stats(matrix.ravel(), usl, lsl)


def _labels(series):
    return series.astype("object").where(series.notna(), "(blank)").astype(str)


def _group_labels(data, column):
    if not column or column not in data:
        return pd.Series("", index=data.index, dtype="object")
    return _labels(data[column])


def vendor_commonality_summary(data, columns, vendor_column, facet_column="", usl=None, lsl=None):
    """Return stable Vendor/Breakdown names for compatibility with callers and reports."""
    cols = list(columns)
    out_cols = ["Vendor", "Breakdown", "Fail N", "Fail % of Total", "Pass N", "Pass % of Total", "Total N"]
    if not vendor_column or vendor_column not in data:
        return pd.DataFrame(columns=out_cols)
    values = data[cols].apply(pd.to_numeric, errors="coerce")
    valid = values.notna().any(axis=1)
    fail = pd.Series(False, index=data.index, dtype=bool)
    if usl is not None:
        fail |= values.gt(usl).any(axis=1)
    if lsl is not None:
        fail |= values.lt(lsl).any(axis=1)
    vendor = _group_labels(data, vendor_column)
    breakdown = _group_labels(data, facet_column) if facet_column and facet_column in data and facet_column != vendor_column else pd.Series("All units", index=data.index)
    frame = pd.DataFrame({"Vendor": vendor, "Breakdown": breakdown, "__fail": fail, "__valid": valid})
    frame = frame.loc[frame["__valid"] & frame["Vendor"].ne("(blank)") & frame["Breakdown"].ne("(blank)")]
    if frame.empty:
        return pd.DataFrame(columns=out_cols)
    grouped = frame.groupby(["Vendor", "Breakdown", "__fail"], observed=True).size().unstack("__fail", fill_value=0).reindex(columns=[False, True], fill_value=0)
    result = grouped.reset_index()
    result["Pass N"] = grouped[False].to_numpy()
    result["Fail N"] = grouped[True].to_numpy()
    total = int(result["Pass N"].sum()+result["Fail N"].sum())
    result["Pass % of Total"] = result["Pass N"]/total*100 if total else 0.0
    result["Fail % of Total"] = result["Fail N"]/total*100 if total else 0.0
    result["Total N"] = result["Pass N"]+result["Fail N"]
    return result[out_cols].sort_values(["Vendor", "Breakdown"], kind="stable").reset_index(drop=True)


def vendor_summary(data, columns, group_column, usl=None, lsl=None):
    return vendor_commonality_summary(data, columns, group_column, "", usl, lsl)


def fail_sn_list(data, columns, key_column, specs):
    output = []
    if not key_column or key_column not in data:
        return pd.DataFrame(columns=["Fail SN", "Fail position", "Fail value"])
    vals = data[list(columns)].apply(pd.to_numeric, errors="coerce")
    for spec in specs:
        for column in columns[spec["start_index"]:spec["end_index"]+1]:
            series = vals[column]
            mask = series.notna()
            if spec.get("USL") is not None:
                mask &= series > spec["USL"]
            if spec.get("LSL") is not None:
                mask |= series.notna() & (series < spec["LSL"])
            for index in data.index[mask]:
                output.append({"Fail SN": data.at[index, key_column], "Fail position": column, "Fail value": float(series.at[index])})
    return pd.DataFrame(output, columns=["Fail SN", "Fail position", "Fail value"])


def dashboard_findings(data, columns, group_column="", usl=None, lsl=None):
    values = data[list(columns)].apply(pd.to_numeric, errors="coerce")
    bad = pd.DataFrame(False, index=data.index, columns=values.columns)
    if usl is not None:
        bad |= values.gt(usl)
    if lsl is not None:
        bad |= values.lt(lsl)
    rows = [{"Finding": "Top Fail Measurement Point", "Category": c, "Count": int(bad[c].sum())} for c in bad if bad[c].any()]
    if bad.to_numpy().any() and group_column in data:
        counts = _group_labels(data, group_column).loc[bad.any(axis=1)].value_counts().drop("(blank)", errors="ignore")
        if not counts.empty:
            rows.append({"Finding": "Top Fail Vendor", "Category": counts.index[0], "Count": int(counts.iloc[0])})
    return pd.DataFrame(rows, columns=["Finding", "Category", "Count"])


def _draw_specs(ax, columns, specs):
    for spec in specs:
        lo, hi = spec["start_index"], spec["end_index"]
        for key, color, label in (("USL", "#e53949", "USL"), ("Target", "#20a45b", "Target"), ("LSL", "#e53949", "LSL")):
            value = spec.get(key)
            if value is not None:
                ax.plot([lo, hi], [value, value], linestyle="--", linewidth=1.5, color=color, label=label if lo == 0 else "_nolegend_")
                if key in {"USL", "LSL"}:
                    ax.text((lo+hi)/2, value, f"{label} {value:g}", color=color, fontsize=7, ha="center", va="bottom")
        if spec.get("USL") is not None and spec.get("LSL") is not None:
            denom = max(1, len(columns)-1)
            ax.axhspan(spec["LSL"], spec["USL"], xmin=lo/denom, xmax=hi/denom, color="#68d8dc", alpha=.14, zorder=0)


def render_facet_chart(data, columns, *, vendor_column, facet_column="", usl=None, lsl=None, target=None,
                       sample_limit=350, figure=None, vendor_values=None, facet_values=None, highlight_oos=True,
                       spec_ranges=None, spec_mode="Single Spec"):
    columns = list(columns)
    if vendor_column not in data:
        raise ValueError("Choose a vendor/group column for the breakdown chart.")
    values = data[columns].apply(pd.to_numeric, errors="coerce")
    vendors_all = _group_labels(data, vendor_column)
    facets_all = _group_labels(data, facet_column) if facet_column and facet_column in data else pd.Series("All units", index=data.index)
    vendors = list(vendor_values) if vendor_values is not None else [x for x in vendors_all.unique() if x != "(blank)"]
    facets = list(facet_values) if facet_values is not None else [x for x in facets_all.unique() if x != "(blank)"]
    vendors = vendors[:8] or ["(no selected vendors)"]
    facets = facets[:8] or ["(no selected breakdowns)"]
    specs = spec_limits_for_columns(columns, spec_mode, usl, target, lsl, spec_ranges)
    failed = pd.Series(False, index=data.index, dtype=bool)
    for spec in specs:
        segment = values.iloc[:, spec["start_index"]:spec["end_index"]+1]
        if spec.get("USL") is not None:
            failed |= segment.gt(spec["USL"]).any(axis=1)
        if spec.get("LSL") is not None:
            failed |= segment.lt(spec["LSL"]).any(axis=1)
    fig = figure or plt.figure(figsize=(14, 8))
    fig.clear()
    axes = fig.subplots(len(facets), len(vendors), squeeze=False, sharex=True, sharey=True)
    x = np.arange(len(columns))
    for r, facet in enumerate(facets):
        for c, vendor in enumerate(vendors):
            ax = axes[r, c]
            ids = np.flatnonzero((vendors_all.eq(vendor) & facets_all.eq(facet)).to_numpy())
            if len(ids) > sample_limit:
                ids = ids[np.linspace(0, len(ids)-1, sample_limit, dtype=int)]
            for idx in ids:
                bad = bool(failed.iloc[idx])
                ax.plot(x, values.iloc[idx].to_numpy(dtype=float), color="#cf142b" if highlight_oos and bad else "#74a9ff",
                        linewidth=1.7 if bad else .65, alpha=.95 if bad else .30)
            _draw_specs(ax, columns, specs)
            ax.set_title(str(vendor), fontsize=10, fontweight="bold")
            ax.grid(alpha=.18)
            if c == 0:
                ax.set_ylabel(f"{facet_column or 'Breakdown'}: {facet}\nMeasurement")
            if r == len(facets)-1:
                ax.set_xticks(x, columns, rotation=90, fontsize=7)
    fig.suptitle(f"Measurement offset by {vendor_column}" + (f" and {facet_column}" if facet_column else ""), fontweight="bold")
    if any(s.get(k) is not None for s in specs for k in ("USL", "LSL", "Target")):
        handles, labels = axes[0, 0].get_legend_handles_labels()
        if handles:
            fig.legend(handles, labels, loc="upper right")
    fig.tight_layout(rect=(.02, .02, .98, .94))
    return fig


def render_chart(data, columns, chart_type, *, group_column="", id_column="", vendor_column="", bm_column="",
                 usl=None, lsl=None, target=None, highlight_oos=True, selected_vendor="", sample_limit=500,
                 figure=None, spec_ranges=None, spec_mode="Single Spec"):
    columns = list(columns)
    values = data[columns].apply(pd.to_numeric, errors="coerce")
    fig = figure or plt.figure(figsize=(11, 6))
    fig.clear()
    ax = fig.add_subplot(111)
    specs = spec_limits_for_columns(columns, spec_mode, usl, target, lsl, spec_ranges)
    failed = pd.Series(False, index=data.index, dtype=bool)
    for spec in specs:
        segment = values.iloc[:, spec["start_index"]:spec["end_index"]+1]
        if spec.get("USL") is not None:
            failed |= segment.gt(spec["USL"]).any(axis=1)
        if spec.get("LSL") is not None:
            failed |= segment.lt(spec["LSL"]).any(axis=1)
    x = np.arange(len(columns))
    if chart_type == "Multi-Line Trend Chart":
        ids = np.arange(len(data))
        if len(ids) > sample_limit:
            ids = ids[np.linspace(0, len(ids)-1, sample_limit, dtype=int)]
        for i in ids:
            bad = bool(failed.iloc[i])
            ax.plot(x, values.iloc[i].to_numpy(), color="#cf142b" if highlight_oos and bad else "#74a9ff",
                    alpha=.9 if bad else .3, linewidth=1.5 if bad else .65)
        ax.set_xticks(x, columns, rotation=45, ha="right")
        ax.set_xlabel("Measurement point")
        ax.set_ylabel("Measurement value")
    elif chart_type in ("Vendor Comparison Chart", "Average Trend Chart"):
        labels = _group_labels(data, group_column) if group_column in data else None
        if chart_type == "Vendor Comparison Chart" and labels is not None:
            for name in labels.unique():
                if name != "(blank)":
                    ax.plot(x, values.loc[labels.eq(name)].mean(axis=0), marker="o", label=name)
            ax.legend(title=group_column)
        else:
            ax.plot(x, values.mean(axis=0), marker="o", label="Mean")
        ax.set_xticks(x, columns, rotation=45, ha="right")
        ax.set_xlabel("Measurement point")
        ax.set_ylabel("Measurement value")
    elif chart_type == "Box Plot by Vendor":
        if group_column not in data:
            raise ValueError("Choose a vendor field for box plots.")
        labels = _group_labels(data, group_column)
        names = [n for n in labels.unique() if n != "(blank)"][:40]
        ax.boxplot([values.loc[labels.eq(n)].to_numpy().ravel() for n in names], tick_labels=names, showfliers=False)
        ax.set_xlabel(group_column)
        ax.set_ylabel("Measurement value")
        ax.tick_params(axis="x", rotation=45)
    elif chart_type == "Histogram":
        ax.hist(values.to_numpy().ravel(), bins="fd", color="#4472c4", alpha=.8)
        ax.set_xlabel("Measurement value")
        ax.set_ylabel("Frequency")
    elif chart_type == "Scatter Plot":
        if len(columns) < 2:
            raise ValueError("Select at least two measurements for scatter plot.")
        ax.scatter(values.iloc[:, 0], values.iloc[:, 1], c=np.where(failed, "#cf142b", "#4472c4"), alpha=.6)
        ax.set_xlabel(columns[0])
        ax.set_ylabel(columns[1])
    elif chart_type == "Control/SPC Chart":
        series = values.iloc[:, 0].to_numpy(dtype=float)
        mean = float(np.nanmean(series)) if np.isfinite(series).any() else np.nan
        sd = float(np.nanstd(series, ddof=1)) if np.isfinite(series).sum() > 1 else np.nan
        ax.plot(np.arange(len(series)), series, color="#4472c4", linewidth=.8)
        ax.axhline(mean, color="green", label="Center")
        if np.isfinite(sd):
            ax.axhline(mean+3*sd, color="#cf142b", linestyle="--", label="UCL")
            ax.axhline(mean-3*sd, color="#cf142b", linestyle="--", label="LCL")
        ax.set_xlabel(id_column or "Unit/row")
        ax.set_ylabel(columns[0])
        ax.legend()
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")
    if chart_type not in ("Control/SPC Chart", "Histogram", "Scatter Plot"):
        _draw_specs(ax, columns, specs)
    ax.set_title(f"{chart_type} — vendor: {group_column or 'All'}")
    ax.grid(alpha=.2)
    fig.tight_layout()
    return fig


def export_engineering_charts(output_path, figures, stats, overall, vendors, spec_analysis,
                              spc_metrics=None, mapped_data=None, failures=None, include_charts=True,
                              include_summary=True, include_stats=True, include_failures=True, include_data=True):
    path = Path(output_path).with_suffix(".xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    from openpyxl import Workbook
    workbook = load_workbook(path) if path.exists() else Workbook()
    if workbook.sheetnames == ["Sheet"] and workbook["Sheet"]["A1"].value is None:
        workbook.remove(workbook.active)
    def add_table(name, frame):
        if name in workbook.sheetnames:
            del workbook[name]
        sheet = workbook.create_sheet(name)
        if frame is None or frame.empty:
            return
        for j, column in enumerate(frame.columns, 1):
            sheet.cell(1, j, str(column))
        for i, row in enumerate(frame.itertuples(index=False, name=None), 2):
            for j, value in enumerate(row, 1):
                if isinstance(value, np.generic):
                    value = value.item()
                sheet.cell(i, j, None if pd.isna(value) else value)
    if include_charts:
        if "Charts" in workbook.sheetnames:
            del workbook["Charts"]
        sheet = workbook.create_sheet("Charts")
        items = figures.items() if isinstance(figures, dict) else [("Chart", figures)]
        for i, (name, figure) in enumerate(items, 1):
            sheet.cell(1+(i-1)*25, 1, name)
            buffer = BytesIO()
            figure.savefig(buffer, format="png", dpi=130, bbox_inches="tight")
            buffer.seek(0)
            image = XLImage(buffer)
            image.width, image.height = 900, 480
            image.anchor = f"A{2+(i-1)*25}"
            sheet.add_image(image)
    if include_stats:
        add_table("EngineeringStats", stats)
    if include_summary:
        add_table("VendorCommonality", vendors)
    if include_failures:
        add_table("FailSNList", failures)
    add_table("SpecAnalysis", spec_analysis)
    if spc_metrics is not None:
        add_table("SPCMetrics", spc_metrics)
    if include_data and mapped_data is not None:
        add_table("MappedUnits", mapped_data)
    workbook.save(path)
    return path


def export_pdf_report(output_path, figures, summary, overall, title="Engineering Chart Report",
                      stats=None, failures=None, include_charts=True, include_summary=True,
                      include_stats=True, include_failures=True):
    path = Path(output_path).with_suffix(".pdf")
    path.parent.mkdir(parents=True, exist_ok=True)
    chart_items = list(figures.items()) if isinstance(figures, dict) else [("Chart", figures)]
    with PdfPages(path) as pdf:
        if include_charts:
            for chart_name, figure in chart_items:
                figure.suptitle(f"{title}\n{chart_name}", fontweight="bold")
                pdf.savefig(figure, bbox_inches="tight")
        if include_summary or include_stats or (include_failures and failures is not None and not failures.empty):
            figure, ax = plt.subplots(figsize=(11.7, 8.3))
            ax.axis("off")
            ax.set_title(title, fontsize=16, fontweight="bold")
            y = .94
            if include_stats:
                ax.text(.02, y, "Engineering statistics", fontweight="bold", transform=ax.transAxes)
                y -= .03
                table = pd.DataFrame([{"Metric": k, "Value": v} for k, v in overall.items()])
                ax.table(cellText=table.fillna("").astype(str).values, colLabels=table.columns,
                         loc="upper left", bbox=[.02, y-.25, .46, .24])
                y -= .29
            if include_summary and summary is not None and not summary.empty:
                ax.text(.02, y, "Vendor Pass/Fail commonality", fontweight="bold", transform=ax.transAxes)
                y -= .03
                shown = summary.head(22).fillna("").astype(str)
                ax.table(cellText=shown.values, colLabels=shown.columns, loc="upper left", bbox=[.02, y-.35, .96, .34])
                y -= .39
            if include_failures and failures is not None and not failures.empty:
                ax.text(.02, y, "Fail SN list", fontweight="bold", transform=ax.transAxes)
                y -= .03
                shown = failures.head(15).fillna("").astype(str)
                ax.table(cellText=shown.values, colLabels=shown.columns, loc="upper left", bbox=[.02, max(.02, y-.3), .96, .29])
            pdf.savefig(figure, bbox_inches="tight")
            plt.close(figure)
    return path
