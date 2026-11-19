from __future__ import annotations

import py_compile

for name in ("engineering_charts.py", "engineering_chart_analyzer.py"):
    py_compile.compile(name, doraise=True)
print("Python syntax OK")
