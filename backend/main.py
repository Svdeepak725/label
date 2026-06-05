from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Template
from pydantic import BaseModel
from typing import Optional
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from urllib.parse import quote_plus
from datetime import datetime
import json
import uvicorn

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
# ensure a project-level downloads folder and expose it
DOWNLOADS_DIR = BASE_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="downloads")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Load preview template text from disk if present; otherwise fall back to an embedded template
def _load_preview_template_text() -> str:
    tpl_file = BASE_DIR / "templates" / "preview.html"
    if tpl_file.exists():
        return tpl_file.read_text(encoding="utf-8")
    # Embedded minimal preview template (keeps same variable names used in code)
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Label Preview - AI Wedding Bottle Label Generator</title>
    <link rel="stylesheet" href="/static/css/style.css" />
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
</head>
<body>
    <div class="page-shell preview-shell">
        <section class="preview-header">
            <div>
                <p class="eyebrow">Label Preview</p>
                <h1>Your wedding bottle label is ready</h1>
                <p class="hero-text">Download your print-ready PNG or PDF sized for a 500ml bottle (210×75 mm).</p>
            </div>
            <a href="/" class="secondary-button">Create Another Label</a>
        </section>

        <section class="preview-content">
            <div class="preview-panel">
                <div class="card white-card">
                    <div id="labelPreviewCard" class="label-preview-card">
                        <div class="label-image-wrap">
                            <img id="label-image-preview" src="{{ label_src }}" alt="Label preview" />
                        </div>
                    </div>

                    <div class="download-actions">
                            <button id="downloadPng" type="button" class="primary-button">Download PNG</button>
                            <button id="downloadPdf" type="button" class="secondary-button">Download PDF</button>
                    </div>
                </div>
            </div>

            <aside class="preview-details">
                <div class="detail-card">
                    <p class="detail-label">Groom</p>
                    <p>{{ data.groom }}</p>
                </div>
                <div class="detail-card">
                    <p class="detail-label">Bride</p>
                    <p>{{ data.bride }}</p>
                </div>
                <div class="detail-card">
                    <p class="detail-label">Wedding Date</p>
                    <p>{{ data.date }}</p>
                </div>
                <div class="detail-card">
                    <p class="detail-label">Religion</p>
                    <p>{{ data.religion }}</p>
                </div>
                <div class="detail-card">
                    <p class="detail-label">Theme</p>
                    <p>{{ data.theme }}</p>
                </div>
            </aside>
        </section>

        <div id="previewSuccess" class="toast-message success hidden">
            <p>Your design is ready. Use the buttons above to download the label.</p>
        </div>
    </div>

    <div id="loadingOverlay" class="loading-overlay hidden">
        <div class="loader"></div>
        <p>Preparing your download...</p>
    </div>

    <script type="application/json" id="preview-data">{{ preview_data_json | safe }}</script>
    <script>
        window.previewData = JSON.parse(document.getElementById('preview-data').textContent);
    </script>
    <script src="/static/js/script.js"></script>
