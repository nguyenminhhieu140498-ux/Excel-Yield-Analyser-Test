"""Generate a beginner-friendly English PowerPoint user guide with visuals.

Usage: python make_user_guide.py [output.pptx]
Uses a GUI screenshot if supplied via --screenshot PATH; otherwise draws
illustrative app mockups and chart examples from sample data.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

from engineering_charts import render_facet_chart, vendor_commonality_summary

NAVY = RGBColor(25, 45, 75)
BLUE = RGBColor(36, 110, 220)
LIGHT = RGBColor(241, 245, 250)
DARK = RGBColor(35, 44, 58)
GREEN = RGBColor(34, 150, 100)


def add_text(slide, text, x, y, w, h, size=20, color=DARK, bold=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    return box


def add_header(slide, title, step=None):
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(.72))
    band.fill.solid(); band.fill.fore_color.rgb = NAVY; band.line.fill.background()
    add_text(slide, title, .45, .12, 11.6, .48, 25, RGBColor(255,255,255), True)
    if step:
        add_text(slide, step, 11.9, .18, 1.0, .35, 14, RGBColor(210,225,245), True)


def add_footer(slide, number):
    add_text(slide, f"Engineering Chart Analyzer · v1.3 · Hiro Nguyen   |   {number}", .45, 7.18, 12.3, .2, 9, RGBColor(105,115,130))


def add_bullets(slide, items, x, y, w, h, size=19):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.word_wrap = True
    for i, text in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = "•  " + text
        p.font.size = Pt(size); p.font.color.rgb = DARK
        p.space_after = Pt(11)
    return box


def mock_ui(path: Path):
    fig, ax = plt.subplots(figsize=(12, 5.4)); fig.patch.set_facecolor("#f4f6f9"); ax.set_facecolor("#f4f6f9")
    ax.set_xlim(0, 12); ax.set_ylim(0, 6); ax.axis("off")
    def panel(x,y,w,h,label,fill="#ffffff"):
        rect=plt.Rectangle((x,y),w,h,facecolor=fill,edgecolor="#c7d0dc",linewidth=1.1); ax.add_patch(rect)
        if label: ax.text(x+.15,y+h-.25,label,fontsize=9,fontweight="bold",va="top",color="#23344d")
    def button(x,y,w,label,color="#2878dc"):
        rect=plt.Rectangle((x,y),w,.42,facecolor=color,edgecolor=color); ax.add_patch(rect)
        ax.text(x+w/2,y+.21,label,ha="center",va="center",color="white",fontsize=8,fontweight="bold")
    panel(.15,.15,4,5.55,"SETUP")
    button(.35,5.1,1.7,"Open measurements")
    button(2.2,5.1,1.7,"Open unit mapping", "#62758c")
    panel(.35,4.25,3.55,.65,"Unit keys: SN  →  Serial Number")
    button(.55,3.62,3.1,"Auto-map units before charting", "#21885e")
    panel(.35,2.7,3.55,.7,"Vendor / breakdown filters")
    panel(.35,1.58,3.55,.95,"Search & select measurement columns")
    panel(.35,.38,3.55,.9,"USL     Target     LSL")
    panel(4.4,2.55,7.4,3.15,"CHART PREVIEW")
    xx=np.linspace(0,1,26)
    for i in range(10):
        yy=.45+.18*np.sin(xx*8+i*.3)+i*.018
        ax.plot(4.8+xx*6.6,2.9+yy*2.1,color="#58a0ec",alpha=.35,lw=1)
    ax.plot(4.8+xx*6.6,3.6+.7*np.sin(xx*8),color="#d8223f",lw=2)
    ax.axhline(4.65,xmin=.4,xmax=.93,color="#e74458",ls="--")
    panel(4.4,.4,7.4,1.75,"VENDOR PASS / FAIL SUMMARY")
    ax.text(4.7,1.62,"Vendor          Breakdown           Fail N       Pass N        % of total",fontsize=8,fontweight="bold")
    ax.text(4.7,1.18,"EVW              BYD CD                   0              116             20.10%",fontsize=8)
    ax.text(4.7,.78,"FX                 LYT                         1              248             42.98%",fontsize=8)
    fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig)


def demo_chart(path: Path):
    rng=np.random.default_rng(42); rows=72
    data=pd.DataFrame({"Vendor":np.repeat(["EVW","FX"],rows//2),"Family":np.tile(np.repeat(["BYD CD","LYT"],rows//4),2)})
    for i in range(18):
        data[f"31A{chr(65+i)}"] = rng.normal(-.11,.055,rows)
    data.loc[33,[f"31A{chr(65+i)}" for i in range(7,12)]]=-.34
    fig=render_facet_chart(data,[c for c in data if c.startswith("31")],vendor_column="Vendor",facet_column="Family",usl=.08,lsl=-.32,target=-.1,sample_limit=50)
    fig.set_size_inches(11,5.4); fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig)


def add_picture(slide, path, x,y,w,h):
    slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(w), height=Inches(h))


def make_deck(output: Path, screenshot: Path | None = None):
    prs=Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5)
    blank=prs.slide_layouts[6]
    with tempfile.TemporaryDirectory(prefix="eya_guide_") as tmp:
        tmp=Path(tmp); ui=tmp/"ui.png"; chart=tmp/"chart.png"
        if screenshot and screenshot.exists():
            ui=screenshot
        else: mock_ui(ui)
        demo_chart(chart)
        # 1. Title
        s=prs.slides.add_slide(blank); s.background.fill.solid(); s.background.fill.fore_color.rgb=LIGHT
        band=s.shapes.add_shape(MSO_SHAPE.RECTANGLE,0,0,Inches(13.333),Inches(7.5)); band.fill.solid(); band.fill.fore_color.rgb=NAVY; band.line.fill.background()
        add_text(s,"ENGINEERING CHART ANALYZER",.8,1.0,11.8,.7,32,RGBColor(255,255,255),True)
        add_text(s,"A beginner-friendly step-by-step guide",.82,1.85,10,.5,22,RGBColor(200,220,245))
        add_text(s,"Map unit serial numbers to vendor data, build offset charts, inspect pass/fail commonality, and export a report.",.85,2.8,7.7,1.25,21,RGBColor(255,255,255))
        add_text(s,"Version 1.3 · Designed and developed by Hiro Nguyen",.85,6.65,11,.35,14,RGBColor(210,225,245))
        add_picture(s,ui,8.0,2.55,4.7,2.8); add_footer(s,1)
        # 2. What is needed
        s=prs.slides.add_slide(blank); add_header(s,"Before you start","01 / 09")
        add_bullets(s,["A measurement workbook (.xlsx or .xlsm): one row per unit, numeric measurement columns, and preferably an SN/Serial Number column.","A mapping workbook (optional): a serial/unit key plus Vendor, Build Matrix, Product, TrackPad Vendor, or other grouping metadata.","Keep both workbooks closed in Excel while importing and exporting.","If vendor information is already in the measurement workbook, a separate mapping workbook is optional."],.7,1.25,5.0,5.3,18)
        add_picture(s,ui,5.8,1.5,6.9,3.8); add_footer(s,2)
        # 3. Open app and load measurement data
        s=prs.slides.add_slide(blank); add_header(s,"Step 1 — Open the app and measurement workbook","02 / 09")
        add_bullets(s,["Launch Excel-Yield-Analyzer-v1.3.app (or run the Python app).","Click Open measurements… and choose the workbook file.","Select the worksheet containing unit rows and measurements.","Wait for the status bar to confirm the number of loaded rows."],.7,1.2,4.5,4.9,19)
        add_picture(s,ui,5.1,1.3,7.7,4.5); add_footer(s,3)
        # 4. Mapping
        s=prs.slides.add_slide(blank); add_header(s,"Step 2 — Map units to vendor metadata","03 / 09")
        add_bullets(s,["Click Open unit mapping… and select the mapping workbook and worksheet.","Check the two key dropdowns: unit key in measurement data and matching serial key in mapping data.","Enable Allow similar (fuzzy) unit-key matches only when serials may contain minor typos; the threshold controls match strictness.","Click Auto-map units before charting. Read the matched-row count and match rate in the status bar.","Mapping preserves measurement rows; duplicate mapping keys keep the first matching record."],.65,1.1,5.3,5.7,17)
        add_picture(s,ui,6.0,1.35,6.8,4.8); add_footer(s,4)
        # 5. Select category filters
        s=prs.slides.add_slide(blank); add_header(s,"Step 3 — Choose vendor and breakdown filters","04 / 09")
        add_bullets(s,["Choose the field used for vendor panels (for example Top Case Vendor).","Check only the vendor values to include. Uncheck (blank) to remove missing vendor records from the chart.","Optionally select a row breakdown such as TrackPad, Build Matrix, Product, or Station.","Check/uncheck breakdown values to include or exclude those panels."],.7,1.3,4.6,4.9,18)
        add_picture(s,ui,5.2,1.35,7.5,4.75); add_footer(s,5)
        # 6. Measurements and specs
        s=prs.slides.add_slide(blank); add_header(s,"Step 4 — Select measurements and specification limits","05 / 09")
        add_bullets(s,["Use Filter measurement columns… to find measurement points quickly.","Select one or more numeric measurement columns; multi-select is supported.","Choose a chart type. Multi-Line Trend Chart is the offset-style unit chart.","Enter USL, Target/Nominal, and LSL when specifications are known. Leave a field empty if it does not apply.","Use Max lines per panel to limit drawn lines for readability; statistical summaries use the filtered rows."],.7,1.2,5.1,5.4,17)
        add_picture(s,chart,5.9,1.55,6.8,4.0); add_footer(s,6)
        # 7. Build/read
        s=prs.slides.add_slide(blank); add_header(s,"Step 5 — Build and read the chart","06 / 09")
        add_bullets(s,["Click Build chart after changing selections.","Each column panel represents a selected vendor; each row represents a selected breakdown value.","Blue lines are passing units; red, thicker lines are units outside USL/LSL. Spec lines and the shaded spec band are repeated in each panel.","Use the chart toolbar to zoom, pan, reset, and save the current view.","Check the status bar: 100% and “Chart ready” means the current chart and summary are ready."],.65,1.15,5.2,5.6,17)
        add_picture(s,chart,5.9,1.45,6.9,4.4); add_footer(s,7)
        # 8. Summary
        s=prs.slides.add_slide(blank); add_header(s,"Step 6 — Understand the vendor Pass/Fail summary","07 / 09")
        add_bullets(s,["The table groups valid units by Vendor and selected breakdown field; blank vendor/breakdown groups are omitted.","Fail N and Pass N count units with at least one selected measurement failing/passing the entered limits.","Fail % of Total and Pass % of Total are shares of all included units in this summary.","Enter USL and/or LSL before building if you want meaningful Pass/Fail classification. Without limits, rows are treated as Pass.","Rows in the summary correspond to the chart’s selected vendor and breakdown values."],.7,1.2,5.2,5.2,17)
        add_picture(s,chart,5.95,1.55,6.75,4.2); add_footer(s,8)
        # 9. Export
        s=prs.slides.add_slide(blank); add_header(s,"Step 7 — Export the results","08 / 09")
        add_bullets(s,["Save PNG… exports only the current chart image.","Save PDF… creates a complete report with the chart, statistics, and vendor commonality table.","Export Excel… creates a workbook containing the chart, statistics, vendor summary, spec analysis, SPC metrics, and mapped unit data.","Confirm the export in the dialog, choose a destination and filename, then wait for the status bar to report completion.","Use Start over to clear the current session and begin with different workbooks."],.7,1.2,5.2,5.3,17)
        add_picture(s,ui,5.9,1.35,6.8,4.8); add_footer(s,9)
        # 10. Troubleshooting / end
        s=prs.slides.add_slide(blank); add_header(s,"If something does not look right","09 / 09")
        add_bullets(s,["No vendor panels? Confirm the mapping ran and the selected vendor field contains nonblank values.","No measurement columns? Select a worksheet with numeric measurement data, then clear the column search box.","All rows appear blank? Verify that the selected serial keys match; try enabling fuzzy matching cautiously and inspect the match rate.","Chart or export failed? Read the red ERROR message, correct the indicated selection, then click Build chart again. Start over resets the session.","Use real specification limits from your engineering process. Capability/SPC metrics are descriptive and should be reviewed by a qualified quality engineer."],.7,1.2,6.1,5.5,17)
        add_picture(s,chart,7.0,1.55,5.7,4.0)
        add_text(s,"You’re ready to analyze your own workbook.",.8,6.45,8,.35,19,GREEN,True); add_footer(s,10)
        prs.save(output)
    return output


def main():
    parser=argparse.ArgumentParser(description="Generate the English Engineering Chart Analyzer PowerPoint guide.")
    parser.add_argument("output", nargs="?", default="Engineering_Chart_Analyzer_User_Guide_v1.3.pptx")
    parser.add_argument("--screenshot", help="Optional screenshot of the real application window for visual reference.")
    args=parser.parse_args()
    output=make_deck(Path(args.output), Path(args.screenshot) if args.screenshot else None)
    print(f"PowerPoint guide created: {output.resolve()}")


if __name__ == "__main__":
    main()
