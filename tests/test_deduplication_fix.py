import numpy as np
import pandas as pd
import pytest
from deduplication_fix import deduplicate_units


def test_deduplicate_with_full_mask_and_blank_sns_does_not_mismatch_lengths():
    # Mirrors the reported 755 data rows, where two rows have blank SNs.
    data = pd.DataFrame({"SN": [f"U{i}" for i in range(753)] + [None, ""], "M": range(755)})
    mask = np.zeros(len(data), dtype=bool)
    result = deduplicate_units(data, "SN", "Keep last + NG", mask)
    assert len(result) == 755
    assert result["SN"].isna().sum() == 1
    assert (result["SN"] == "").sum() == 1


def test_keep_last_plus_ng_selects_last_failing_retest():
    data = pd.DataFrame({"SN": ["A", "A", "A", "B", "B"], "M": [1, 2, 3, 4, 5]})
    mask = pd.Series([False, True, False, False, False], index=[100, 101, 102, 103, 104])
    result = deduplicate_units(data, "SN", "Keep last + NG", mask)
    assert result.set_index("SN")["M"].to_dict() == {"A": 2, "B": 5}


def test_fail_mask_length_must_match_original_data():
    data = pd.DataFrame({"SN": ["A", None, "B"], "M": [1, 2, 3]})
    with pytest.raises(ValueError, match="exactly 3"):
        deduplicate_units(data, "SN", "Keep last + NG", [True, False])
