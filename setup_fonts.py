#!/usr/bin/env python3
"""
Direct font downloader - downloads fonts from GitHub raw URLs directly.
No git clone required. Fonts are cached in static/fonts/ directory.
"""
import os
import urllib.request
from pathlib import Path

FONTS = {
    "Cinzel-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/cinzel/Cinzel-Bold.ttf",
    "CinzelDecorative-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/cinzeldecorative/CinzelDecorative-Regular.ttf",
    "PlayfairDisplay-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/playfairdisplay/PlayfairDisplay-Regular.ttf",
    "PlayfairDisplay-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/playfairdisplay/PlayfairDisplay-Bold.ttf",
    "Montserrat-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Regular.ttf",
    "Montserrat-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Bold.ttf",
    "Montserrat-Italic.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat-Italic.ttf",
    "Poppins-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Regular.ttf",
    "Poppins-Bold.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Bold.ttf",
    "Poppins-Italic.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Italic.ttf",
    "GreatVibes-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/greatvibes/GreatVibes-Regular.ttf",
    "CormorantGaramond-Regular.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/cormorantgaramond/CormorantGaramond-Regular.ttf",
}

def download_fonts():
    font_dir = Path(os.getcwd()) / "static" / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading fonts to {font_dir}...")
    failed = []
    
    for filename, url in FONTS.items():
        dest = font_dir / filename
        
        # Skip if already exists
        if dest.exists():
            print(f"✓ {filename} (cached)")
            continue
        
        try:
            print(f"  Downloading {filename}...")
            urllib.request.urlretrieve(url, str(dest))
            print(f"✓ {filename}")
        except Exception as e:
            print(f"✗ {filename}: {e}")
            failed.append(filename)
    
    if failed:
        print(f"\nFailed to download: {', '.join(failed)}")
        return False
    
    print(f"\n✓ All fonts ready in {font_dir}")
    return True

if __name__ == "__main__":
    success = download_fonts()
    exit(0 if success else 1)
