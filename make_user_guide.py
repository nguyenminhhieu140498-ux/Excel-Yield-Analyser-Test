"""Generate a beginner-friendly English PowerPoint user guide with visuals.

Usage:
  python make_user_guide.py [output.pptx] --screenshot PATH_OR_FOLDER

Numbered screenshots (1.png, 2.png, ...) are placed on the matching numbered
step slides. Additional screenshots are included in an appendix in numeric order.
Without screenshots, the guide uses generated illustrative mockups.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image as PILImage
from pptx import Presentation
from pptx.dml import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches, Pt

from engineering_charts import render_facet_chart

NAVY = RGBColor(25, 45, 75)
LIGHT = RGBColor(241, 245, 250)
DARK = RGBColor(35, 44, 58)
GREEN = RGBColor(34, 150, 100)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}


def add_text(slide, text, x, y, w, h, size=20, color=DARK, bold=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    box.text_frame.word_wrap = True
    p = box.text_frame.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    return box


def add_header(slide, title, step=None):
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(.72))
    band.fill.solid(); band.fill.fore_color.rgb = NAVY; band.line.fill.background()
    add_text(slide, title, .45, .12, 11.6, .48, 25, RGBColor(255, 255, 255), True)
    if step:
        add_text(slide, step, 11.9, .18, 1.0, .35, 14, RGBColor(210, 225, 245), True)


def add_footer(slide, number):
    add_text(slide, f"Engineering Chart Analyzer · v1.3 · Hiro Nguyen   |   {number}", .45, 7.18, 12.3, .2, 9, RGBColor(105, 115, 130))


def add_bullets(slide, items, x, y, w, h, size=19):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    box.text_frame.word_wrap = True
    for i, text in enumerate(items):
        p = box.text_frame.paragraphs[0] if i == 0 else box.text_frame.add_paragraph()
        p.text = "•  " + text
        p.font.size = Pt(size); p.font.color.rgb = DARK; p.space_after = Pt(11)
    return box


def mock_ui(path: Path):
    fig, ax = plt.subplots(figsize=(12, 5.4)); fig.patch.set_facecolor("#f4f6f9"); ax.set_facecolor("#f4f6f9")
    ax.set_xlim(0, 12); ax.set_ylim(0, 6); ax.axis("off")
    def panel(x, y, w, h, label):
        ax.add_patch(plt.Rectangle((x, y), w, h, facecolor="#fff", edgecolor="#c7d0dc"))
        ax.text(x+.15, y+h-.25, label, fontsize=9, fontweight="bold", va="top", color="#23344d")
    def button(x, y, w, label, color="#2878dc"):
        ax.add_patch(plt.Rectangle((x, y), w, .42, facecolor=color, edgecolor=color))
        ax.text(x+w/2, y+.21, label, ha="center", va="center", color="white", fontsize=8, fontweight="bold")
    panel(.15,.15,4,5.55,"SETUP"); button(.35,5.1,1.7,"Open measurements")
    button(2.2,5.1,1.7,"Open unit mapping","#62758c")
    panel(.35,4.25,3.55,.65,"Unit keys: SN → Serial Number")
    button(.55,3.62,3.1,"Auto-map units before charting","#21885e")
    panel(.35,2.7,3.55,.7,"Vendor / breakdown filters")
    panel(.35,1.58,3.55,.95,"Search & select measurement columns")
    panel(.35,.38,3.55,.9,"USL     Target     LSL")
    panel(4.4,2.55,7.4,3.15,"CHART PREVIEW")
    xx=np.linspace(0,1,26)
    for i in range(10): ax.plot(4.8+xx*6.6,2.9+(.45+.18*np.sin(xx*8+i*.3)+i*.018)*2.1,color="#58a0ec",alpha=.35,lw=1)
    ax.plot(4.8+xx*6.6,3.6+.7*np.sin(xx*8),color="#d8223f",lw=2)
    ax.axhline(4.65,xmin=.4,xmax=.93,color="#e74458",ls="--")
    panel(4.4,.4,7.4,1.75,"VENDOR PASS / FAIL SUMMARY")
    ax.text(4.7,1.62,"Vendor       Breakdown       Fail N       Pass N        % of total",fontsize=8,fontweight="bold")
    ax.text(4.7,1.18,"EVW           BYD CD              0              116            20.10%",fontsize=8)
    ax.text(4.7,.78,"FX              LYT                  1              248            42.98%",fontsize=8)
    fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig)


def demo_chart(path: Path):
    rng=np.random.default_rng(42); rows=72
    data=pd.DataFrame({"Vendor":np.repeat(["EVW","FX"],rows//2),"Family":np.tile(np.repeat(["BYD CD","LYT"],rows//4),2)})
    for i in range(18): data[f"31A{chr(65+i)}"]=rng.normal(-.11,.055,rows)
    data.loc[33,[f"31A{chr(65+i)}" for i in range(7,12)]]=-.34
    fig=render_facet_chart(data,[c for c in data if c.startswith("31")],vendor_column="Vendor",facet_column="Family",usl=.08,lsl=-.32,target=-.1,sample_limit=50)
    fig.set_size_inches(11,5.4); fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig)


def add_picture(slide, path, x, y, w, h):
    """Place image without distorting its aspect ratio."""
    with PILImage.open(path) as image:
        img_w, img_h = image.size
    scale = min(w / img_w, h / img_h)
    draw_w, draw_h = img_w * scale, img_h * scale
    slide.shapes.add_picture(str(path), Inches(x + (w-draw_w)/2), Inches(y + (h-draw_h)/2),
                             width=Inches(draw_w), height=Inches(draw_h))


def collect_screenshots(items: list[str] | None) -> list[Path]:
    found = []
    for item in items or []:
        path = Path(item).expanduser()
        if not path.exists(): raise FileNotFoundError(f"Screenshot path does not exist: {path}")
        candidates = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS) if path.is_dir() else [path]
        for candidate in candidates:
            if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
                raise ValueError(f"Unsupported image: {candidate}. Use PNG, JPG, JPEG, BMP, or GIF.")
            if candidate not in found: found.append(candidate)
    return sorted(found, key=_screenshot_sort_key)


def _screenshot_sort_key(path: Path):
    match = re.fullmatch(r"\s*(\d+)\s*", path.stem)
    return (0, int(match.group(1))) if match else (1, path.name.casefold())


def map_step_screenshots(screenshots: list[Path]) -> tuple[dict[int, Path], list[Path]]:
    """Map 1.png to Step 1, 2.png to Step 2, etc.; return unused images for appendix."""
    numbered = {}
    nonnumbered = []
    for path in screenshots:
        match = re.fullmatch(r"\s*(\d+)\s*", path.stem)
        if match:
            number = int(match.group(1))
            if number in numbered:
                raise ValueError(f"More than one screenshot is named for step {number}: {numbered[number].name}, {path.name}")
            numbered[number] = path
        else:
            nonnumbered.append(path)
    step_map = {}
    used = set()
    if numbered:
        step_map = numbered.copy()
        used.update(numbered.values())
    else:
        for number, path in enumerate(nonnumbered, start=1):
            step_map[number] = path
            used.add(path)
    return step_map, [p for p in screenshots if p not in used]


def add_screenshot_gallery(prs, blank, screenshots):
    for start in range(0, len(screenshots), 2):
        slide = prs.slides.add_slide(blank)
        add_header(slide, "Additional SOP screenshots", f"IMAGE {start+1:02d}")
        for offset, image_path in enumerate(screenshots[start:start+2]):
            x=.55+offset*6.4
            add_text(slide,image_path.name,x,.95,6.1,.35,13,NAVY,True)
            add_picture(slide,image_path,x,1.35,6.05,5.45)
        add_footer(slide,len(prs.slides))


def make_deck(output: Path, screenshots: list[Path] | None = None):
    screenshots = screenshots or []
    step_images, extra_images = map_step_screenshots(screenshots)
    prs=Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5); blank=prs.slide_layouts[6]
    with tempfile.TemporaryDirectory(prefix="eya_guide_") as tmp_name:
        tmp=Path(tmp_name); ui=tmp/"ui.png"; chart=tmp/"chart.png"
        mock_ui(ui); demo_chart(chart)
        s=prs.slides.add_slide(blank); s.background.fill.solid(); s.background.fill.fore_color.rgb=NAVY
        add_text(s,"ENGINEERING CHART ANALYZER",.8,1.0,11.8,.7,32,RGBColor(255,255,255),True)
        add_text(s,"A beginner-friendly step-by-step guide",.82,1.85,10,.5,22,RGBColor(200,220,245))
        add_text(s,"Map unit serial numbers to vendor data, build offset charts, inspect pass/fail commonality, and export a report.",.85,2.8,7.7,1.25,21,RGBColor(255,255,255))
        add_text(s,"Version 1.3 · Designed and developed by Hiro Nguyen",.85,6.65,11,.35,14,RGBColor(210,225,245))
        add_picture(s,ui,8,2.55,4.7,2.8); add_footer(s,1)

        s=prs.slides.add_slide(blank); add_header(s,"Before you start","01 / 09")
        add_bullets(s,["A measurement workbook (.xlsx or .xlsm): one row per unit, numeric measurement columns, and preferably an SN/Serial Number column.","A mapping workbook (optional): a serial/unit key plus Vendor, Build Matrix, Product, TrackPad Vendor, or other grouping metadata.","Keep both workbooks closed in Excel while importing and exporting.","If vendor information is already in the measurement workbook, a separate mapping workbook is optional."],.7,1.25,5,5.3,18)
        add_picture(s,ui,5.8,1.5,6.9,3.8); add_footer(s,2)

        steps = [
            ("Step 1 — Open the app and measurement workbook",["Launch Excel-Yield-Analyzer-v1.3.app (or run the Python app).","Click Open measurements… and choose the workbook file.","Select the worksheet containing unit rows and measurements.","Wait for the status bar to confirm the number of loaded rows."],chart),
            ("Step 2 — Map units to vendor metadata",["Click Open unit mapping… and select the mapping workbook and worksheet.","Check the unit key and matching serial key dropdowns.","Enable fuzzy matching only when serials may have minor typos; the threshold controls match strictness.","Click Auto-map units before charting and check the match count/status.","Duplicate mapping keys keep their first matching record."],ui),
            ("Step 3 — Choose vendor and breakdown filters",["Choose the field used for vendor panels (for example Top Case Vendor).","Check only vendor values to include; uncheck (blank) to exclude missing vendor records.","Optionally select a row breakdown such as TrackPad, Build Matrix, Product, or Station.","Check/uncheck breakdown values to show or hide those panels."],ui),
            ("Step 4 — Select measurements and specification limits",["Use the measurement-column filter to find measurement points.","Select one or more numeric measurement columns.","Choose a chart type; Multi-Line Trend Chart is the offset-style unit chart.","Enter USL, Target/Nominal, and LSL when known; otherwise leave a field blank.","Max lines per panel limits displayed lines for readability."],chart),
            ("Step 5 — Build and read the chart",["Click Build chart after changing selections.","Each column panel represents a vendor; each row is a selected breakdown value.","Blue lines are passing units; red thicker lines indicate units outside USL/LSL.","Use the toolbar to zoom, pan, reset, and save the view.","A 100% / Chart ready status means chart and summary are ready."],chart),
            ("Step 6 — Understand the vendor Pass/Fail summary",["The table groups valid units by Vendor and selected breakdown; blank groups are omitted.","Fail N and Pass N count units outside/inside the entered limits.","Percent columns show each status share of included units.","Enter USL and/or LSL for meaningful Pass/Fail classifications.","Summary categories follow the current chart filters."],ui),
            ("Step 7 — Export the results",["Save PNG… exports only the current chart image.","Save PDF… creates a report with chart, statistics, and vendor commonality.","Export Excel… includes chart, statistics, summary, and mapped unit data.","Confirm the export, choose a filename, and wait for completion status.","Start over clears the current session."],ui),
        ]
        for number,(title,bullets,fallback) in enumerate(steps,start=1):
            s=prs.slides.add_slide(blank); add_header(s,title,f"STEP {number:02d} / 07")
            add_bullets(s,bullets,.65,1.2,5.2,5.5,17)
            # Numbered SOP screenshots are deliberately used in place of illustrative images.
            add_picture(s,step_images.get(number,fallback),5.9,1.4,6.9,4.8)
            if number in step_images:
                add_text(s,f"Source: {step_images[number].name}",5.9,6.25,6.9,.25,10,RGBColor(105,115,130))
            add_footer(s,len(prs.slides))

        s=prs.slides.add_slide(blank); add_header(s,"If something does not look right","09 / 09")
        add_bullets(s,["No vendor panels? Confirm mapping ran and the selected vendor field has nonblank values.","No measurement columns? Select a worksheet with numeric measurements and clear the search box.","No matched units? Verify serial-key columns; use fuzzy matching cautiously and inspect the match rate.","Chart/export failed? Read the error, correct the selection, and build again. Start over resets the session.","Use specification limits from your engineering process; ask a quality engineer to review capability/SPC metrics."],.7,1.2,6.1,5.5,17)
        add_picture(s,chart,7,1.55,5.7,4); add_footer(s,len(prs.slides))

        if extra_images:
            add_screenshot_gallery(prs,blank,extra_images)
        output.parent.mkdir(parents=True,exist_ok=True); prs.save(output)
    return output


def main():
    parser=argparse.ArgumentParser(description="Generate the English Engineering Chart Analyzer PowerPoint guide.")
    parser.add_argument("output",nargs="?",default="Engineering_Chart_Analyzer_User_Guide_v1.3.pptx")
    parser.add_argument("--screenshot",action="append",default=[],metavar="PATH",
                        help="Screenshot file or directory; repeat to add multiple. Files named 1.png, 2.png, etc. map to matching steps.")
    args=parser.parse_args(); screenshots=collect_screenshots(args.screenshot)
    output=make_deck(Path(args.output),screenshots)
    print(f"PowerPoint guide created: {output.resolve()}")
    print(f"Step screenshots mapped: {sum(1 for p in screenshots if re.fullmatch(r'\\s*\\d+\\s*',p.stem))}; total screenshots found: {len(screenshots)}")


if __name__ == "__main__":
    main()
