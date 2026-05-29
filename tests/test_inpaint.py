"""Tests for the OpenCV inpainter and rectangular mask builder."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from yaku.core.config import InpaintConfig
from yaku.core.errors import InvalidBackendError
from yaku.core.image_utils import Rect
from yaku.v2_mirror.inpaint import OpenCVInpainter, build_rect_mask, create_inpainter


def _noise(w: int = 64, h: int = 48, seed: int = 0) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 256, (h, w, 3), dtype=np.uint8))


# ---------------------------------------------------------------------------
# Mask builder
# ---------------------------------------------------------------------------

def test_mask_has_image_size_and_l_mode():
    mask = build_rect_mask((100, 80), Rect(10, 10, 20, 20), padding=5)
    assert mask.size == (100, 80)
    assert mask.mode == "L"


def test_mask_marks_region_white():
    mask = build_rect_mask((100, 80), Rect(10, 10, 20, 20), padding=0)
    arr = np.array(mask)
    assert arr.max() == 255
    assert arr[15, 15] == 255   # inside
    assert arr[0, 0] == 0       # outside


def test_mask_padding_clamps_to_bounds():
    # Rect near the top-left corner with padding far larger than the margin.
    mask = build_rect_mask((100, 80), Rect(2, 2, 10, 10), padding=50)
    arr = np.array(mask)
    ys, xs = np.nonzero(arr)
    assert xs.min() >= 0 and ys.min() >= 0
    assert xs.max() <= 99 and ys.max() <= 79
    assert arr.max() == 255


def test_mask_padding_expands_region():
    base = np.array(build_rect_mask((200, 200), Rect(50, 50, 40, 40), padding=0))
    padded = np.array(build_rect_mask((200, 200), Rect(50, 50, 40, 40), padding=10))
    assert np.count_nonzero(padded) > np.count_nonzero(base)


def test_mask_fully_outside_is_blank():
    mask = build_rect_mask((50, 50), Rect(100, 100, 10, 10), padding=0)
    assert np.count_nonzero(np.array(mask)) == 0


# ---------------------------------------------------------------------------
# OpenCV inpainter
# ---------------------------------------------------------------------------

def test_inpaint_returns_same_size():
    img = _noise()
    mask = build_rect_mask(img.size, Rect(10, 10, 20, 15), padding=3)
    out = OpenCVInpainter().inpaint(img, mask)
    assert out.size == img.size
    assert out.mode == "RGB"


def test_inpaint_ns_method_returns_same_size():
    img = _noise(seed=1)
    mask = build_rect_mask(img.size, Rect(8, 8, 16, 16), padding=2)
    out = OpenCVInpainter(method="ns").inpaint(img, mask)
    assert out.size == img.size


def test_inpaint_modifies_masked_region():
    # Distinct bright block over a dark background; inpaint should blend it out.
    arr = np.zeros((48, 64, 3), dtype=np.uint8)
    arr[15:30, 20:40] = (255, 0, 0)
    img = Image.fromarray(arr)
    mask = build_rect_mask(img.size, Rect(20, 15, 20, 15), padding=2)
    out = np.array(OpenCVInpainter().inpaint(img, mask))
    # The center of the painted block should no longer be pure red.
    assert tuple(out[22, 30]) != (255, 0, 0)


def test_inpaint_invalid_method_raises():
    with pytest.raises(InvalidBackendError):
        OpenCVInpainter(method="bogus")


def test_inpaint_mask_size_mismatch_raises():
    from yaku.core.errors import InpaintError

    img = _noise(64, 48)
    wrong = build_rect_mask((32, 24), Rect(1, 1, 4, 4), padding=0)
    with pytest.raises(InpaintError):
        OpenCVInpainter().inpaint(img, wrong)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def test_create_inpainter_opencv():
    inp = create_inpainter(InpaintConfig(backend="opencv", method="telea", radius=3))
    assert isinstance(inp, OpenCVInpainter)


def test_create_inpainter_unknown_backend_raises():
    with pytest.raises(InvalidBackendError):
        create_inpainter(InpaintConfig(backend="not-a-backend"))
