# AI Wedding Bottle Label Generator

A responsive web application to generate premium wedding water bottle label previews, download PNG and PDF versions, and save personalized designs for Hindu, Muslim, and Christian weddings.

## Project Structure

- `backend/main.py` - FastAPI application with label generation and download routes
- `templates/index.html` - Home page with label form
- `templates/preview.html` - Generated preview page
- `static/css/style.css` - Responsive styling
- `static/js/script.js` - Client-side form handling and downloads
- `static/images/` - Religion images used in the label design
- `requirements.txt` - Python dependencies

## Installation

1. Open a terminal in the project root:
   ```powershell
   cd c:\Users\Anu\OneDrive\Desktop\label
   ```

2. Create and activate a virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

4. Generate the sample religion images (required once):
   ```powershell
   python - <<'PY'
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

base = Path(r'c:\Users\Anu\OneDrive\Desktop\label\static\images')
base.mkdir(parents=True, exist_ok=True)
for name, color, symbol in [
    ('hindu.png', '#E8C26D', '𑀳'),
    ('muslim.png', '#8CBF9F', '☪'),
    ('christian.png', '#B28FD6', '✛'),
]:
    img = Image.new('RGBA', (300, 300), color)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arial.ttf', 150)
    except OSError:
        font = ImageFont.load_default()
    w, h = draw.textsize(symbol, font=font)
    draw.text(((300 - w) / 2, (300 - h) / 2), symbol, font=font, fill='white')
    draw.ellipse((80, 80, 220, 220), outline='white', width=8)
    img.save(base / name)
PY
   ```

## Run Locally

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000` in your browser.

## Features

- Mobile-first responsive design
- Premium wedding-themed layout
- Dynamic preview with religion-specific image
- PNG and PDF downloads generated server-side
- Validation and loading animation
