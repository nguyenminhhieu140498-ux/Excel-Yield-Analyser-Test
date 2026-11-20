import pandas as pd
import pytest
from engineering_charts import _optional_float, validate_spec_ranges, vendor_commonality_summary


def test_engineering_charts_module_imports_without_optional_float_name_error():
    assert _optional_float(".12") == .12
    assert _optional_float("") is None


def test_spec_ranges_sorted_and_nonoverlapping_by_axis_not_csv_order():
    axis=["11AA","11AB","11AC","11BA","11BB","11BC"]
    rows=[{"Start Point":"11BA","End Point":"11BC","USL":".13","Target":"0","LSL":"-.18"},
          {"Start Point":"11AA","End Point":"11AC","USL":".09","Target":"0","LSL":"-.14"}]
    result=validate_spec_ranges(rows,axis)
    assert [r["Start Point"] for r in result]==["11AA","11BA"]
    with pytest.raises(ValueError,match="cannot overlap"):
        validate_spec_ranges([rows[0],{"Start Point":"11AC","End Point":"11BA","USL":1,"LSL":0}],axis)


def test_vendor_summary_keeps_legacy_vendor_breakdown_columns():
    data=pd.DataFrame({"Vendor":["EVW","EVW"],"Family":["BYD","LYT"],"M":[0,.2]})
    result=vendor_commonality_summary(data,["M"],"Vendor","Family",usl=.1,lsl=-.1)
    assert {"Vendor","Breakdown","Fail N","Pass N"}.issubset(result.columns)
