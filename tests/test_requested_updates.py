import numpy as np
import pandas as pd
import pytest
from engineering_charts import deduplicate_units, fail_sn_list, spec_limits_for_columns, validate_spec_ranges, vendor_commonality_summary


def test_multispec_ranges_validate_and_reject_overlap():
    columns=["11AA","11AB","11AC","11BA"]
    ranges=[{"Start Point":"11AA","End Point":"11AB","USL":".12","Target":"0","LSL":"-.14"},{"Start Point":"11AC","End Point":"11BA","USL":".1","Target":"","LSL":"-.1"}]
    assert len(spec_limits_for_columns(columns,"Multi Spec",spec_ranges=ranges))==2
    with pytest.raises(ValueError):
        validate_spec_ranges([ranges[0],{"Start Point":"11AB","End Point":"11AC","USL":1,"LSL":0}],columns)


def test_duplicate_keep_last_plus_ng_preserves_failure_row():
    data=pd.DataFrame({"SN":["a","a","b"],"M":[1,2,3]})
    result=deduplicate_units(data,"SN","Keep last + NG",[True,False,False])
    assert result.loc[result.SN.eq("a"),"M"].iloc[0]==1


def test_fail_sn_list_reports_position_value():
    data=pd.DataFrame({"SN":["A","B"],"11AA":[.2,0.0],"11AB":[0.0,-.3]})
    specs=[{"start_index":0,"end_index":1,"USL":.1,"LSL":-.2}]
    result=fail_sn_list(data,["11AA","11AB"],"SN",specs)
    assert set(result["Fail SN"])=={"A","B"}
    assert set(result.columns)=={"Fail SN","Fail position","Fail value"}


def test_vendor_commonality_has_vendor_and_facet_values():
    data=pd.DataFrame({"Vendor":["FX","EVW"],"TrackPad":["LYT","BYD CD"],"M":[.2,0]})
    result=vendor_commonality_summary(data,["M"],"Vendor","TrackPad",usl=.1,lsl=-.2)
    assert "Vendor" in result and "TrackPad" in result
    assert result["Fail N"].sum()==1
