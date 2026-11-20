# Fixes for stable Multi Spec validation and legacy commonality-summary API.
# Spec row order in CSV is not significant: return ranges sorted by X-axis order.
def validate_spec_ranges(spec_rows, categories):
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
            raise ValueError(f"Start Point must not come after End Point: {start} – {end}.")
        populated.append(row)
    populated.sort(key=lambda row: positions[str(row.get("Start Point", "")).strip()])

    validated = []
    previous_end = -1
    for row in populated:
        start = str(row["Start Point"]).strip()
        end = str(row["End Point"]).strip()
        lo, hi = positions[start], positions[end]
        if lo <= previous_end:
            raise ValueError(f"Spec ranges cannot overlap: {start} – {end}.")
        usl = _optional_float(row.get("USL"))
        target = _optional_float(row.get("Target"))
        lsl = _optional_float(row.get("LSL"))
        if usl is not None and lsl is not None and usl <= lsl:
            raise ValueError(f"USL must be greater than LSL in range {start} – {end}.")
        validated.append({"Start Point": start, "End Point": end, "USL": usl,
                          "Target": target, "LSL": lsl,
                          "start_index": lo, "end_index": hi})
        previous_end = hi
    return validated


def vendor_commonality_summary(data, columns, vendor_column, facet_column="", usl=None, lsl=None):
    """Return the stable Vendor/Breakdown column names used by existing clients."""
    columns = list(columns)
    output_columns = ["Vendor", "Breakdown", "Fail N", "Fail % of Total",
                      "Pass N", "Pass % of Total", "Total N"]
    if not vendor_column or vendor_column not in data:
        return pd.DataFrame(columns=output_columns)
    values = data[columns].apply(pd.to_numeric, errors="coerce")
    valid = values.notna().any(axis=1)
    fail = pd.Series(False, index=data.index, dtype=bool)
    if usl is not None:
        fail |= values.gt(usl).any(axis=1)
    if lsl is not None:
        fail |= values.lt(lsl).any(axis=1)
    vendor = _group_labels(data, vendor_column)
    breakdown = (_group_labels(data, facet_column)
                 if facet_column and facet_column in data and facet_column != vendor_column
                 else pd.Series("All units", index=data.index))
    frame = pd.DataFrame({"Vendor": vendor, "Breakdown": breakdown,
                          "__fail": fail, "__valid": valid})
    frame = frame.loc[frame["__valid"] & frame["Vendor"].ne("(blank)") & frame["Breakdown"].ne("(blank)")]
    if frame.empty:
        return pd.DataFrame(columns=output_columns)
    grouped = frame.groupby(["Vendor", "Breakdown", "__fail"], observed=True).size().unstack("__fail", fill_value=0)
    grouped = grouped.reindex(columns=[False, True], fill_value=0)
    result = grouped.reset_index().rename(columns={False: "Pass N", True: "Fail N"})
    result["Pass N"] = grouped[False].to_numpy()
    result["Fail N"] = grouped[True].to_numpy()
    total = int(result["Pass N"].sum() + result["Fail N"].sum())
    result["Pass % of Total"] = result["Pass N"] / total * 100 if total else 0.0
    result["Fail % of Total"] = result["Fail N"] / total * 100 if total else 0.0
    result["Total N"] = result["Pass N"] + result["Fail N"]
    return result[output_columns].sort_values(["Vendor", "Breakdown"], kind="stable").reset_index(drop=True)


# Resolve globals used by spec_limits_for_columns and export imported symbols.
_original_optional_float = _optional_float
