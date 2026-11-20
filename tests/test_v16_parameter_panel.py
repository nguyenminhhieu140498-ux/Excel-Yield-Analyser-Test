"""UI regression test: the full parameter panel is restored by compact launcher."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QScrollArea, QSplitter
import pytest


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_compact_launcher_keeps_parameter_controls_visible(qapp):
    import engineering_chart_analyzer_v16_compact as launcher
    from engineering_chart_analyzer import EngineeringChartWindow

    window = EngineeringChartWindow()
    required = ("unit_key", "vendor_column", "facet_column", "chart_checks", "columns",
                "single_mode", "multi_mode", "spec_table", "build_button")
    assert all(hasattr(window, name) for name in required)
    assert isinstance(window.input_scroll_area, QScrollArea)
    assert window.input_scroll_area.widget() is not None
    splitters = [item for item in window.findChildren(QSplitter)
                 if item.orientation().name == "Horizontal" and item.count() >= 2]
    assert splitters and splitters[0].widget(0) is window.input_scroll_area
    window.close()
