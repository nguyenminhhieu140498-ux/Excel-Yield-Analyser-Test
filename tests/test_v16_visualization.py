import pandas as pd
import numpy as np
from matplotlib.figure import Figure
from engineering_chart_analyzer_v16_debug import render_v16_chart


def test_box_plot_uses_selected_measurement_points_and_numeric_values():
    data = pd.DataFrame({"M1": [1.0, 2.0], "M2": [10.0, 20.0], "Vendor": ["A", "B"]})
    fig = render_v16_chart(data, ["M1", "M2"], "Box Plot by Vendor", figure=Figure())
    ax = fig.axes[0]
    assert ax.get_xlabel() == "Measurement point"
    assert ax.get_ylabel() == "Measurement value"
    assert [tick.get_text() for tick in ax.get_xticklabels()] == ["M1", "M2"]
    assert len(ax.lines) >= 2


def test_multi_line_retains_red_failure_highlight_when_enabled():
    data = pd.DataFrame({"M1": [2.0, 0.0], "M2": [2.0, 0.0]})
    fig = render_v16_chart(data, ["M1", "M2"], "Multi-Line Trend Chart", usl=1.0, highlight_oos=True, figure=Figure())
    assert any(line.get_color() == "#d62728" for line in fig.axes[0].lines)
