"""Tests for text style extraction heuristics."""
from __future__ import annotations

import numpy as np
from PIL import Image
from yaku.render.style_extract import estimate_text_style, TextStyle


def test_style_extract_fallback_on_blank_image():
    # Blank/uniform image should return fallback style (white fill, black stroke)
    img = Image.new("RGB", (100, 50), (128, 128, 128))
    style = estimate_text_style(img)
    assert style.fill_rgb == (255, 255, 255)
    assert style.stroke_rgb == (0, 0, 0)


def test_style_extract_with_simulated_text():
    # Draw a simulated yellow text with a blue outline
    arr = np.zeros((50, 150, 3), dtype=np.uint8)
    
    # Fill background with some dark color
    arr[:] = (20, 20, 20)
    
    # Draw bright yellow text pixels (gray > 200)
    arr[15:35, 30:120] = (255, 255, 0)
    
    # Draw blue outline around yellow pixels
    arr[13:15, 28:122] = (0, 0, 255)
    arr[35:37, 28:122] = (0, 0, 255)
    arr[15:35, 28:30] = (0, 0, 255)
    arr[15:35, 120:122] = (0, 0, 255)
    
    img = Image.fromarray(arr)
    style = estimate_text_style(img)
    
    # Yellow fill (255, 255, 0) should be detected
    assert style.fill_rgb[0] > 200
    assert style.fill_rgb[1] > 200
    assert style.fill_rgb[2] < 50
    
    # Blue stroke (0, 0, 255) should be detected
    assert style.stroke_rgb[0] < 50
    assert style.stroke_rgb[1] < 50
    assert style.stroke_rgb[2] > 200
    
    # Bounding box vertical height is 15:35 (20 pixels), so font size estimate should be around 20-22
    assert style.estimated_font_size is not None
    assert 18 <= style.estimated_font_size <= 24
