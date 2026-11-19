"""Engineering measurements, automatic unit mapping, statistics, and charts."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage

CHART_TYPES = [
    "Multi-Line Trend Chart", "Vendor Comparison Chart", "Average Trend Chart",
    "Box Plot by Vendor", "Histogram", "Scatter Plot", "Control/SPC Chart",
]
KEY_HINTS = ("serial number", "serial_number", "serialnumber", "unit id", "unit_id", "unitid", "serial", "sn")
GROUP_HINTS = ("vendor", "supplier", "manufacturer", "maker")


def _norm_name(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _norm_key(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().upper()
    # Excel frequently reads numeric-looking serials as 123.0.
    text = re.sub(r"\.0+$", "", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def detect_key_column(data: pd.DataFrame) -> str | None:
    """Detect likely unit/serial-number columns by common manufacturing names."""
    if data is None or data.empty:
        return None
    normalized = {_norm_name(c): str(c) for c in data.columns}
    for hint in KEY_HINTS:
        key = _norm_name(hint)
        if key in normalized:
            return normalized[key]
    for col in data.columns:
        name = _norm_name(col)
        if name in {"sn", "serial", "serialno", "serialnumber", "unitid", "unitnumber"} or "serialnumber" in name:
            return str(col)
    return None


def detect_group_column(data: pd.DataFrame) -> str | None:
    if data is None:
        return None
    for col in data.columns:
        if any(hint in _norm_name(col) for hint in GROUP_HINTS):
            return str(col)
    return None


def numeric_columns(data: pd.DataFrame) -> list[str]:
    """Columns containing at least one numeric value; numeric text is accepted."""
    return [str(c) for c in data.columns if pd.to_numeric(data[c], errors="coerce").notna().any()]


def auto_map_units(unit_data: pd.DataFrame, mapping_data: pd.DataFrame,
                   unit_key: str | None = None, mapping_key: str | None = None,
                   append_columns: Iterable[str] | None = None) -> tuple[pd.DataFrame, dict]:
    """Join unit measurements with vendor/build metadata using normalized IDs.

    Matching is exact after trimming, case-folding, and removing punctuation.
    Duplicate mapping IDs keep their first row; all original unit rows/order are kept.
    """
    if unit_data is None or mapping_data is None:
        raise ValueError("Load both measurement and mapping worksheets first.")
    unit_key = unit_key or detect_key_column(unit_data)
    mapping_key = mapping_key or detect_key_column(mapping_data)
    if not unit_key or unit_key not in unit_data.columns:
        raise ValueError("Could not detect the unit serial-number column; select it manually.")
    if not mapping_key or mapping_key not in mapping_data.columns:
        raise ValueError("Could not detect the mapping serial-number column; select it manually.")

    if append_columns is None:
        append_columns = [c for c in mapping_data.columns if c != mapping_key and c not in unit_data.columns]
    append_columns = list(dict.fromkeys(append_columns))
    missing = [c for c in append_columns if c not in mapping_data.columns]
    if missing:
        raise ValueError("Mapping column(s) not found: " + ", ".join(map(str, missing)))
    append_columns = [c for c in append_columns if c != mapping_key and c not in unit_data.columns]

    left = unit_data.copy()
    right = mapping_data[[mapping_key, *append_columns]].copy()
    left["__unit_map_key__"] = left[unit_key].map(_norm_key)
    right["__unit_map_key__"] = right[mapping_key].map(_norm_key)
    right = right[right["__unit_map_key__"].ne("")].drop_duplicates("__unit_map_key__", keep="first")
    right = right.drop(columns=[mapping_key])
    left["__unit_map_order__"] = np.arange(len(left))
    merged = left.merge(right, how="left", on="__unit_map_key__", sort=False, validate="many_to_one")
    matched = int(merged["__unit_map_key__"].isin(right["__unit_map_key__"]).sum())
    merged = merged.sort_values("__unit_map_order__", kind="stable").drop(
        columns=["__unit_map_key__", "__unit_map_order__"]
    ).reset_index(drop=True)
    total = len(unit_data)
    return merged, {
        "unit_rows": total,
        "matched_rows": matched,
        "unmatched_rows": total - matched,
        "match_rate_pct": matched / total * 100 if total else 0.0,
        "unit_key": unit_key,
        "mapping_key": mapping_key,
        "mapped_columns": append_columns,
    }


def _values(data: pd.DataFrame, columns: Iterable[str]) -> np.ndarray:
    columns = list(columns)
    if not columns:
        raise ValueError("Select at least one measurement column.")
    missing = [c for c in columns if c not in data]
    if missing:
        raise ValueError("Measurement column(s) not found: " + ", ".join(missing))
    return data[columns].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)


def _stats(array: np.ndarray, usl=None, lsl=None) -> dict:
    x = np.asarray(array, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    mean = float(np.mean(x)) if n else np.nan
    sd = float(np.std(x, ddof=1)) if n > 1 else np.nan
    above = int((x > usl).sum()) if usl is not None else 0
    below = int((x < lsl).sum()) if lsl is not None else 0
    failed = int(((x > usl) if lsl is None else (x < lsl) if usl is None else ((x > usl) | (x < lsl))).sum()) if (usl is not None or lsl is not None) else 0
    within = float(np.std(np.diff(x), ddof=1) / np.sqrt(2)) if n > 2 else np.nan
    cp = cpk = np.nan
    if usl is not None and lsl is not None and np.isfinite(within) and within > 0:
        cp = (usl - lsl) / (6 * within)
        cpk = min((usl - mean) / (3 * within), (mean - lsl) / (3 * within))
    q1, q3 = np.percentile(x, [25, 75]) if n else (np.nan, np.nan)
    iqr = q3 - q1
    return {
        "Count": n, "Mean": mean, "Median": float(np.median(x)) if n else np.nan,
        "Std Dev": sd, "Min": float(np.min(x)) if n else np.nan,
        "Max": float(np.max(x)) if n else np.nan, "Range": float(np.ptp(x)) if n else np.nan,
        "Cp": cp, "Cpk": cpk, "Pp": (usl - lsl) / (6 * sd) if usl is not None and lsl is not None and np.isfinite(sd) and sd > 0 else np.nan,
        "Ppk": min((usl - mean) / (3 * sd), (mean - lsl) / (3 * sd)) if usl is not None and lsl is not None and np.isfinite(sd) and sd > 0 else np.nan,
        "Above USL": above, "Below LSL": below, "Pass": n - failed, "Fail": failed,
        "Yield %": (n - failed) / n * 100 if n and (usl is not None or lsl is not None) else np.nan,
        "Outlier Count": int(((x < q1 - 1.5 * iqr) | (x > q3 + 1.5 * iqr)).sum()) if n else 0,
    }


def analyze_measurements(data: pd.DataFrame, columns: Iterable[str], usl=None, lsl=None):
    columns = list(columns)
    matrix = _values(data, columns)
    overall = _stats(matrix.ravel(), usl, lsl)
    by_point = pd.DataFrame([{"Measurement Point": c, **_stats(matrix[:, i], usl, lsl)} for i, c in enumerate(columns)])
    return by_point, overall


def vendor_summary(data: pd.DataFrame, columns: Iterable[str], group_column: str, usl=None, lsl=None):
    if not group_column or group_column not in data:
        return pd.DataFrame()
    matrix = data[list(columns)].apply(pd.to_numeric, errors="coerce")
    records = []
    for group, indexes in data.groupby(group_column, dropna=False, sort=False).groups.items():
        stats = _stats(matrix.loc[indexes].to_numpy().ravel(), usl, lsl)
        records.append({"Vendor": "(blank)" if pd.isna(group) else str(group), "Sample Count": stats["Count"],
                        "Average": stats["Mean"], "Minimum": stats["Min"], "Maximum": stats["Max"],
                        "Std Dev": stats["Std Dev"], "Cpk": stats["Cpk"], "Yield %": stats["Yield %"],
                        "Out-of-spec Count": stats["Fail"]})
    out = pd.DataFrame(records)
    if not out.empty:
        out = out.sort_values(["Yield %", "Cpk", "Std Dev"], ascending=[False, False, True], na_position="last").reset_index(drop=True)
        out.insert(0, "Rank", np.arange(1, len(out) + 1))
    return out


def dashboard_findings(data: pd.DataFrame, columns: Iterable[str], group_column="", usl=None, lsl=None):
    values = data[list(columns)].apply(pd.to_numeric, errors="coerce")
    bad = pd.DataFrame(False, index=data.index, columns=values.columns)
    if usl is not None: bad |= values.gt(usl)
    if lsl is not None: bad |= values.lt(lsl)
    rows = [{"Finding": "Top Fail Measurement Point", "Category": c, "Count": int(bad[c].sum())}
            for c in bad if bad[c].any()]
    if bad.to_numpy().any():
        unit_bad = bad.any(axis=1)
        candidates = [(group_column, "Top Fail Vendor"), ("Build Matrix", "Top Fail BM"), ("BM", "Top Fail BM"), ("Station", "Top Fail Station")]
        added = set()
        for col, label in candidates:
            if col and col in data and label not in added:
                counts = data.loc[unit_bad, col].fillna("(blank)").astype(str).value_counts()
                if not counts.empty:
                    rows.append({"Finding": label, "Category": counts.index[0], "Count": int(counts.iloc[0])})
                    added.add(label)
    return pd.DataFrame(rows, columns=["Finding", "Category", "Count"])


def _spec_lines(ax, usl, lsl, target):
    if usl is not None: ax.axhline(usl, color="#e53949", linestyle="--", linewidth=1.1, label="USL")
    if target is not None: ax.axhline(target, color="#27ae60", linestyle="--", linewidth=1.1, label="Target")
    if lsl is not None: ax.axhline(lsl, color="#e53949", linestyle="--", linewidth=1.1, label="LSL")
    if usl is not None and lsl is not None and usl > lsl:
        ax.axhspan(lsl, usl, color="#68d8dc", alpha=.22, zorder=0)


def render_facet_chart(data: pd.DataFrame, columns: Iterable[str], *, vendor_column: str,
                       facet_column: str = "", usl=None, lsl=None, target=None,
                       sample_limit=350, figure=None):
    """Offset-style small multiples: vendor panels across, optional facet rows down."""
    if vendor_column not in data:
        raise ValueError("Choose a vendor/group column for the breakdown chart.")
    columns = list(columns)
    values = data[columns].apply(pd.to_numeric, errors="coerce")
    vendors = data[vendor_column].fillna("(blank)").astype(str).unique().tolist()[:6]
    if facet_column and facet_column in data:
        facets = data[facet_column].fillna("(blank)").astype(str).unique().tolist()[:6]
    else:
        facet_column, facets = "", ["All units"]
    fig = figure or plt.figure(figsize=(14, 8))
    fig.clear()
    axes = fig.subplots(len(facets), len(vendors), squeeze=False, sharex=True, sharey=True)
    vendor_values = data[vendor_column].fillna("(blank)").astype(str)
    facet_values = data[facet_column].fillna("(blank)").astype(str) if facet_column else pd.Series("All units", index=data.index)
    unit_oos = pd.Series(False, index=data.index)
    if usl is not None: unit_oos |= values.gt(usl).any(axis=1)
    if lsl is not None: unit_oos |= values.lt(lsl).any(axis=1)
    x = np.arange(len(columns))
    for r, facet in enumerate(facets):
        for c, vendor in enumerate(vendors):
            ax = axes[r, c]
            mask = vendor_values.eq(vendor) & facet_values.eq(facet)
            ids = np.flatnonzero(mask.to_numpy())
            if len(ids) > sample_limit:
                ids = ids[np.linspace(0, len(ids)-1, sample_limit, dtype=int)]
            for idx in ids:
                y = values.iloc[idx].to_numpy(dtype=float)
                failed = bool(unit_oos.iloc[idx])
                ax.plot(x, y, color="#cf142b" if failed else "#74a9ff",
                        linewidth=1.65 if failed else .65,
                        alpha=.95 if failed else .30, zorder=3 if failed else 2)
            _spec_lines(ax, usl, lsl, target)
            ax.set_title(vendor, fontsize=10, fontweight="bold")
            ax.grid(alpha=.18)
            if c == 0:
                ax.set_ylabel(f"{facet}\nMeasurement")
            if r == len(facets)-1:
                ax.set_xticks(x, columns, rotation=90, fontsize=7)
    fig.suptitle("Measurement offset by vendor" + (f" and {facet_column}" if facet_column else ""), fontweight="bold")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper right")
    fig.tight_layout(rect=(0.02, 0.02, .98, .94))
    return fig


def render_chart(data: pd.DataFrame, columns: Iterable[str], chart_type: str, *, group_column="",
                 id_column="", vendor_column="", bm_column="", usl=None, lsl=None,
                 target=None, highlight_oos=True, selected_vendor="", sample_limit=500,
                 figure=None):
    columns = list(columns)
    values = data[columns].apply(pd.to_numeric, errors="coerce")
    fig = figure or plt.figure(figsize=(11, 6))
    fig.clear()
    ax = fig.add_subplot(111)
    failed = pd.Series(False, index=data.index)
    if usl is not None: failed |= values.gt(usl).any(axis=1)
    if lsl is not None: failed |= values.lt(lsl).any(axis=1)
    if chart_type == "Multi-Line Trend Chart":
        chosen = np.arange(len(data))
        if len(chosen) > sample_limit: chosen = chosen[np.linspace(0, len(chosen)-1, sample_limit, dtype=int)]
        for idx in chosen:
            is_fail = bool(failed.iloc[idx])
            is_vendor = bool(selected_vendor and group_column in data and str(data.iloc[idx][group_column]) == selected_vendor)
            ax.plot(np.arange(len(columns)), values.iloc[idx].to_numpy(),
                    color="#cf142b" if highlight_oos and is_fail else ("#2878b5" if is_vendor else "#9aa0a6"),
                    alpha=.95 if is_fail or is_vendor else .2,
                    linewidth=1.6 if is_fail else .65)
        ax.set_xticks(np.arange(len(columns)), columns, rotation=45, ha="right")
        ax.set_xlabel("Measurement point"); ax.set_ylabel("Measurement value")
    elif chart_type in ("Vendor Comparison Chart", "Average Trend Chart"):
        if chart_type == "Vendor Comparison Chart" and group_column in data:
            for name, ix in data.groupby(group_column, dropna=False, sort=False).groups.items():
                ax.plot(columns, values.loc[ix].mean(axis=0), marker="o", label=str(name))
            ax.legend(title=group_column)
        else:
            ax.plot(columns, values.mean(axis=0), marker="o", label="Mean")
        ax.tick_params(axis="x", rotation=45); ax.set_ylabel("Measurement value")
    elif chart_type == "Box Plot by Vendor":
        if group_column not in data: raise ValueError("Choose a group column for vendor box plots.")
        groups = data.assign(__group=data[group_column].fillna("(blank)").astype(str)).melt(id_vars="__group", value_vars=columns).dropna()
        names = groups["__group"].unique().tolist()[:40]
        ax.boxplot([groups.loc[groups.__group.eq(name), "value"] for name in names], tick_labels=names, showfliers=False)
        ax.set_ylabel("Measurement value"); ax.tick_params(axis="x", rotation=45)
    elif chart_type == "Histogram":
        ax.hist(values.to_numpy().ravel(), bins="fd", color="#4472c4", alpha=.8)
    elif chart_type == "Scatter Plot":
        if len(columns) < 2: raise ValueError("Select at least two measurements for scatter plot.")
        ax.scatter(values.iloc[:, 0], values.iloc[:, 1], c=np.where(failed, "#cf142b", "#4472c4"), alpha=.6)
        ax.set_xlabel(columns[0]); ax.set_ylabel(columns[1])
    elif chart_type == "Control/SPC Chart":
        series = values.iloc[:, 0].to_numpy(dtype=float)
        mean = float(np.nanmean(series)) if np.isfinite(series).any() else np.nan
        sd = float(np.nanstd(series, ddof=1)) if np.isfinite(series).sum() > 1 else np.nan
        ax.plot(np.arange(len(series)), series, color="#4472c4", linewidth=.8)
        ax.axhline(mean, color="green", label="Center")
        if np.isfinite(sd):
            ax.axhline(mean+3*sd, color="#cf142b", linestyle="--", label="UCL")
            ax.axhline(mean-3*sd, color="#cf142b", linestyle="--", label="LCL")
        ax.legend(); ax.set_ylabel(columns[0])
    else:
        raise ValueError(f"Unsupported chart type: {chart_type}")
    if chart_type != "Control/SPC Chart": _spec_lines(ax, usl, lsl, target)
    ax.set_title(chart_type); ax.grid(alpha=.2)
    return fig


def export_engineering_charts(output_path: str | Path, figure, stats: pd.DataFrame,
                              overall: dict, vendors: pd.DataFrame,
                              spec_analysis: pd.DataFrame,
                              spc_metrics: pd.DataFrame | None = None,
                              mapped_data: pd.DataFrame | None = None) -> Path:
    path = Path(output_path).with_suffix(".xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        workbook = load_workbook(path)
    else:
        from openpyxl import Workbook
        workbook = Workbook(); workbook.remove(workbook.active)
    sheet_name = "6_EngineeringCharts"
    if sheet_name in workbook.sheetnames: del workbook[sheet_name]
    sheet = workbook.create_sheet(sheet_name)
    sheet["A1"] = "Engineering Chart Analyzer"
    row = 3
    for key, value in overall.items():
        sheet.cell(row, 1, key); sheet.cell(row, 2, None if pd.isna(value) else value); row += 1
    buffer = BytesIO(); figure.savefig(buffer, format="png", dpi=140, bbox_inches="tight"); buffer.seek(0)
    image = XLImage(buffer); image.width = 960; image.height = 520; image.anchor = "D3"; sheet.add_image(image)
    def add_table(title, frame, start_row, start_col=1):
        sheet.cell(start_row, start_col, title)
        if frame is None or frame.empty:
            sheet.cell(start_row+1, start_col, "No data"); return
        for j, name in enumerate(frame.columns, start_col): sheet.cell(start_row+1, j, str(name))
        for i, row_values in enumerate(frame.itertuples(index=False, name=None), start_row+2):
            for j, value in enumerate(row_values, start_col):
                if pd.isna(value): value = None
                elif isinstance(value, np.generic): value = value.item()
                sheet.cell(i, j, value)
    add_table("Measurement statistics", stats, 20)
    add_table("Vendor summary", vendors, 20, max(8, len(stats.columns)+2))
    add_table("Spec analysis", spec_analysis, 40)
    add_table("SPC metrics", spc_metrics, 40, 8)
    if mapped_data is not None: mapped_data.to_excel(workbook, sheet_name="MappedUnits", index=False)
    workbook.save(path)
    return path