</body>
</html>'''

PREVIEW_TEMPLATE_TEXT = _load_preview_template_text()

RELIGIONS = ["Christian", "Hindu", "Muslim"]
THEMES = ["Minimalist", "Modern", "Royal", "Traditional"]

# Preferred font families / filenames per theme (attempts several fallbacks)
THEME_FONTS = {
    "Royal": {
        "title": ["Cinzel-Bold.ttf", "CinzelDecorative.ttf", "CinzelDecorative-Regular.ttf", "Cinzel.ttf", "Playfair Display", "cambriab.ttf"],
        "weds": ["CinzelDecorative.ttf", "Playfair Display", "cambria.ttc"],
        "date": ["CinzelDecorative.ttf", "Times New Roman", "times.ttf"],
        "quote": ["Playfair Display", "Gabriola.ttf", "timesi.ttf"],
        "mono": ["CinzelDecorative.ttf", "georgia.ttf"],
    },
    "Traditional": {
        "title": ["PlayfairDisplay-Bold.ttf", "PlayfairDisplay-Regular.ttf", "Playfair Display", "Cambria", "cambria.ttc"],
        "weds": ["Playfair Display", "cambria.ttc", "georgia.ttf"],
        "date": ["Playfair Display", "georgia.ttf", "times.ttf"],
        "quote": ["Playfair Display", "Gabriola.ttf"],
        "mono": ["Playfair Display", "georgia.ttf"],
    },
    "Modern": {
        "title": ["Montserrat-Bold.ttf", "Montserrat.ttf", "Montserrat", "Inter", "Segoe UI"],
        "weds": ["Montserrat.ttf", "Inter", "georgia.ttf", "CormorantGaramond-Regular.ttf"],
        "date": ["Montserrat-Regular.ttf", "Inter"],
        "quote": ["Montserrat-Italic.ttf", "Inter Italic", "GreatVibes-Regular.ttf"],
        "mono": ["Montserrat.ttf", "Inter"],
    },
    "Minimalist": {
        "title": ["Poppins-Bold.ttf", "Poppins.ttf", "Poppins", "Inter", "Segoe UI"],
        "weds": ["Poppins.ttf", "Inter", "CormorantGaramond-Regular.ttf"],
        "date": ["Poppins-Regular.ttf", "Inter", "Montserrat-Regular.ttf"],
        "quote": ["GreatVibes-Regular.ttf", "Poppins-Italic.ttf", "Inter Italic"],
        "mono": ["Poppins.ttf", "Inter"],
    },
}


class LabelRequest(BaseModel):
    groom: str
    bride: str
    date: str
    religion: str
    theme: str


def get_theme_colors(theme: str) -> dict:
    # Minimal theme color mapping; can be expanded
    return {
        "background": "#F7F1E6",
        "border": "#C0A070",
        "accent": "#D4AF37",
        "text": "#3b2f2f",
    }


def get_event_text(religion: str) -> str:
    return "Wedding Celebration"


def dumps_safe_json(payload: dict) -> str:
    return json.dumps(payload).replace("</", "<\\/")


def validate_label_data(data: LabelRequest) -> Optional[dict]:
    errors = {}
    if not data.groom:
        errors["groom"] = "Required"
    if not data.bride:
        errors["bride"] = "Required"
    if not data.date:
        errors["date"] = "Required"
    if errors:
        return errors
    return None


# Template color and font configurations for 20-litre wedding labels
# text_area: x, y = top-left corner as fraction of image; width, height = size as fraction of image
# These coordinates are calibrated per-template to the visible blank/frame area in each design.
#
# Image layout reference (all templates are wide landscape ~1500×600px):
#   Left panel  : 0.00 – 0.23  (product info / label data)
#   Center area : 0.23 – 0.75  (decorative zone with blank text space inside frame)
#   Right panel : 0.75 – 1.00  (couple photo + Good Feel logo)
#
# For each template the blank writable region inside its decorative frame is:
#   Christian Minimalist  – thin oval arch; blank center strip x≈0.27–0.61, y≈0.20–0.72
#   Christian Modern      – diamond/geometric frame; blank strip x≈0.27–0.61, y≈0.22–0.72
#   Christian Royal       – ornate gold border; blank strip x≈0.27–0.60, y≈0.18–0.72
#   Christian Traditional – arch frame with florals; blank strip x≈0.27–0.62, y≈0.18–0.72
#   Muslim Minimalist     – plain arch; blank strip x≈0.27–0.62, y≈0.18–0.75
#   Muslim Modern         – arch + lanterns; blank strip x≈0.27–0.62, y≈0.22–0.78
#   Muslim Royal          – navy/gold medallion; blank inside medallion x≈0.29–0.57, y≈0.18–0.82
#   Muslim Traditional    – green/gold scallop frame; blank inside x≈0.28–0.60, y≈0.15–0.82
#   Hindu Minimalist      – subtle rounded rectangle frame; x≈0.27–0.65, y≈0.22–0.75
#   Hindu Modern          – modern pendant frame; x≈0.27–0.65, y≈0.22–0.72
#   Hindu Royal           – elaborate gold mandala frame; x≈0.27–0.60, y≈0.20–0.80
#   Hindu Traditional     – rich temple arch frame; x≈0.27–0.60, y≈0.18–0.82

WEDDING_TEMPLATES = {
    # ── CHRISTIAN ──────────────────────────────────────────────────────────────
    "Christian_Minimalist": {
        # Simple arch; "Two Hearts, One Journey" text already at bottom of arch.
        # Blank writable zone: centre of arch, clear of the couple photo.
        "text_area": {"x": 0.380, "y": 0.325, "width": 0.260, "height": 0.305},
        "smart_text_area": False,
        "name_size_factor": 0.30,
        "max_name_size": 64,
        "line_gap_fraction": 0.065,
        "groom_font": "Marcellus",
        "bride_font": "Marcellus",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (180, 140, 60),
        "text_align": "center",
    },
    "Christian_Modern": {
        # Geometric/diamond border; large open centre.
        "text_area": {"x": 0.275, "y": 0.22, "width": 0.330, "height": 0.50},
        "groom_font": "Playfair Display",
        "bride_font": "Playfair Display",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (180, 140, 60),
        "text_align": "center",
    },
    "Christian_Royal": {
        # Ornate gold scrollwork border; cross at top, large blank centre.
        "text_area": {"x": 0.315, "y": 0.325, "width": 0.315, "height": 0.305},
        "smart_text_area": False,
        "name_size_factor": 0.30,
        "max_name_size": 64,
        "line_gap_fraction": 0.065,
        "groom_font": "Cinzel Decorative Bold",
        "bride_font": "Cinzel Decorative Bold",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (190, 148, 60),
        "text_align": "center",
    },
    "Christian_Traditional": {
        # Arch with gold florals; cross at top, "Two Hearts…" at bottom.
        # Write names in the open space between cross and quote.
        "text_area": {"x": 0.270, "y": 0.22, "width": 0.340, "height": 0.50},
        "groom_font": "Marcellus",
        "bride_font": "Marcellus",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (180, 140, 60),
        "text_align": "center",
    },

    # ── MUSLIM ─────────────────────────────────────────────────────────────────
    "Muslim_Minimalist": {
        # Clean white arch, mosque silhouette at bottom, leaves at top-right.
        "text_area": {"x": 0.275, "y": 0.20, "width": 0.330, "height": 0.55},
        "smart_scan_area": {"x": 0.330, "y": 0.24, "width": 0.300, "height": 0.48},
        "smart_min_luma": 185,
        "smart_max_chroma": 55,
        "groom_font": "Marcellus",
        "bride_font": "Marcellus",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (180, 148, 80),
        "text_align": "center",
    },
    "Muslim_Modern": {
        # Arch with hanging lanterns, "PURE WATER | PURE LOVE" inside arch.
        # Names go in the large blank area below the crescent.
        "text_area": {"x": 0.278, "y": 0.25, "width": 0.325, "height": 0.50},
        "groom_font": "Playfair Display",
        "bride_font": "Playfair Display",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (155, 120, 50),
        "text_align": "center",
    },
    "Muslim_Royal": {
        # Navy & gold; large ornate medallion in centre; couple on right.
        # Blank writable space is inside the medallion frame.
        "text_area": {"x": 0.325, "y": 0.31, "width": 0.330, "height": 0.40},
        "padding_fraction": 0.014,
        "name_size_factor": 0.24,
        "max_name_size": 60,
        "groom_font": "Cinzel Decorative Bold",
        "bride_font": "Cinzel Decorative Bold",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (200, 168, 107),
        "text_align": "center",
    },
    "Muslim_Traditional": {
        # Green & gold scalloped medallion; couple on right.
        "text_area": {"x": 0.290, "y": 0.18, "width": 0.285, "height": 0.62},
        "groom_font": "Cinzel Decorative Bold",
        "bride_font": "Cinzel Decorative Bold",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (195, 155, 55),
        "text_align": "center",
    },

    # ── HINDU ──────────────────────────────────────────────────────────────────
    "Hindu_Minimalist": {
        # Ivory background; Om symbol top-centre; subtle gold rounded-rect frame.
        "text_area": {"x": 0.315, "y": 0.275, "width": 0.340, "height": 0.430},
        "smart_text_area": False,
        "name_size_factor": 0.23,
        "max_name_size": 64,
        "groom_font": "Marcellus",
        "bride_font": "Marcellus",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (190, 150, 55),
        "text_align": "center",
    },
    "Hindu_Modern": {
        # Peach/cream; Om in circle top; modern pendant decorations right.
        # Large rectangular gold frame in centre; names go inside it.
        "text_area": {"x": 0.278, "y": 0.25, "width": 0.360, "height": 0.46},
        "groom_font": "Playfair Display",
        "bride_font": "Playfair Display",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (190, 148, 50),
        "text_align": "center",
    },
    "Hindu_Royal": {
        # Vivid temple scene; Om at top; elaborate gold ornate frame.
        # Frame interior is the writable area.
        "text_area": {"x": 0.280, "y": 0.22, "width": 0.300, "height": 0.55},
        "groom_font": "Cinzel Decorative Bold",
        "bride_font": "Cinzel Decorative Bold",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (180, 30, 30),
        "text_align": "center",
    },
    "Hindu_Traditional": {
        # Rich cream/gold; temple arch, marigold garlands top, diya bottom-left.
        # Large ornate Mughal-arch frame in centre.
        "text_area": {"x": 0.278, "y": 0.20, "width": 0.310, "height": 0.58},
        "groom_font": "Cinzel Decorative Bold",
        "bride_font": "Cinzel Decorative Bold",
        "weds_font": "Cormorant Garamond SemiBold",
        "date_font": "Montserrat Medium",
        "text_color": (180, 30, 30),
        "text_align": "center",
    },
}

FONT_FAMILY_MAP = {
    "Cinzel Decorative Bold": ["CinzelDecorative-Bold.ttf", "CinzelDecorative.ttf", "Cinzel-Bold.ttf", "CinzelDecorative-Regular.ttf", "Cinzel.ttf", "arialbd.ttf"],
    "Cormorant Garamond Bold": ["CormorantGaramond-Bold.ttf", "Cormorant Garamond Bold.ttf", "CormorantGaramond-SemiBold.ttf", "cambriab.ttf", "georgiab.ttf"],
    "Cormorant Garamond SemiBold": ["CormorantGaramond-SemiBold.ttf", "CormorantGaramond-Bold.ttf", "CormorantGaramond.ttf", "cambriab.ttf", "georgia.ttf"],
    "Cormorant Garamond Medium": ["CormorantGaramond-Medium.ttf", "Cormorant Garamond Medium.ttf", "CormorantGaramond-Regular.ttf", "cambria.ttc", "georgia.ttf"],
    "Cormorant Garamond": ["CormorantGaramond-Regular.ttf", "Cormorant Garamond.ttf", "cambria.ttc", "georgia.ttf"],
    "Montserrat Medium": ["Montserrat-Medium.ttf", "Montserrat-SemiBold.ttf", "Montserrat-Bold.ttf", "Montserrat.ttf", "arialbd.ttf"],
    "Poppins Bold": ["Poppins-Bold.ttf", "Montserrat-Bold.ttf", "arialbd.ttf"],
    "Poppins Medium": ["Poppins-Medium.ttf", "Montserrat-Medium.ttf", "Poppins-Regular.ttf", "Poppins-SemiBold.ttf", "arial.ttf"],
    "Poppins SemiBold": ["Poppins-SemiBold.ttf", "Poppins-Medium.ttf", "Poppins-Bold.ttf", "Montserrat-SemiBold.ttf", "arialbd.ttf"],
    "Poppins Regular": ["Poppins-Regular.ttf", "Montserrat-Regular.ttf", "arial.ttf"],
    "Cinzel Decorative": ["CinzelDecorative.ttf", "Cinzel-Bold.ttf", "CinzelDecorative-Regular.ttf", "Cinzel.ttf", "arialbd.ttf", "arial.ttf"],
    "Marcellus": ["Marcellus-Regular.ttf", "Marcellus.ttf", "arial.ttf", "times.ttf", "georgia.ttf"],
    "Playfair Display": ["PlayfairDisplay-Bold.ttf", "PlayfairDisplay-Regular.ttf", "Playfair Display", "times.ttf", "georgia.ttf"],
    "Forum": ["Forum.ttf", "arial.ttf", "arialbd.ttf", "georgia.ttf"],
}


def load_font(font_family: str, size: int) -> ImageFont.FreeTypeFont:
    windows_fonts = Path("C:/Windows/Fonts")
    project_fonts = BASE_DIR / "static" / "fonts"
    candidates = FONT_FAMILY_MAP.get(font_family, [font_family])

    for font_name in candidates:
        # Try project fonts first
        project_font = project_fonts / font_name
        if project_font.exists():
            try:
                return ImageFont.truetype(str(project_font), size)
            except Exception:
                pass

        # Try system fonts directory
        system_font = windows_fonts / font_name
        if system_font.exists():
            try:
                return ImageFont.truetype(str(system_font), size)
            except Exception:
                pass

        # Try loading by font name
        try:
            return ImageFont.truetype(font_name, size)
        except Exception:
            pass

    # Last resort
    try:
        return ImageFont.truetype(str(windows_fonts / "arial.ttf"), size)
    except Exception:
        return ImageFont.load_default()  # type: ignore


def _fraction_box_to_pixels(box: dict, img_width: int, img_height: int) -> tuple[int, int, int, int]:
    x = int(img_width * box["x"])
    y = int(img_height * box["y"])
    width = int(img_width * box["width"])
    height = int(img_height * box["height"])
    return x, y, width, height


def find_smart_text_area(
    img: Image.Image,
    template_config: dict,
    fallback_cfg: dict,
) -> tuple[int, int, int, int]:
    img_width, img_height = img.size
    fallback_x, fallback_y, fallback_width, fallback_height = _fraction_box_to_pixels(
        fallback_cfg, img_width, img_height
    )

    scan_cfg = template_config.get("smart_scan_area")
    if scan_cfg is None:
        scan_cfg = {
            "x": max(0.23, fallback_cfg["x"] - 0.07),
            "y": max(0.10, fallback_cfg["y"] - 0.08),
            "width": min(0.46, fallback_cfg["width"] + 0.14),
            "height": min(0.74, fallback_cfg["height"] + 0.16),
        }

    scan_x, scan_y, scan_width, scan_height = _fraction_box_to_pixels(
        scan_cfg, img_width, img_height
    )
    scan_x = max(0, min(scan_x, img_width - 1))
    scan_y = max(0, min(scan_y, img_height - 1))
    scan_width = max(1, min(scan_width, img_width - scan_x))
    scan_height = max(1, min(scan_height, img_height - scan_y))

    cell_size = int(template_config.get("smart_cell_size", max(5, img_width // 220)))
    cols = max(1, scan_width // cell_size)
    rows = max(1, scan_height // cell_size)
    min_luma = int(template_config.get("smart_min_luma", 168))
    max_chroma = int(template_config.get("smart_max_chroma", 82))

    pixels = img.convert("RGB").load()
    clean: list[list[bool]] = []
    for row in range(rows):
        clean_row = []
        py = min(img_height - 1, scan_y + row * cell_size + cell_size // 2)
        for col in range(cols):
            px = min(img_width - 1, scan_x + col * cell_size + cell_size // 2)
            r, g, b = pixels[px, py]
            luma = (299 * r + 587 * g + 114 * b) // 1000
            chroma = max(r, g, b) - min(r, g, b)
            clean_row.append(luma >= min_luma and chroma <= max_chroma)
        clean.append(clean_row)

    obstacle_padding = int(template_config.get("smart_obstacle_padding_cells", 1))
    if obstacle_padding > 0:
        padded = [row[:] for row in clean]
        for row in range(rows):
            for col in range(cols):
                if clean[row][col]:
                    continue
                for dy in range(-obstacle_padding, obstacle_padding + 1):
                    for dx in range(-obstacle_padding, obstacle_padding + 1):
                        ny, nx = row + dy, col + dx
                        if 0 <= ny < rows and 0 <= nx < cols:
                            padded[ny][nx] = False
        clean = padded

    min_width_px = int(template_config.get("smart_min_width_fraction", 0.16) * img_width)
    min_height_px = int(template_config.get("smart_min_height_fraction", 0.18) * img_height)
    fallback_center_x = fallback_x + fallback_width / 2
    fallback_center_y = fallback_y + fallback_height / 2
    max_center_dx = template_config.get("smart_max_center_dx_fraction", 0.16) * img_width
    max_center_dy = template_config.get("smart_max_center_dy_fraction", 0.22) * img_height

    best: tuple[float, int, int, int, int] | None = None
    heights = [0] * cols
    for row in range(rows):
        for col in range(cols):
            heights[col] = heights[col] + 1 if clean[row][col] else 0

        stack: list[int] = []
        for col in range(cols + 1):
            current_height = heights[col] if col < cols else 0
            while stack and current_height < heights[stack[-1]]:
                top = stack.pop()
                height_cells = heights[top]
                left = stack[-1] + 1 if stack else 0
                width_cells = col - left
                rect_width = width_cells * cell_size
                rect_height = height_cells * cell_size
                if rect_width < min_width_px or rect_height < min_height_px:
                    continue

                rect_x = scan_x + left * cell_size
                rect_y = scan_y + (row - height_cells + 1) * cell_size
                center_x = rect_x + rect_width / 2
                center_y = rect_y + rect_height / 2
                dx = abs(center_x - fallback_center_x)
                dy = abs(center_y - fallback_center_y)
                if dx > max_center_dx or dy > max_center_dy:
                    continue

                area = rect_width * rect_height
                center_penalty = ((dx / max_center_dx) ** 2 + (dy / max_center_dy) ** 2) * area * 0.18
                score = area - center_penalty
                if best is None or score > best[0]:
                    best = (score, rect_x, rect_y, rect_width, rect_height)
            stack.append(col)

    if best is None:
        return fallback_x, fallback_y, fallback_width, fallback_height

    _, area_x, area_y, area_width, area_height = best
    inner_pad = int(template_config.get("smart_inner_padding_fraction", 0.01) * img_width)
    area_x += inner_pad
    area_y += inner_pad
    area_width = max(10, area_width - inner_pad * 2)
    area_height = max(10, area_height - inner_pad * 2)
    return area_x, area_y, area_width, area_height


def format_label_date(date_text: str) -> str:
    value = date_text.strip()
    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d-%m-%y", "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d.%m.%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, date_format).strftime("%d.%m.%Y")
        except ValueError:
            pass
    return value


def generate_20litre_wedding_label(groom_name: str, bride_name: str, wedding_date: str, 
                                    religion: str, theme: str) -> BytesIO:
    """
    Generate label with smart text layout system that respects safe areas
    and automatically resizes text to prevent overlaps.
    """
    religion_name = religion.strip().title()
    theme_name = theme.strip().title()
    template_path = BASE_DIR / "static" / "images" / religion_name / f"{theme_name.lower()}.png"
    if not template_path.exists() and religion_name == "Muslim" and theme_name == "Traditional":
        template_path = BASE_DIR / "static" / "images" / religion_name / "traditonal.png"
    if not template_path.exists():
        raise ValueError(f"Template not found: {template_path}")

    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    template_key = f"{religion_name}_{theme_name}"
    template_config = WEDDING_TEMPLATES.get(template_key, WEDDING_TEMPLATES.get("Hindu_Royal"))
    if template_config is None:
        template_config = WEDDING_TEMPLATES["Hindu_Royal"]

    # Get text area configuration
    img_width, img_height = img.size
    text_area_cfg = template_config.get("text_area", {"x": 0.27, "y": 0.22, "width": 0.32, "height": 0.52})
    
    # Convert proportional coordinates to pixels. Smart mode scans the template
    # image and tightens the box around the largest quiet writable area.
    # Add a small internal padding so text never kisses the frame border
    padding = int(img_width * template_config.get("padding_fraction", 0.012))
    if template_config.get("smart_text_area", True):
        area_x, area_y, area_width, area_height = find_smart_text_area(
            img, template_config, text_area_cfg
        )
    else:
        area_x, area_y, area_width, area_height = _fraction_box_to_pixels(
            text_area_cfg, img_width, img_height
        )

    content_x       = area_x + padding
    content_width   = max(10, area_width - padding * 2)
    content_center_x = content_x + content_width // 2
    text_align = template_config.get("text_align", "center")

    # Prepare text for the printable label.
    groom_text = groom_name.strip().upper() or "GROOM"
    bride_text = bride_name.strip().upper() or "BRIDE"
    date_text  = format_label_date(wedding_date or "2026-06-01")
    wed_text   = "WEDS"

    # Luxury typography uses Cormorant Garamond with religion-aware premium colors.
    groom_font_name = "Cormorant Garamond Bold"
    bride_font_name = "Cormorant Garamond Bold"
    weds_font_name  = "Cormorant Garamond SemiBold"
    # Keep the existing date font family per current label styling.
    date_font_name  = "Poppins Medium"
    letter_spacing = 1
    shadow_offset = (1, 1)

    def clamp_channel(value: float) -> int:
        return max(0, min(255, int(round(value))))

    def blend_color(color_a: tuple[int, int, int], color_b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
        return tuple(
            clamp_channel(color_a[i] * (1 - amount) + color_b[i] * amount)
            for i in range(3)
        )

    def darken_color(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
        return tuple(clamp_channel(channel * (1 - amount)) for channel in color)

    def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        value = hex_color.strip().lstrip("#")
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

    religion_name_colors = {
        "Christian": {
            "fill": hex_to_rgb("#B8860B"),
            "shadow": (0, 0, 0),
            "shadow_alpha": 28,
            "glow": hex_to_rgb("#C9A227"),
            "glow_alpha": 82,
        },
        "Muslim": {
            "fill": hex_to_rgb("#0F5E4F"),
            "shadow": hex_to_rgb("#C9A227"),
            "shadow_alpha": 58,
            "glow": hex_to_rgb("#C9A227"),
            "glow_alpha": 76,
        },
        "Hindu": {
            "fill": hex_to_rgb("#7A1F1F"),
            "shadow": hex_to_rgb("#B8860B"),
            "shadow_alpha": 64,
            "glow": hex_to_rgb("#B8860B"),
            "glow_alpha": 72,
        },
    }
    name_style = religion_name_colors.get(religion_name, religion_name_colors["Christian"])

    name_color = name_style["fill"]
    name_shadow_fill = (*name_style["shadow"], name_style["shadow_alpha"])
    name_glow_fill = (*name_style["glow"], name_style["glow_alpha"])
    neutral_shadow_fill = (0, 0, 0, 20)
    weds_color = hex_to_rgb("#5E5A54")
    date_color = hex_to_rgb("#4A4A4A")

    def text_bbox(text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int, int, int]:
        return draw.textbbox((0, 0), text, font=font)

    def measure(text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
        bbox = text_bbox(text, font)
        width = bbox[2] - bbox[0]
        if len(text) > 1:
            width += letter_spacing * (len(text) - 1)
        return width, bbox[3] - bbox[1]

    def break_long_word(word: str, max_width: int, font: ImageFont.FreeTypeFont) -> list[str]:
        if not word:
            return [""]
        parts = []
        current = ""
        for ch in word:
            if measure(current + ch, font)[0] <= max_width:
                current += ch
            else:
                if current:
                    parts.append(current)
                current = ch
        if current:
            parts.append(current)
        return parts or [word]

    def wrap_text(text: str, max_width: int, font: ImageFont.FreeTypeFont) -> list[str]:
        words = text.split()
        lines = []
        current_line: list[str] = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            if measure(test_line, font)[0] <= max_width:
                current_line.append(word)
                continue

            if current_line:
                lines.append(' '.join(current_line))
                current_line = []

            if measure(word, font)[0] <= max_width:
                current_line = [word]
            else:
                for part in break_long_word(word, max_width, font):
                    lines.append(part)

        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else [text]

    def block_height(lines: list[str], font: ImageFont.FreeTypeFont) -> int:
        return sum(measure(line, font)[1] for line in lines) + (len(lines) - 1) * 3

    def fit_text_block(text: str, font_family: str, max_size: int, min_size: int,
                       max_width: int, max_lines: int = 2, max_height: int | None = None) -> tuple[list[str], ImageFont.FreeTypeFont]:
        for size in range(max_size, min_size - 1, -1):
            font = load_font(font_family, size)
            lines = wrap_text(text, max_width, font)
            if len(lines) > max_lines:
                continue
            if max_height is not None and block_height(lines, font) > max_height:
                continue
            return lines, font
        font = load_font(font_family, min_size)
        lines = wrap_text(text, max_width, font)
        return lines, font

    def name_line_limit(text: str) -> int:
        return 1 if " " not in text and len(text) <= 12 else 2

    # ── Choose font sizes relative to the writable area height ─────────────────
    name_size_factor = float(template_config.get("name_size_factor", 0.28))
    name_max_cap = int(template_config.get("max_name_size", 88))
    name_min_size = int(template_config.get("min_name_size", 16))
    name_max_size  = max(20, min(name_max_cap, int(area_height * name_size_factor * 1.12)))
    weds_max_size  = max(16, min(46, int(area_height * 0.17)))
    weds_min_size  = 12
    date_max_size  = max(18, min(44, int(area_height * 0.17)))
    date_min_size  = 14

    def choose_best_layout() -> tuple[list[str], ImageFont.FreeTypeFont, list[str], ImageFont.FreeTypeFont, list[str], ImageFont.FreeTypeFont, list[str], ImageFont.FreeTypeFont, int]:
        for groom_size in range(name_max_size, name_min_size - 1, -1):
            groom_lines, groom_font = fit_text_block(
                groom_text, groom_font_name, groom_size, name_min_size,
                content_width, max_lines=name_line_limit(groom_text),
            )
            bride_lines, bride_font = fit_text_block(
                bride_text, bride_font_name, groom_size, name_min_size,
                content_width, max_lines=name_line_limit(bride_text),
            )
            weds_lines, weds_font = fit_text_block(
                wed_text, weds_font_name, min(weds_max_size, groom_size - 8), weds_min_size,
                content_width, max_lines=2,
            )
            date_lines, date_font = fit_text_block(
                date_text, date_font_name, min(date_max_size, groom_size - 8), date_min_size,
                content_width, max_lines=2,
            )

            groom_h = block_height(groom_lines, groom_font)
            bride_h = block_height(bride_lines, bride_font)
            weds_h = block_height(weds_lines, weds_font)
            date_h = block_height(date_lines, date_font)
            gap = max(8, int(area_height * float(template_config.get("line_gap_fraction", 0.09))))
            total_h = groom_h + weds_h + bride_h + date_h + gap * 3
            if total_h <= area_height:
                return groom_lines, groom_font, bride_lines, bride_font, weds_lines, weds_font, date_lines, date_font, gap

        # fallback to smaller all-minimum sizes and allow more wrapping for names
        groom_lines, groom_font = fit_text_block(groom_text, groom_font_name, name_min_size, name_min_size, content_width, max_lines=4)
        bride_lines, bride_font = fit_text_block(bride_text, bride_font_name, name_min_size, name_min_size, content_width, max_lines=4)
        weds_lines, weds_font = fit_text_block(wed_text, weds_font_name, weds_min_size, weds_min_size, content_width, max_lines=2)
        date_lines, date_font = fit_text_block(date_text, date_font_name, date_min_size, date_min_size, content_width, max_lines=2)
        total_h = block_height(groom_lines, groom_font) + block_height(bride_lines, bride_font) + block_height(weds_lines, weds_font) + block_height(date_lines, date_font)
        gap = max(5, int((area_height - total_h) / 4))
        return groom_lines, groom_font, bride_lines, bride_font, weds_lines, weds_font, date_lines, date_font, gap

    groom_lines, groom_font, bride_lines, bride_font, weds_lines, weds_font, date_lines, date_font, ideal_gap = choose_best_layout()

    groom_h = block_height(groom_lines, groom_font)
    bride_h = block_height(bride_lines, bride_font)
    weds_h = block_height(weds_lines, weds_font)
    date_h = block_height(date_lines, date_font)
    total_h = groom_h + weds_h + bride_h + date_h + ideal_gap * 3
    start_y = area_y + max(0, (area_height - total_h) // 2)

    def draw_spaced_text(
        position: tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: tuple[int, int, int],
        text_shadow_fill: tuple[int, int, int, int],
        glow: bool = False,
        glow_fill: tuple[int, int, int, int] | None = None,
    ) -> None:
        nonlocal draw
        x, y = position
        line_bbox = text_bbox(text, font)
        text_y = y - line_bbox[1]
        if glow:
            glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_layer)
            glow_rgba = glow_fill or (*blend_color(fill, (255, 224, 132), 0.45), 80)
            glow_x = x
            for char in text:
                bbox = text_bbox(char, font)
                char_x = glow_x - bbox[0]
                glow_draw.text((char_x, text_y), char, font=font, fill=glow_rgba)
                glow_x += (bbox[2] - bbox[0]) + letter_spacing
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=max(2, font.size // 10)))
            img.alpha_composite(glow_layer)
            draw = ImageDraw.Draw(img)

        x, y = position
        for char in text:
            bbox = text_bbox(char, font)
            char_x = x - bbox[0]
            draw.text((char_x + shadow_offset[0], text_y + shadow_offset[1]), char, font=font, fill=text_shadow_fill)
            draw.text((char_x, text_y), char, font=font, fill=fill)
            x += (bbox[2] - bbox[0]) + letter_spacing

    def draw_block(
        lines: list[str],
        font: ImageFont.FreeTypeFont,
        y: int,
        fill: tuple[int, int, int],
        text_shadow_fill: tuple[int, int, int, int],
        glow: bool = False,
        glow_fill: tuple[int, int, int, int] | None = None,
    ) -> int:
        for line in lines:
            bbox = text_bbox(line, font)
            lw, lh = measure(line, font)
            painted_x = content_center_x - lw // 2 if text_align == "center" else content_x
            painted_x = max(content_x, min(painted_x, content_x + content_width - lw))
            draw_spaced_text((painted_x, y), line, font, fill, text_shadow_fill, glow=glow, glow_fill=glow_fill)
            y += lh + 3
        return y

    y = start_y
    y = draw_block(groom_lines, groom_font, y, name_color, name_shadow_fill, glow=True, glow_fill=name_glow_fill)
    y += ideal_gap
    y = draw_block(weds_lines, weds_font, y, weds_color, neutral_shadow_fill)
    y += ideal_gap
    y = draw_block(bride_lines, bride_font, y, name_color, name_shadow_fill, glow=True, glow_fill=name_glow_fill)
    y += ideal_gap
    draw_block(date_lines, date_font, y, date_color, neutral_shadow_fill)

    output = BytesIO()
    img.save(output, "PNG", quality=95)
    output.seek(0)
    return output


@app.on_event("startup")
async def startup_event():
    """App startup - templates already exist in static/images/wedding/"""
    pass


def create_pdf(data: LabelRequest) -> BytesIO:
    image_stream = generate_20litre_wedding_label(data.groom, data.bride, data.date, data.religion, data.theme)
    pdf_buffer = BytesIO()
    # Embed PNG into a PDF page sized proportionally (we'll use 1200x600 px => map to A4 landscape scaled)
    page_w = 595
    page_h = 842
    c = canvas.Canvas(pdf_buffer, pagesize=(page_w, page_h))
    # Place image centered
    img = Image.open(image_stream)
    img_w, img_h = img.size
    # scale to page width with margins
    target_w = page_w - 72
    scale = target_w / img_w
    target_h = img_h * scale
    x = 36
    y = (page_h - target_h) / 2
    c.drawImage(ImageReader(img), x, y, width=target_w, height=target_h)
    c.showPage()
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer


@app.get("/label.png")
async def get_label(groom: str = "Groom", bride: str = "Bride", date: str = "2026-06-01", religion: str = "Hindu", theme: str = "Traditional"):
    """Return the ready-made template PNG for the selected label."""
    try:
        png_stream = generate_20litre_wedding_label(groom, bride, date, religion, theme)
        return StreamingResponse(png_stream, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/label.png")
async def post_label(data: LabelRequest):
    """Return the ready-made template PNG for the selected label (POST variant)."""
    try:
        png_stream = generate_20litre_wedding_label(data.groom, data.bride, data.date, data.religion, data.theme)
        return StreamingResponse(png_stream, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    index_file = BASE_DIR / "templates" / "index.html"
    if index_file.exists():
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>AI Wedding Bottle Label Generator</h1>")


@app.get("/preview", response_class=HTMLResponse)
def preview_get(request: Request, groom: str = "Groom", bride: str = "Bride", date: str = "2026-06-01", religion: str = "Hindu", theme: str = "Traditional"):
    # Render the preview template with concrete context to avoid TemplateResponse caching issues
    religion_name = religion.strip().title()
    theme_name = theme.strip().title()
    tpl = Template(PREVIEW_TEMPLATE_TEXT)
    data = LabelRequest(groom=groom, bride=bride, date=date, religion=religion_name, theme=theme_name)
    display_date = format_label_date(data.date)
    label_src = f"/label.png?groom={quote_plus(data.groom)}&bride={quote_plus(data.bride)}&date={quote_plus(data.date)}&religion={quote_plus(data.religion)}&theme={quote_plus(data.theme)}"
    context = {
        "data": {"groom": data.groom, "bride": data.bride, "date": display_date, "religion": data.religion, "theme": data.theme},
        "image": f"/static/images/{religion_name}/{theme_name.lower()}.png",
        "theme": get_theme_colors(theme_name),
        "event_text": get_event_text(religion_name),
        "label_src": label_src,
        "preview_data_json": dumps_safe_json({
            "groom": data.groom,
            "bride": data.bride,
            "date": data.date,
            "religion": data.religion,
            "theme": data.theme,
            "colors": get_theme_colors(theme),
        }),
    }
    rendered = tpl.render(**context)
    return HTMLResponse(content=rendered)


@app.post("/generate", response_class=HTMLResponse)
async def generate(request: Request, data: LabelRequest):
    errors = validate_label_data(data)
    if errors:
        raise HTTPException(status_code=400, detail=errors)
    religion_name = data.religion.strip().title()
    theme_name = data.theme.strip().title()
    tpl = Template(PREVIEW_TEMPLATE_TEXT)
    display_date = format_label_date(data.date)
    label_src = f"/label.png?groom={quote_plus(data.groom)}&bride={quote_plus(data.bride)}&date={quote_plus(data.date)}&religion={quote_plus(religion_name)}&theme={quote_plus(theme_name)}"
    context = {
        "data": {"groom": data.groom, "bride": data.bride, "date": display_date, "religion": religion_name, "theme": theme_name},
        "image": f"/static/images/{religion_name}/{theme_name.lower()}.png",
        "theme": get_theme_colors(theme_name),
        "event_text": get_event_text(religion_name),
        "label_src": label_src,
        "preview_data_json": dumps_safe_json({
            "groom": data.groom,
            "bride": data.bride,
            "date": data.date,
            "religion": data.religion,
            "theme": data.theme,
            "colors": get_theme_colors(data.theme),
        }),
    }
    rendered = tpl.render(**context)
    return HTMLResponse(content=rendered)


@app.post("/download/png")
async def download_png(data: LabelRequest):
    errors = validate_label_data(data)
    if errors:
        return JSONResponse(status_code=400, content={"errors": errors})
    png_stream = generate_20litre_wedding_label(data.groom, data.bride, data.date, data.religion, data.theme)
    # ensure outputs dir exists
    outputs_dir = BASE_DIR / "static" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # build sanitized filename
    def sanitize(name: str) -> str:
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name).strip().replace(' ', '_')

    fname = f"{sanitize(data.groom)}_{sanitize(data.bride)}_label.png"
    out_path = outputs_dir / fname

    # write copy to disk in static outputs and project downloads
    png_bytes = png_stream.getvalue()
    with open(out_path, "wb") as f:
        f.write(png_bytes)

    download_path = DOWNLOADS_DIR / fname
    with open(download_path, "wb") as f:
        f.write(png_bytes)

    # return stream for download and include saved filename header (project-relative)
    headers = {
        "Content-Disposition": f"attachment; filename={fname}",
        "X-Saved-Filename": str(download_path.relative_to(BASE_DIR)),
        "X-Public-URL": f"/downloads/{quote_plus(fname)}",
    }
    return StreamingResponse(BytesIO(png_bytes), media_type="image/png", headers=headers)


@app.post("/save/png")
async def save_png(data: LabelRequest):
    """Save the selected template PNG on the server and return JSON with path and public URL."""
    errors = validate_label_data(data)
    if errors:
        return JSONResponse(status_code=400, content={"errors": errors})

    png_stream = generate_20litre_wedding_label(data.groom, data.bride, data.date, data.religion, data.theme)
    outputs_dir = BASE_DIR / "static" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    def sanitize(name: str) -> str:
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name).strip().replace(' ', '_')

    fname = f"{sanitize(data.groom)}_{sanitize(data.bride)}_label.png"
    out_path = outputs_dir / fname
    png_bytes = png_stream.getvalue()
    with open(out_path, "wb") as f:
        f.write(png_bytes)

    download_path = DOWNLOADS_DIR / fname
    with open(download_path, "wb") as f:
        f.write(png_bytes)

    return JSONResponse(content={
        "saved": str(download_path.relative_to(BASE_DIR)),
        "url": f"/downloads/{quote_plus(fname)}",
    })


@app.post("/download/pdf")
async def download_pdf(data: LabelRequest):
    errors = validate_label_data(data)
    if errors:
        return JSONResponse(status_code=400, content={"errors": errors})
    pdf_stream = create_pdf(data)
    outputs_dir = BASE_DIR / "static" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    def sanitize(name: str) -> str:
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name).strip().replace(' ', '_')

    fname = f"{sanitize(data.groom)}_{sanitize(data.bride)}_label.pdf"
    out_path = outputs_dir / fname
    pdf_bytes = pdf_stream.getvalue()
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)

    download_path = DOWNLOADS_DIR / fname
    with open(download_path, "wb") as f:
        f.write(pdf_bytes)

    headers = {
        "Content-Disposition": f"attachment; filename={fname}",
        "X-Saved-Filename": str(download_path.relative_to(BASE_DIR)),
        "X-Public-URL": f"/downloads/{quote_plus(fname)}",
    }
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf", headers=headers)


@app.post("/save/pdf")
async def save_pdf(data: LabelRequest):
    """Save the generated PDF on the server and return JSON with path and public URL."""
    errors = validate_label_data(data)
    if errors:
        return JSONResponse(status_code=400, content={"errors": errors})

    pdf_stream = create_pdf(data)
    outputs_dir = BASE_DIR / "static" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    def sanitize(name: str) -> str:
        return "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name).strip().replace(' ', '_')

    fname = f"{sanitize(data.groom)}_{sanitize(data.bride)}_label.pdf"
    out_path = outputs_dir / fname
    pdf_bytes = pdf_stream.getvalue()
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)

    download_path = DOWNLOADS_DIR / fname
    with open(download_path, "wb") as f:
        f.write(pdf_bytes)

    return JSONResponse(content={
        "saved": str(download_path.relative_to(BASE_DIR)),
        "url": f"/downloads/{quote_plus(fname)}",
    })


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
